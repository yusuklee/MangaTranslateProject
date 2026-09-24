"""데스크톱 앱 실행기: 백엔드(FastAPI)를 빈 포트에 띄우고 pywebview 창으로 연다.

  python app.py            개발 PC 에서 앱처럼 실행 (frontend/dist 가 있어야 함: cd frontend && npm run build)
  PyInstaller 로 묶으면 이 파일이 exe 의 진입점

흐름: 창을 먼저 "Loading models..." 화면으로 띄우고, 뒤에서 모델을 올린 뒤(backend import) 서버가 응답하면 그 화면이 앱으로 넘어간다.
프런트는 window.pywebview.api.pick_folder() 로 윈도우 폴더 선택창을 열 수 있다 (브라우저의 "N개 파일 업로드" 확인창이 없음).
"""
import socket
import sys
import threading

import webview

APP_NAME = "Manga Translator"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port):
    # 여기서 import 해야 모델 로드(수 초)가 창을 막지 않는다
    import uvicorn
    from backend import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


class Api:
    """프런트(JS)에서 부르는 함수들. window.pywebview.api.<이름>()"""

    def __init__(self):
        self._window = None   # 밑줄: pywebview 는 js_api 의 공개 속성을 전부 JS 로 노출하려 하는데, 창 객체를 노출하면 무한 순회 오류가 수천 줄 찍힌다

    #윈도우 폴더 선택창 → {"path": 고른 폴더}. 취소하면 None. 프런트가 이 경로로 /projects/from_folder 를 부른다
    def pick_folder(self):
        picked = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not picked:
            return None
        return {"path": picked[0]}


def loading_html(url):
    # 서버가 /models 에 답할 때까지 1초마다 확인하고, 되면 앱으로 이동
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{APP_NAME}</title>
<style>
  html,body{{height:100%;margin:0;font-family:Segoe UI,system-ui,sans-serif;background:#0a1033;color:#fff}}
  .c{{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}}
  .dot{{width:10px;height:10px;border-radius:50%;background:#f2760a;animation:b 1s infinite alternate}}
  @keyframes b{{to{{opacity:.2}}}}
  small{{color:#9aa4d6}}
</style></head><body><div class="c">
  <div class="dot"></div><div>Loading models...</div><small>first start can take a while</small>
</div>
<script>
  const url = {url!r};
  const tick = () => fetch(url + "/models").then(r => {{ if (r.ok) location.href = url; else setTimeout(tick, 1000); }}).catch(() => setTimeout(tick, 1000));
  setTimeout(tick, 1500);
</script></body></html>"""


def main():
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    api = Api()
    api._window = webview.create_window(APP_NAME, html=loading_html(url), js_api=api, width=1400, height=900, min_size=(900, 600))
    webview.start()
    sys.exit(0)  # 창을 닫으면 서버 스레드(daemon)도 같이 끝난다


if __name__ == "__main__":
    main()
