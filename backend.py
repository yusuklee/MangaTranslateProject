from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
import io, os, base64, json
from Process.detect import detect_file
from Process.translate import translate_lines
from Process.inpaint_normal import inpaint_white
from Process.inpaint_lama import inpaint_lama
from Process.inpaint_flux import inpaint_flux
from Process.fonts import list_korean_fonts, FONTS_DIR

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def to_data_url(out):
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return {"image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}


#상자 찾기 + OCR (+ 마스크, 말풍선, 글자 크기·색)
@app.post("/detect")
async def detect(file: UploadFile):
    return detect_file(Image.open(io.BytesIO(await file.read())))


#일반 def → FastAPI 가 스레드에서 돌림. Gemini 응답을 기다리는 동안 inpaint 요청이 같이 처리됨
@app.post("/translate")
def translate(lines: list[dict]):
    return translate_lines(lines)


#글자 자리만 흰색으로 (모델 없음)
@app.post("/inpaint_normal")
async def inpaint_normal_route(file: UploadFile, contents: str = Form(...)):
    return to_data_url(inpaint_white(Image.open(io.BytesIO(await file.read())), json.loads(contents)))


#LaMa
@app.post("/inpaint_lama")
async def inpaint_lama_route(file: UploadFile, contents: str = Form(...)):
    return to_data_url(inpaint_lama(Image.open(io.BytesIO(await file.read())), json.loads(contents)))


#FLUX2 (프롬프트로 지운 뒤 마스크 자리만 덮어씀). 8bit 압축본 flux2-klein-8bit/ 필요
@app.post("/inpaint_flux")
async def inpaint_flux_route(file: UploadFile, contents: str = Form(...)):
    return to_data_url(inpaint_flux(Image.open(io.BytesIO(await file.read())), json.loads(contents)))


#렌더용 폰트: koharu 내장 Google Fonts 중 한글 되는 것. 파일은 /fontfiles/<상대경로> 로 그대로 내보낸다
if os.path.isdir(FONTS_DIR):
    app.mount("/fontfiles", StaticFiles(directory=FONTS_DIR), name="fontfiles")

@app.get("/fonts")
def fonts():
    return list_korean_fonts() if os.path.isdir(FONTS_DIR) else []
