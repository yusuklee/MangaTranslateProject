"""포터블 앱 폴더 만들기 (BallonsTranslator 방식) → dist/MangaTranslator/
    python build/make_portable.py

들어가는 것:
    python/            python.org embeddable (3.13, 약 11MB). python313._pth 로 앱 폴더와 pylib_boot 를 경로에 넣는다
    pip.pyz            pip (첫 실행 때 requirements.txt 설치용)
    pylib_boot/        pywebview(설치 진행 창용)·setuptools·wheel 만 미리 설치. 나머지는 첫 실행 때 사용자 PC 의 pylib 에
    launch.py app.py backend.py Process/ frontend/dist/ fonts/ requirements.txt icon.ico
    comictextdetector.pt.onnx (91MB), anime-manga-big-lama.pt (197MB)
안 들어가는 것: torch 등 (첫 실행 때 약 3GB 설치), RF-DETR·manga-ocr 가중치 (첫 실행 때 Hugging Face 에서), .env
"""
import os
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist", "MangaTranslator")
CACHE = os.path.join(ROOT, "build", "cache")
PY_VERSION = "3.13.11"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
PIP_URL = "https://bootstrap.pypa.io/pip/pip.pyz"


def fetch(url, dest):
    if not os.path.isfile(dest):
        print("download", url, flush=True)
        urllib.request.urlretrieve(url, dest)
    return dest


def main():
    os.makedirs(CACHE, exist_ok=True)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    # 1) 파이썬
    zip_path = fetch(PY_URL, os.path.join(CACHE, os.path.basename(PY_URL)))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(os.path.join(OUT, "python"))
    major_minor = "".join(PY_VERSION.split(".")[:2])
    with open(os.path.join(OUT, "python", f"python{major_minor}._pth"), "w", encoding="utf-8") as f:
        f.write(f"python{major_minor}.zip\n.\n..\n..\\pylib_boot\nimport site\n")   # ..=앱 폴더 (launch.py, backend.py, Process/)
    shutil.copy2(fetch(PIP_URL, os.path.join(CACHE, "pip.pyz")), os.path.join(OUT, "pip.pyz"))

    # 2) 앱 코드와 리소스
    for f in ["launch.py", "app.py", "backend.py", "requirements.txt", "comictextdetector.pt.onnx", "anime-manga-big-lama.pt"]:
        shutil.copy2(os.path.join(ROOT, f), os.path.join(OUT, f))
    shutil.copytree(os.path.join(ROOT, "Process"), os.path.join(OUT, "Process"), ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "frontend", "dist"), os.path.join(OUT, "frontend", "dist"))
    shutil.copytree(os.path.join(ROOT, "fonts"), os.path.join(OUT, "fonts"))
    shutil.copy2(os.path.join(ROOT, "build", "icon.ico"), os.path.join(OUT, "icon.ico"))

    # 3) 진행 창용 pywebview 만 미리 설치
    py = os.path.join(OUT, "python", "python.exe")
    subprocess.run([py, os.path.join(OUT, "pip.pyz"), "install", "--target", os.path.join(OUT, "pylib_boot"),
                    "pywebview==6.2.1", "setuptools", "wheel", "--no-warn-script-location", "--disable-pip-version-check", "-q"], check=True)
    #setuptools·wheel: fire·unidic-lite 처럼 소스로만 배포되는 패키지를 첫 실행 때 빌드하려면 필요하다.
    #embeddable 파이썬은 ._pth 로 경로가 고정돼 pip 의 격리 빌드 환경을 못 보므로, launch.py 는 --no-build-isolation 으로 설치한다

    # 4) 첫 실행 때 받을 총 바이트 수 → requirements.total (진행 막대의 분모). 버전이 고정돼 있어 빌드 때 한 번 재면 된다
    write_download_total(py)

    total = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(OUT) for f in fs)
    print(f"done: {OUT}  ({total / 1e6:.0f} MB)")


def write_download_total(py):
    import json
    import tempfile
    report = os.path.join(tempfile.gettempdir(), "mt_pip_report.json")
    subprocess.run([py, os.path.join(OUT, "pip.pyz"), "install", "--dry-run", "--report", report, "-r", os.path.join(OUT, "requirements.txt"),
                    "--index-url", "https://download.pytorch.org/whl/cu128", "--extra-index-url", "https://pypi.org/simple",
                    "--no-build-isolation", "--disable-pip-version-check", "-q"], check=True)
    urls = [i["download_info"]["url"] for i in json.load(open(report, encoding="utf-8"))["install"]]
    total = 0
    for url in urls:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "pip/26.0"})   # UA 없으면 download.pytorch.org 가 403
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                total += int(r.headers.get("Content-Length") or 0)
        except Exception as e:   # noqa: BLE001
            print("  size unknown:", url[-60:], e)
    with open(os.path.join(OUT, "requirements.total"), "w") as f:
        f.write(str(total))
    print(f"  first-run download: {len(urls)} files, {total / 1e9:.2f} GB -> requirements.total")


if __name__ == "__main__":
    main()
