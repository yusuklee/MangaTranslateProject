import os
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist", "MangaTranslator")
APP = os.path.join(OUT, "app")
CACHE = os.path.join(ROOT, "build", "cache")
PY_VERSION = "3.13.11"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
PIP_URL = "https://bootstrap.pypa.io/pip/pip.pyz"


def fetch(url, dest):
    if not os.path.isfile(dest):
        urllib.request.urlretrieve(url,dest)
    return dest


def main():
    os.makedirs(CACHE, exist_ok=True)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(APP)

    # 1) 파이썬
    zip_path = fetch(PY_URL, os.path.join(CACHE, os.path.basename(PY_URL)))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(os.path.join(APP, "python"))
    major_minor = "".join(PY_VERSION.split(".")[:2])
    with open(os.path.join(APP, "python", f"python{major_minor}._pth"), "w", encoding="utf-8") as f:
        f.write(f"python{major_minor}.zip\n.\n..\n..\\pylib_boot\nimport site\n")   # ..=app 폴더 (launch.py, backend.py, Process/)
    shutil.copy2(fetch(PIP_URL, os.path.join(CACHE, "pip.pyz")), os.path.join(APP, "pip.pyz"))

    # 2) 앱 코드와 리소스
    for f in ["launch.py", "backend.py", "requirements.txt", "comictextdetector.pt.onnx", "anime-manga-big-lama.pt"]:
        shutil.copy2(os.path.join(ROOT, f), os.path.join(APP, f))
    shutil.copytree(os.path.join(ROOT, "Process"), os.path.join(APP, "Process"), ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(ROOT, "frontend", "dist"), os.path.join(APP, "frontend", "dist"))
    shutil.copytree(os.path.join(ROOT, "fonts"), os.path.join(APP, "fonts"))
    with open(os.path.join(OUT, "MangaTranslator.bat"), "w", encoding="ascii", newline="") as f:
        f.write("\r\n".join([
            "@echo off",
            'if not exist "%~dp0app\\python\\pythonw.exe" (',
            "  echo Please extract the zip first, then run MangaTranslator.bat from the extracted folder.",
            "  pause",
            "  exit /b 1",
            ")",
            'start "" "%~dp0app\\python\\pythonw.exe" "%~dp0app\\launch.py"',
        ]) + "\r\n")

    # 3) 진행 창용 pywebview 만 미리 설치
    py = os.path.join(APP, "python", "python.exe")
    boot = os.path.join(APP, "pylib_boot")
    common = ["--target", boot, "--no-warn-script-location", "--disable-pip-version-check", "--no-cache-dir", "-q"]
    subprocess.run([py, os.path.join(APP, "pip.pyz"), "install", "setuptools", "wheel", *common], check=True)
    subprocess.run([py, os.path.join(APP, "pip.pyz"), "install", "pywebview==6.2.1", "--no-build-isolation", *common], check=True)


    write_download_total(py)

    total = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(OUT) for f in fs)
    print(f"done: {OUT}  ({total / 1e6:.0f} MB)")

    zip_out = OUT + ".zip"
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for b, _, fs in os.walk(OUT):
            for f in fs:
                path = os.path.join(b, f)
                z.write(path, os.path.relpath(path, os.path.dirname(OUT)))
    print(f"zip: {zip_out}  ({os.path.getsize(zip_out) / 1e6:.0f} MB)")


def write_download_total(py):
    import json
    import tempfile
    report = os.path.join(tempfile.gettempdir(), "mt_pip_report.json")
    subprocess.run([py, os.path.join(APP, "pip.pyz"), "install", "--dry-run", "--report", report, "-r", os.path.join(APP, "requirements.txt"),
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
    with open(os.path.join(APP, "requirements.total"), "w") as f:
        f.write(str(total))
    print(f"  first-run download: {len(urls)} files, {total / 1e9:.2f} GB -> requirements.total")




if __name__ == "__main__":
    main()
