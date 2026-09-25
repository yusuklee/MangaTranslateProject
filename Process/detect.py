import warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import re, base64, io
import numpy as np
import cv2
from PIL import Image
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from rfdetr import RFDETRSeg2XLarge
from manga_ocr import MangaOcr
from manga_ocr.ocr import post_process
from Process.textmask import ctd_maps, koharu_mask
from Process.textlines import split_box, font_size

load_dotenv()

HAS_TEXT = re.compile(r'[ぁ-んァ-ヶ一-龯가-힣0-9A-Za-z]')

mocr = MangaOcr()
model = RFDETRSeg2XLarge(pretrain_weights=None, resolution=1152, num_select=160, num_classes=4)
model.model.model.load_state_dict(
    load_file(hf_hub_download("mayocream/koharu-layout-rfdetr-seg-2xl-1152", "model.safetensors"), device="cpu"),
    strict=True,
)

model.model.class_names = ["text", "onomatopoeia", "bubble", "panel"]


#mask-> 프런트에 저장할 텍스트로
def mask_to_text(mask_box):
    buf = io.BytesIO()
    Image.fromarray(mask_box.astype(np.uint8)*255).save(buf,format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


#조각들을 한 묶음으로 넣어 OCR 1번에 처리
def ocr_batch(crops, batch=32):
    words = []
    for i in range(0, len(crops), batch):
        imgs = [img.convert("L").convert("RGB") for img in crops[i:i + batch]]
        x = mocr.processor(imgs, return_tensors="pt").pixel_values
        tokens = mocr.model.generate(x.to(mocr.model.device), max_length=300)
        words += [post_process(mocr.tokenizer.decode(t, skip_special_tokens=True)) for t in tokens]
    return words


#지우기용 상자: RF-DETR 상자를 ctd 획 덩어리에 맞게 넓힌 것 (상자 경계에서 획이 잘리면 LaMa 결과에 줄무늬가 생김)
def erase_box(labels, bbox, box):
    x1, y1, x2, y2 = box
    for i in set(np.unique(labels[y1:y2, x1:x2])) - {0}:
        bx1, by1, bx2, by2 = bbox[i]
        x1, y1, x2, y2 = min(x1, bx1), min(y1, by1), max(x2, bx2), max(y2, by2)
    return (x1, y1, x2, y2)



def assign_bubbles(boxes, bubbles):
    def owner(box):
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        hit = [b for b in bubbles if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]]
        return min(hit, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if hit else None
    owners = [owner(b) for b in boxes]
    shared = {b for b in owners if b is not None and owners.count(b) > 1}
    return [None if b in shared else b for b in owners]



def text_colors(arr, page_mask, box):
    x1, y1, x2, y2 = box
    crop, m = arr[y1:y2, x1:x2], page_mask[y1:y2, x1:x2]
    if m.sum() < 20 or (~m).sum() < 20:
        return "#000000", None
    lum = lambda c: 0.299 * c[..., 0] + 0.587 * c[..., 1] + 0.114 * c[..., 2]
    px = crop[m].astype(np.float32)
    l = lum(px)
    dark = np.median(px[l <= np.percentile(l, 30)], axis=0)
    light = np.median(px[l >= np.percentile(l, 70)], axis=0)
    bg = np.median(crop[~m].astype(np.float32), axis=0)
    fg = dark if abs(lum(dark) - lum(bg)) >= abs(lum(light) - lum(bg)) else light
    return ("#ffffff", "#000000") if lum(fg) > lum(bg) else ("#000000", None)



def detect_file(file, classes=("text",)):
    image = file.convert("RGB")
    arr = np.array(image)

    d = model.predict(image)
    xyxy, names = d.xyxy, d.data["class_name"]
    text_boxes = [tuple(max(0,int(v)) for v in b) for b, n in zip(xyxy, names) if n in classes]
    bubbles = [tuple(max(0,int(v)) for v in b) for b, n in zip(xyxy, names) if n == "bubble"]

    prob, line_map = ctd_maps(image)
    page_mask = koharu_mask(prob)
    ink = (np.array(image.convert("L")) < 100) & page_mask       # 실제 잉크 픽셀 (줄 나누기용)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(page_mask.astype(np.uint8))
    bbox = {i: (int(x), int(y), int(x + w), int(y + h)) for i, (x, y, w, h, a) in enumerate(stats) if i > 0}
    erase_boxes = [erase_box(labels, bbox, b) for b in text_boxes]

    #긴 상자는 줄 조각으로 나누고, 조각 전부를 한 번에 OCR 한 뒤 상자별로 이어 붙인다
    pieces = [split_box(line_map, ink, b) for b in text_boxes]
    flat = ocr_batch([image.crop(p) for ps in pieces for p in ps])
    words, k = [], 0
    for ps in pieces:
        words.append("".join(flat[k:k + len(ps)]))
        k += len(ps)

    lines = []
    for pos, erase, word, bub in zip(text_boxes, erase_boxes, words, assign_bubbles(text_boxes, bubbles)):
        if not word.strip() or not HAS_TEXT.search(word):
            continue
        ex1, ey1, ex2, ey2 = erase
        color, stroke = text_colors(arr, page_mask, erase)
        lines.append({
            "pos": pos,
            "mask_area": erase,
            "word": word,
            "page": 1,
            "mask": mask_to_text(page_mask[ey1:ey2, ex1:ex2]),
            "bubble": bub,
            "font_size": font_size(line_map, ink, pos),
            "color": color,
            "stroke": stroke,
        })

    lines.sort(key=lambda t: (t["pos"][1], -t["pos"][2]))   # 위에서 아래, 같은 높이면 오른쪽부터
    for i, t in enumerate(lines):
        t["id"] = i
    return lines
