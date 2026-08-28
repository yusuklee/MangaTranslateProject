import warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
from huggingface_hub import hf_hub_download
from rfdetr import RFDETRSeg2XLarge
from safetensors.torch import load_file
from PIL import Image
import numpy as np
from dotenv import load_dotenv
load_dotenv()

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



#이미지 가져오기
image = Image.open("images/4-Koma_EP1.webp").convert('RGB')



# 1 DETECT
repo = "mayocream/koharu-layout-rfdetr-seg-2xl-1152"
params = hf_hub_download(repo,"model.safetensors")
model = RFDETRSeg2XLarge(pretrain_weights=None, resolution=1152,
                         num_select =160, num_classes=4)
model.model.model.load_state_dict(load_file(params,device="cpu"), strict=True)
model.model.class_names=["text", "onomatopoeia","bubble","panel"]

d = model.predict(image)
print("detect comp")

# 2 OCR

import re
HAS_TEXT = re.compile(r'[ぁ-んァ-ヶ一-龯0-9A-Za-z]')
from manga_ocr import MangaOcr
mocr = MangaOcr()
word_id=0
lines = []
for (x1,y1,x2,y2), name in zip(d.xyxy, d.data["class_name"]):
    if name=="text":
        crop = image.crop((int(x1), int(y1), int(x2), int(y2)))
        word = mocr(crop)
        if word.strip() and HAS_TEXT.search(word):
            lines.append({"id":word_id,"pos": (int(x1), int(y1), int(x2), int(y2)), "word":word})
            word_id+=1
lines.sort(key=lambda t:(t["pos"][1], -t["pos"][2]) )

print("ocr comp")

import os, json
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

payload = {
    "source_language":"Japanese",
    "target_language":"Korean",
    "context":[],
    "segments":[{"id":t["id"], "text":t["word"]} for t in lines]
}

resp = client.models.generate_content(
    model="gemini-3.5-flash",
    contents = json.dumps(payload, ensure_ascii=False),
    config=types.GenerateContentConfig(
        system_instruction=PROMPT,
        response_mime_type = "application/json"
    )
)


data=json.loads(resp.text)

#lines 에서 번역문으로 교체하는 작업
ko = {r["id"]:r["text"] for r in data["translations"]}
for t in lines:
    if t["id"] in ko.keys():
        t["word"] = ko[t["id"]]

print("translate comp")




# 3 INPAINT
#d.xyxy 말풍선을 감싸는 직사각형 좌상단, 우상단
#d.mask 말풍선의 실제모양 픽셀 하나하나 True/False

out = np.array(image)
# for  name, masks in zip( d.data["class_name"], d.mask):
#     if name=="bubble":
#         out[masks]=255


from PIL import ImageDraw, ImageFont

FONT_PATH = "C:/Windows/Fonts/malgunbd.ttf"
canvas = Image.fromarray(out)
draw = ImageDraw.Draw(canvas)

for t in lines:
      x1, y1, x2, y2 = t["pos"]
      out[y1:y2, x1:x2] = 255
      draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255))  # 흰색으로 지우고

      box_w, box_h = x2 - x1, y2 - y1
      for size in range(40, 8, -1):
          font = ImageFont.truetype(FONT_PATH, size)
          rows, cur = [], ""
          for ch in t["word"]:
              if draw.textlength(cur + ch, font=font) <= box_w or not cur:
                  cur += ch
              else:
                  rows.append(cur)
                  cur = ch
          rows.append(cur)
          if len(rows) * (size + 4) <= box_h:
              break

      y = y1 + (box_h - len(rows) * (size + 4)) // 2
      for row in rows:  # 바로 글씨 그리기
          w = draw.textlength(row, font=font)
          draw.text((x1 + (box_w - w) // 2, y), row, font=font, fill=(0, 0, 0))
          y += size + 4

print("render comp")



canvas.save("results/4-Koma_EP1_translated.png")








