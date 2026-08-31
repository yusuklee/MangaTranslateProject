import warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
from huggingface_hub import hf_hub_download
from rfdetr import RFDETRSeg2XLarge
from safetensors.torch import load_file
from PIL import Image
import numpy as np
from dotenv import load_dotenv
from pathlib import Path
load_dotenv()
import re
HAS_TEXT = re.compile(r'[ぁ-んァ-ヶ一-龯0-9A-Za-z]')
from manga_ocr import MangaOcr
mocr = MangaOcr()


PROMPT = """You are a professional manga translator.

  Translation requirements:
  - Translate every input segment from Japanese into natural Korean.
  - Preserve meaning, character voice, emotional tone, relationship nuance, emphasis, and sound effects.
  - Localize idioms and sound effects naturally while keeping wording concise enough for speech bubbles.
  - Use surrounding segments only for disambiguation and continuity; never merge or split segments.
  - Write every translated `text` value only in Korean; do not include source text, notes, explanations, or alternatives.
  - Never preserve or repeat original-language text; translate names, terms, and sound effects using natural Korean
  conventions.

  Output requirements:
  - Each input segment has a numeric `id`.
  - Return only a JSON object whose `translations` array contains one object with `id` and translated `text` for every input
  segment.
  - Copy every input ID exactly once; order does not matter.
  - Never merge, split, omit, duplicate, or add segments."""

repo = "mayocream/koharu-layout-rfdetr-seg-2xl-1152"
params = hf_hub_download(repo,"model.safetensors")
model = RFDETRSeg2XLarge(pretrain_weights=None, resolution=1152,
                         num_select =160, num_classes=4)
model.model.model.load_state_dict(load_file(params,device="cpu"), strict=True)
model.model.class_names=["text", "onomatopoeia","bubble","panel"]


def draw_dashed_rect(draw, box, color=(0, 100, 255), dash=6, gap=4, width=2):  #파란색 점선 그리는 코드
    x1, y1, x2, y2 = box
    for edge in [(x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)]:
        ex1, ey1, ex2, ey2 = edge
        length = max(abs(ex2 - ex1), abs(ey2 - ey1))
        steps = int(length // (dash + gap)) + 1
        for i in range(steps):
            t0 = i * (dash + gap)
            t1 = t0 + dash
            frac0, frac1 = t0 / length, min(t1 / length, 1)
            sx = ex1 + (ex2 - ex1) * frac0
            sy = ey1 + (ey2 - ey1) * frac0
            ex = ex1 + (ex2 - ex1) * frac1
            ey = ey1 + (ey2 - ey1) * frac1
            draw.line([(sx, sy), (ex, ey)], fill=color, width=width)



#탐지한 말풍선들에 파란점선 + d를 저장
def detect_file(file):
    from PIL import ImageDraw, ImageFont
    word_id = 0
    page = 1
    lines = []
    image = file.convert('RGB')
    d = model.predict(image)
    image2 = image.copy()
    draw = ImageDraw.Draw(image2)
    for (x1,y1,x2,y2), name in zip(d.xyxy, d.data["class_name"]):
        if name=="text":
            crop = image.crop((int(x1), int(y1), int(x2), int(y2)))
            word = mocr(crop)
            if word.strip() and HAS_TEXT.search(word):
                lines.append({"id":word_id,"pos": (int(x1), int(y1), int(x2), int(y2)), "word":word, "page":page})
                word_id+=1
        if name=="bubble":
            draw.rectangle((int(x1), int(y1), int(x2), int(y2)), outline=(0, 100, 255), width=10)
    page+=1
    lines.sort(key=lambda t: (t["page"], t["pos"][1], -t["pos"][2]))

    return lines, image2


def ocr_file(lines):
    pass


