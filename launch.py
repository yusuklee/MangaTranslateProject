"""포터블 앱 실행기 (BallonsTranslator 방식). 설치 파일에는 파이썬(embeddable)·앱 코드·글꼴·작은 모델만 들어 있고,
무거운 패키지(torch 등 약 3GB)와 모델 가중치는 처음 실행할 때 사용자 PC 에 받는다.

    <앱 폴더>\\python\\pythonw.exe launch.py      ← 바로 가기가 이걸 실행한다

  %LOCALAPPDATA%\\MangaTranslator\\pylib\\   requirements.txt 의 패키지 (pip --target). 앱을 지우거나 업데이트해도 남는다
  %LOCALAPPDATA%\\MangaTranslator\\hf\\      Hugging Face 모델 캐시 (RF-DETR, manga-ocr)
  %LOCALAPPDATA%\\MangaTranslator\\logs\\    app.log (pythonw 는 콘솔이 없으므로 출력을 여기로)

흐름: 창을 먼저 띄우고 → (없으면) pip 설치, 진행 상황 표시 → (없으면) 모델 다운로드 → 서버 시작 → 창을 앱으로 넘김.
실패하면 메시지와 Retry 버튼. 개발 PC 에서는 이 파일 대신 `python app.py` 를 쓴다.
"""
import hashlib
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(ROOT, "python", "python.exe")
PIP = os.path.join(ROOT, "pip.pyz")
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")
DATA = os.environ.get("MANGA_DATA_DIR") or os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "MangaTranslator")
PYLIB = os.path.join(DATA, "pylib")
MARK = os.path.join(PYLIB, ".installed")
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
EXTRA_NO_DEPS = "simple-lama-inpainting==0.1.2"   # numpy<2 선언 때문에 의존성 검사 없이 설치 (requirements.txt 참고)
HF_MODELS = [
    ("mayocream/koharu-layout-rfdetr-seg-2xl-1152", ["model.safetensors"]),
    ("kha-white/manga-ocr-base", ["*.json", "*.txt", "*.safetensors"]),
]


def setup_env():
    os.chdir(ROOT)
    os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
    if sys.stdout is None or sys.stderr is None:   # pythonw: 콘솔이 없다 → 로그 파일로
        log = open(os.path.join(DATA, "logs", "app.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    os.environ["HF_HOME"] = os.path.join(DATA, "hf")
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ.setdefault("LAMA_MODEL", os.path.join(ROOT, "anime-manga-big-lama.pt"))
    os.environ.setdefault("CTD_MODEL", os.path.join(ROOT, "comictextdetector.pt.onnx"))
    if PYLIB not in sys.path:
        sys.path.insert(0, PYLIB)


def req_hash():
    return hashlib.sha256(open(REQUIREMENTS, "rb").read()).hexdigest()


def installed():
    try:
        return open(MARK, encoding="utf-8").read().strip() == req_hash()
    except OSError:
        return False


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Boot:
    """상태를 들고 뒤에서 설치·다운로드·서버 시작을 한다. 로딩 화면이 status() 를 0.5초마다 읽는다"""

    def __init__(self, window, port):
        self.window, self.port = window, port
        self.url = f"http://127.0.0.1:{port}"
        self.state = {"phase": "start"}
        self.lock = threading.Lock()

    def set(self, **kw):
        with self.lock:
            self.state = kw

    def status(self):
        with self.lock:
            return dict(self.state)

    def retry(self):
        if self.status().get("phase") == "error":
            self.start()
        return True

    def pick_folder(self):
        import webview
        picked = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        return {"path": picked[0]} if picked else None

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            if not installed():
                self.install()
            import importlib
            importlib.invalidate_caches()
            self.download_models()
            self.set(phase="load", text="Loading models...")
            threading.Thread(target=self.serve, daemon=True).start()
            while True:
                try:
                    with urllib.request.urlopen(self.url + "/models", timeout=2) as r:
                        if r.status == 200:
                            break
                except Exception:   # noqa: BLE001  아직 안 떴다
                    pass
                time.sleep(1)
            self.window.load_url(self.url)
        except Exception as e:   # noqa: BLE001
            print(f"[launch] failed: {type(e).__name__}: {e}", flush=True)
            self.set(phase="error", text=str(e)[:300])

    #pip 으로 requirements.txt 를 pylib 에 설치. 출력 줄을 읽어 진행 상황으로 보여준다
    def install(self):
        os.makedirs(PYLIB, exist_ok=True)
        cmd = [PYTHON, PIP, "install", "--target", PYLIB, "--upgrade", "-r", REQUIREMENTS,
               "--index-url", TORCH_INDEX, "--extra-index-url", "https://pypi.org/simple",
               "--no-warn-script-location", "--progress-bar", "off", "--disable-pip-version-check",
               "--no-build-isolation"]   # embeddable 파이썬은 격리 빌드 환경을 못 본다 → 동봉한 setuptools(pylib_boot) 로 빌드
        self.set(phase="install", text="Preparing to install PyTorch and other packages (about 3 GB, first start only)")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=flags)
        tail = []
        for line in p.stdout:
            line = line.strip()
            if not line:
                continue
            tail = (tail + [line])[-30:]
            print("[pip]", line, flush=True)
            if line.startswith(("Collecting", "Downloading", "Installing collected", "Successfully")):
                self.set(phase="install", text=line[:160])
        if p.wait() != 0:
            raise RuntimeError("Package install failed:\n" + "\n".join(tail[-5:]))
        #simple-lama-inpainting 은 numpy<2 를 요구해 위 목록과 충돌한다 (numpy 2.x 로 잘 돈다) → 의존성 검사 없이 따로
        self.set(phase="install", text="Installing simple-lama-inpainting")
        r = subprocess.run([PYTHON, PIP, "install", "--target", PYLIB, "--no-deps", "--upgrade", EXTRA_NO_DEPS,
                            "--no-warn-script-location", "--disable-pip-version-check", "-q"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags)
        if r.returncode != 0:
            raise RuntimeError("Package install failed: " + (r.stdout + r.stderr)[-500:])
        with open(MARK, "w", encoding="utf-8") as f:
            f.write(req_hash())

    #Hugging Face 모델을 미리 받는다 (안 받아도 backend 가 처음 쓸 때 받지만, 그러면 진행 표시가 없다)
    def download_models(self):
        from huggingface_hub import snapshot_download
        for i, (repo, patterns) in enumerate(HF_MODELS):
            self.set(phase="download", text=f"Downloading model {i + 1}/{len(HF_MODELS)}: {repo} (first start only)")
            snapshot_download(repo, allow_patterns=patterns)

    def serve(self):
        import uvicorn
        from backend import app
        uvicorn.run(app, host="127.0.0.1", port=self.port, log_level="warning")


def loading_html():
    return """<!doctype html><html><head><meta charset="utf-8"><title>Manga Translator</title>
<style>
  html,body{height:100%;margin:0;font-family:Segoe UI,system-ui,sans-serif;background:#0a1033;color:#fff}
  .c{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:0 24px}
  .dot{width:10px;height:10px;border-radius:50%;background:#f2760a;animation:b 1s infinite alternate}
  @keyframes b{to{opacity:.2}}
  small{color:#9aa4d6;max-width:520px;text-align:center;line-height:1.5;white-space:pre-wrap}
  button{display:none;margin-top:8px;padding:6px 18px;border:0;border-radius:6px;background:#f2760a;color:#fff;font:inherit;cursor:pointer}
</style></head><body><div class="c">
  <div class="dot" id="dot"></div><div id="title">Starting...</div>
  <small id="sub"></small>
  <button id="retry" onclick="retry()">Retry</button>
</div>
<script>
  const $ = id => document.getElementById(id);
  const titles = {start: "Starting...", install: "Installing packages", download: "Downloading models", load: "Loading models...", error: "Setup failed"};
  function retry() { $("retry").style.display = "none"; window.pywebview.api.retry(); }
  async function tick() {
    let s;
    try { s = await window.pywebview.api.status(); } catch { return setTimeout(tick, 500); }
    $("title").textContent = titles[s.phase] || s.phase;
    $("sub").textContent = s.text || "";
    $("dot").style.display = s.phase === "error" ? "none" : "";
    $("retry").style.display = s.phase === "error" ? "" : "none";
    setTimeout(tick, 500);
  }
  window.addEventListener("pywebviewready", tick);
</script></body></html>"""


class Api:
    """pywebview 에 노출되는 함수들 (window.pywebview.api.*). Boot 로 넘긴다"""

    def __init__(self):
        self._boot = None

    def status(self):
        return self._boot.status()

    def retry(self):
        return self._boot.retry()

    def pick_folder(self):
        return self._boot.pick_folder()


def main():
    setup_env()
    import webview
    api = Api()
    window = webview.create_window("Manga Translator", html=loading_html(), js_api=api, width=1400, height=900, min_size=(900, 600))
    api._boot = Boot(window, free_port())
    api._boot.start()
    webview.start()
    sys.exit(0)


if __name__ == "__main__":
    main()
