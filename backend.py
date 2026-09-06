from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io, base64
from Process.detect import detect_file
from Process.translate import translate_lines

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/detect")
async def detect(file:UploadFile):
    image = Image.open(io.BytesIO(await file.read()))
    return detect_file(image)


@app.post("/translate")
async def translate(lines: list[dict]):
  return translate_lines(lines)
