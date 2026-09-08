import warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import re, base64, io
import numpy as np
from PIL import Image
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from rfdetr import RFDETRSeg2XLarge
from manga_ocr import MangaOcr

load_dotenv()

HAS_TEXT = re.compile(r'[ぁ-んァ-ヶ一-龯0-9A-Za-z]')
mocr = MangaOcr()

repo = "mayocream/koharu-layout-rfdetr-seg-2xl-1152"
params = hf_hub_download(repo, "model.safetensors")
model = RFDETRSeg2XLarge(pretrain_weights=None, resolution=1152,
                         num_select=160, num_classes=4)
model.model.model.load_state_dict(load_file(params, device="cpu"), strict=True)
model.model.class_names = ["text", "onomatopoeia", "bubble", "panel"]


#d.mask(전체 이미지 크기 True/False)에서 상자 부분만 잘라 base64 PNG로 만든다
def encode_mask(mask_bool):
    img = Image.fromarray(mask_bool.astype(np.uint8) * 255)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


#페이지 이미지에서 text 상자를 찾아 OCR과 마스크를 붙여 돌려준다
def detect_file(file):
    word_id = 0
    page = 1
    lines = []
    image = file.convert('RGB')
    d = model.predict(image)

    for i, ((x1, y1, x2, y2), name) in enumerate(zip(d.xyxy, d.data["class_name"])):
        if name != "text":
            continue
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        crop = image.crop((x1, y1, x2, y2))
        word = mocr(crop)
        if word.strip() and HAS_TEXT.search(word):
            mask_crop = d.mask[i][y1:y2, x1:x2]   # 상자 안에서 실제 글자인 픽셀만 True
            lines.append({
                "id": word_id,
                "pos": (x1, y1, x2, y2),
                "word": word,
                "page": page,
                "mask": encode_mask(mask_crop),
            })
            word_id += 1

    lines.sort(key=lambda t: (t["page"], t["pos"][1], -t["pos"][2]))
    return lines
