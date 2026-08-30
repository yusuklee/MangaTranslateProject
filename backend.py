from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io, base64
from Process.detect import detect_file


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/detect")
async def detect(file:UploadFile):
    image = Image.open(io.BytesIO(await file.read()))
    lines, detected_img = detect_file(image)

    buf = io.BytesIO()
    detected_img.save(buf,format="PNG")
    preview = base64.b64encode(buf.getvalue()).decode()

    return {"lines": lines, "detected_img": f"data:image/png;base64,{preview}"}
