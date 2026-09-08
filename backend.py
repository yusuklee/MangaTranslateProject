from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io, base64, json
from Process.detect import detect_file
from Process.translate import translate_lines
from Process.inpaint import inpaint_lama

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/detect")
async def detect(file:UploadFile):
    image = Image.open(io.BytesIO(await file.read()))
    return detect_file(image)


@app.post("/translate")
async def translate(lines: list[dict]):
  return translate_lines(lines)


@app.post("/inpaint")
async def inpaint(file: UploadFile, contents: str = Form(...)):
    image = Image.open(io.BytesIO(await file.read()))
    out = inpaint_lama(image, json.loads(contents))
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return {"image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}
