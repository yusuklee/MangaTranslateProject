
import fnmatch
import hashlib
import os
import re
import shutil
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
REQUIREMENTS_TOTAL = os.path.join(ROOT, "requirements.total")   # build/build.py 가 잰 첫 실행 다운로드 총 바이트
DATA = os.environ.get("MANGA_DATA_DIR") or ROOT
PYLIB = os.path.join(DATA, "pylib")
MARK = os.path.join(PYLIB, ".installed")
TMP = os.path.join(DATA, "tmp")
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"
EXTRA_NO_DEPS = "simple-lama-inpainting==0.1.2"   # numpy<2 선언 때문에 의존성 검사 없이 설치 (requirements.txt 참고)
HF_MODELS = [
    ("mayocream/koharu-layout-rfdetr-seg-2xl-1152", ["model.safetensors"]),
    ("kha-white/manga-ocr-base", ["*.json", "*.txt", "*.safetensors"]),
]
FALLBACK_TOTAL = 3_400_000_000   # requirements.total 이 없을 때의 대략치
INSTALL_SIZE = 5_400_000_000     # 설치가 끝났을 때 pylib 크기 (압축 해제 진행률의 분모. 2026-09 측정값)


def setup_env():
    os.chdir(ROOT)
    os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
    if sys.stdout is None or sys.stderr is None:   # pythonw: 콘솔이 없다 → 로그 파일로
        log = open(os.path.join(DATA, "logs", "app.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    os.environ["HF_HOME"] = os.path.join(DATA, "hf")
    os.environ.setdefault("MANGA_PROJECTS_DIR", os.path.join(DATA, "projects"))
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


def download_total():
    try:
        return int(open(REQUIREMENTS_TOTAL).read().strip()) or FALLBACK_TOTAL
    except (OSError, ValueError):
        return FALLBACK_TOTAL


def dir_size(path):
    total = 0
    for base, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]





#pip 출력 줄에서 다운로드 진행률을 계산한다. 파일마다 "Downloading x.whl (7.0 MB)" 뒤에 "Progress X of Y" 가 이어진다
class PipProgress:
    SIZE = re.compile(r"\((\d+(?:\.\d+)?)\s*(kB|MB|GB|bytes)\)")
    UNIT = {"bytes": 1, "kB": 1e3, "MB": 1e6, "GB": 1e9}

    def __init__(self, total):
        self.total, self.done, self.cur, self.cur_total = total, 0, 0, 0

    def feed(self, line):
        if line.startswith("Progress "):
            m = re.match(r"Progress (\d+) of (\d+)", line)
            if m:
                self.cur, self.cur_total = int(m.group(1)), int(m.group(2))
            return
        if ".metadata" in line:   # 메타데이터 파일(수 kB)은 무시
            return
        if line.startswith(("Downloading ", "Using cached ")):
            self.done += self.cur           # 직전 파일은 끝났다
            self.cur = 0
            m = self.SIZE.search(line)
            size = int(float(m.group(1)) * self.UNIT[m.group(2)]) if m else 0
            if line.startswith("Using cached"):   # 이미 받아 둔 파일: 바로 완료로 친다
                self.done += size
                self.cur_total = 0
            else:
                self.cur_total = size

    @property
    def pct(self):
        return min(99, int(100 * (self.done + self.cur) / self.total)) if self.total else None


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
            self.set(phase="load", text="Loading models", done=3)
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

    #pip 으로 requirements.txt 를 pylib 에 설치. 진행 막대만 갱신하고 pip 출력은 로그로
    def install(self):
        os.makedirs(PYLIB, exist_ok=True)
        cmd = [PYTHON, PIP, "install", "--target", PYLIB, "--upgrade", "-r", REQUIREMENTS,
               "--index-url", TORCH_INDEX, "--extra-index-url", "https://pypi.org/simple",
               "--no-warn-script-location", "--progress-bar", "raw", "--disable-pip-version-check",
               "--no-build-isolation", "--no-cache-dir"]   # 캐시를 두면 4GB 가 pip 캐시 폴더에 또 남는다   # embeddable 파이썬은 격리 빌드 환경을 못 본다 → 동봉한 setuptools(pylib_boot) 로 빌드
        progress = PipProgress(download_total())
        self.set(phase="download", text="Downloading packages", pct=0, done=0)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        shutil.rmtree(TMP, ignore_errors=True)
        os.makedirs(TMP)
        env = dict(os.environ, TMPDIR=TMP, TEMP=TMP, TMP=TMP)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=flags, env=env)
        tail = []
        installing = threading.Event()

        def watch_install():   # pip --target 은 TMP\pip-target-* 에 먼저 풀고 끝에 pylib 로 옮긴다 → 둘을 합쳐 잰다
            while not installing.wait(2):
                pass
            while p.poll() is None:
                size = dir_size(PYLIB) + sum(dir_size(os.path.join(TMP, d)) for d in os.listdir(TMP) if d.startswith("pip-target-"))
                self.set(phase="install", text="Installing packages", pct=min(99, int(100 * size / INSTALL_SIZE)), done=1)
                time.sleep(2)

        threading.Thread(target=watch_install, daemon=True).start()
        for line in p.stdout:
            line = line.strip()
            if not line:
                continue
            tail = (tail + [line])[-30:]
            if not line.startswith("Progress "):
                print("[pip]", line, flush=True)
            progress.feed(line)
            if line.startswith("Installing collected"):
                installing.set()
            elif not installing.is_set():
                self.set(phase="download", text="Downloading packages", pct=progress.pct, done=0)
        if p.wait() != 0:
            raise RuntimeError("Package install failed: " + "\n".join(tail[-5:]))
        #simple-lama-inpainting 은 numpy<2 를 요구해 위 목록과 충돌한다 (numpy 2.x 로 잘 돈다) → 의존성 검사 없이 따로
        r = subprocess.run([PYTHON, PIP, "install", "--target", PYLIB, "--no-deps", "--upgrade", EXTRA_NO_DEPS,
                            "--no-warn-script-location", "--disable-pip-version-check", "--no-cache-dir", "-q"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags, env=env)
        if r.returncode != 0:
            raise RuntimeError("Package install failed: " + (r.stdout + r.stderr)[-500:])
        shutil.rmtree(TMP, ignore_errors=True)
        with open(MARK, "w", encoding="utf-8") as f:
            f.write(req_hash())

    #Hugging Face 모델을 미리 받는다 (안 받아도 backend 가 처음 쓸 때 받지만, 그러면 진행 표시가 없다)
    def download_models(self):
        from huggingface_hub import HfApi, snapshot_download
        from huggingface_hub.utils import tqdm as hf_tqdm

        total = 0
        for repo, patterns in HF_MODELS:   # 받을 파일 크기 합 (진행 막대의 분모)
            try:
                for s in HfApi().model_info(repo, files_metadata=True).siblings:
                    if any(fnmatch.fnmatch(s.rfilename, pat) for pat in patterns):
                        total += s.size or 0
            except Exception:   # noqa: BLE001  크기를 못 얻으면 퍼센트 없이 진행
                pass
        got = {"n": 0}
        boot = self

        class Progress(hf_tqdm):   # 파일 단위 막대(unit="B")의 증가분만 더한다
            def update(self, n=1):
                if getattr(self, "unit", "") == "B" and n:
                    got["n"] += n
                    boot.set(phase="download", text="Downloading models", pct=min(99, int(100 * got["n"] / total)) if total else None, done=2)
                return super().update(n)

        self.set(phase="download", text="Downloading models", pct=0 if total else None, done=2)
        for repo, patterns in HF_MODELS:
            snapshot_download(repo, allow_patterns=patterns, tqdm_class=Progress)

    def serve(self):
        import uvicorn
        from backend import app
        uvicorn.run(app, host="127.0.0.1", port=self.port, log_level="warning")


def loading_html():
    return """<!doctype html><html><head><meta charset="utf-8"><title>Manga Translator</title>
<style>
  html,body{height:100%;margin:0;font-family:Segoe UI,system-ui,sans-serif;background:#0a1033;color:#fff}
  .c{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:0 24px}
  .title{font-size:15px}
  .bar{width:360px;height:8px;border-radius:4px;background:#1c2657;overflow:hidden;position:relative}
  .bar i{display:block;height:100%;width:0;background:#f2760a;transition:width .4s}
  .bar.busy i{width:30%;animation:slide 1.2s infinite ease-in-out}
  @keyframes slide{from{margin-left:-30%}to{margin-left:100%}}
  small{color:#9aa4d6;text-align:center;line-height:1.5;white-space:pre-wrap;max-width:520px}
  button{display:none;margin-top:8px;padding:6px 18px;border:0;border-radius:6px;background:#f2760a;color:#fff;font:inherit;cursor:pointer}
</style></head><body><div class="c">
  <div class="title" id="title">Starting</div>
  <div class="bar busy" id="bar"><i id="fill"></i></div>
  <small id="sub"></small>
  <button id="retry" onclick="retry()">Retry</button>
</div>
<script>
  const $ = id => document.getElementById(id);
  function retry() { $("retry").style.display = "none"; window.pywebview.api.retry(); }
  async function tick() {
    let s;
    try { s = await window.pywebview.api.status(); } catch { return setTimeout(tick, 500); }
    const err = s.phase === "error";
    const pct = (s.pct === null || s.pct === undefined) ? null : s.pct;
    $("title").textContent = err ? "Setup failed" : (s.done === undefined ? "" : `${s.done}/3  `) + (s.text || "Starting") + (pct !== null ? `  ${pct}%` : "");
    $("bar").style.display = err ? "none" : "";
    $("bar").classList.toggle("busy", pct === null);
    $("fill").style.width = pct === null ? "" : pct + "%";
    $("sub").textContent = err ? s.text : (s.phase === "download" || s.phase === "install") ? "First start only. This can take several minutes." : "";
    $("retry").style.display = err ? "" : "none";
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

    def fullscreen(self):
        self._boot.window.toggle_fullscreen()


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
