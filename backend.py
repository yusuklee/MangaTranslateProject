from fastapi import FastAPI, UploadFile, Form, Response, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
import io, os, json
from Process.detect import detect_file
from Process.translate import translate_lines, list_models, MODEL as DEFAULT_MODEL
from Process.inpaint_normal import inpaint_white
from Process.inpaint_lama import inpaint_lama
from Process.fonts import list_korean_fonts, FONTS_DIR
from google.genai import errors as genai_errors

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


#인페인팅 결과는 PNG 바이트 그대로 보낸다 (base64 JSON 보다 1/3 작고, 프런트가 디코드할 필요 없음)
def png_response(out):
    buf = io.BytesIO()
    out.save(buf, format="PNG", compress_level=1)   # 압축 낮게 = 빠르게. 브라우저로 가는 임시 결과라 용량보다 속도
    return Response(buf.getvalue(), media_type="image/png")


#상자 찾기 + OCR (+ 마스크, 말풍선, 글자 크기·색)
#classes: "text" 또는 "text,onomatopoeia" (설정의 Detect 항목). 한 번의 RF-DETR 로 둘 다 나오니 종류만 고른다
@app.post("/detect")
async def detect(file: UploadFile, classes: str = Form("text")):
    wanted = tuple(c.strip() for c in classes.split(",") if c.strip()) or ("text",)
    return detect_file(Image.open(io.BytesIO(await file.read())), wanted)


#일반 def → FastAPI 가 스레드에서 돌림. Gemini 응답을 기다리는 동안 inpaint 요청이 같이 처리됨
#body: {"lines": [{id, word}], "source": "Japanese", "target": "Korean", "model": "gemini-3.6-flash"}
#Gemini 키는 X-Gemini-Key 헤더로 (설정 창에서 입력한 사용자 키). 없으면 서버 .env 키. 둘 다 없으면 400
@app.post("/translate")
def translate(body: dict, x_gemini_key: str | None = Header(default=None)):
    try:
        return translate_lines(body["lines"], body.get("source", "Japanese"), body.get("target", "Korean"), body.get("model") or None, x_gemini_key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except genai_errors.APIError as e:   # 키가 틀리거나(400/403) 한도(429) 등 Gemini 쪽 오류 → 그 코드와 메시지를 그대로
        raise HTTPException(e.code if 400 <= (e.code or 0) < 600 else 502, f"Gemini: {e.message}")


#설정 창의 모델 목록 + 기본값. 키가 틀리면 Gemini 오류 코드를 그대로 돌려준다
@app.get("/gemini_models")
def gemini_models(x_gemini_key: str | None = Header(default=None)):
    try:
        return {"models": list_models(x_gemini_key), "default": DEFAULT_MODEL}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except genai_errors.APIError as e:
        raise HTTPException(e.code if 400 <= (e.code or 0) < 600 else 502, f"Gemini: {e.message}")


#글자 자리만 흰색으로 (모델 없음)
@app.post("/inpaint_normal")
async def inpaint_normal_route(file: UploadFile, contents: str = Form(...)):
    return png_response(inpaint_white(Image.open(io.BytesIO(await file.read())), json.loads(contents)))


#LaMa
@app.post("/inpaint_lama")
async def inpaint_lama_route(file: UploadFile, contents: str = Form(...)):
    return png_response(inpaint_lama(Image.open(io.BytesIO(await file.read())), json.loads(contents)))


#FLUX2 (프롬프트로 지운 뒤 마스크 자리만 덮어씀). 8bit 압축본 flux2-klein-8bit/ 필요
#torch·diffusers 가 있는 설치에서만 된다. 여기서 늦게 import 해서 없는 빌드에서도 서버는 뜨게 한다
@app.post("/inpaint_flux")
async def inpaint_flux_route(file: UploadFile, contents: str = Form(...)):
    try:
        from Process.inpaint_flux import inpaint_flux
        import torch, diffusers  # noqa: F401
    except ImportError:
        raise HTTPException(501, "FLUX is not available in this build")
    return png_response(inpaint_flux(Image.open(io.BytesIO(await file.read())), json.loads(contents)))


#데스크톱 앱 내보내기: 프런트가 캔버스로 그린 PNG 를 폴더 경로와 함께 보내면 그 폴더에 쓴다.
#브라우저의 폴더 쓰기 API(showDirectoryPicker)는 "127.0.0.1 이 파일을 수정하도록 허용?" 창을 띄우므로, 앱에서는 이 길로 간다
@app.post("/export")
async def export_file(file: UploadFile, folder: str = Form(...), name: str = Form(...)):
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise HTTPException(400, "folder not found")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "bad file name")
    with open(os.path.join(folder, name), "wb") as f:
        f.write(await file.read())
    return {"ok": True}


#어떤 모델이 메모리에 올라와 있는지. detect 모델(RF-DETR·OCR)은 서버 시작 때 올라오니 응답이 오면 이미 준비된 것.
#LaMa·FLUX 는 처음 쓸 때 올라온다. 프런트가 "모델 불러오는 중" 표시에 쓴다
@app.get("/models")
def models():
    import importlib.util
    from Process import inpaint_lama as L
    #inpaint_flux 는 torch·diffusers 를 함수 안에서 늦게 import 하므로 모듈 import 성공으로는 판단이 안 된다 → 패키지 존재로 판정
    flux_available = all(importlib.util.find_spec(m) is not None for m in ("torch", "diffusers"))
    flux = False
    if flux_available:
        from Process import inpaint_flux as F
        flux = F._flux2 is not None
    return {"lama": L._lama is not None, "flux": flux, "flux_available": flux_available}


#렌더용 폰트: koharu 내장 Google Fonts 중 한글 되는 것. 파일은 /fontfiles/<상대경로> 로 그대로 내보낸다
if os.path.isdir(FONTS_DIR):
    app.mount("/fontfiles", StaticFiles(directory=FONTS_DIR), name="fontfiles")

@app.get("/fonts")
def fonts():
    return list_korean_fonts() if os.path.isdir(FONTS_DIR) else []


#프로젝트 저장 (코하루식 디스크 저장): /projects/... — Process/projects.py
from Process.projects import router as projects_router
app.include_router(projects_router)


#데스크톱 앱: 빌드된 프런트(frontend/dist)를 / 에서 직접 서빙. API 경로들 뒤에 두어야 /detect 같은 게 먼저 잡힌다
#PyInstaller 로 묶이면 sys._MEIPASS(임시 풀림 폴더) 아래에 있다
def resource_dir():
    import sys
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

FRONTEND_DIST = os.path.join(resource_dir(), "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
