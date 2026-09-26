import warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import os, re, base64, io
import numpy as np
import cv2
from PIL import Image
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from rfdetr import RFDETRSeg2XLarge
from manga_ocr import MangaOcr
from manga_ocr.ocr import post_process

load_dotenv()

HAS_TEXT = re.compile(r'[ぁ-んァ-ヶ一-龯가-힣0-9A-Za-z]')

mocr = MangaOcr()  #ocr
model = RFDETRSeg2XLarge(pretrain_weights=None, resolution=1152, num_select=160, num_classes=4)      #detect model
model.model.model.load_state_dict(
    load_file(hf_hub_download("mayocream/koharu-layout-rfdetr-seg-2xl-1152", "model.safetensors"), device="cpu"),
    strict=True,
)

model.model.class_names = ["text", "onomatopoeia", "bubble", "panel"]



#조각들을 한 묶음으로 넣어 OCR 1번에 처리
def ocr_batch(crops, batch=32):
    words = []
    for i in range(0, len(crops), batch):
        imgs = [img.convert("L").convert("RGB") for img in crops[i:i + batch]]
        x = mocr.processor(imgs, return_tensors="pt").pixel_values
        tokens = mocr.model.generate(x.to(mocr.model.device), max_length=300)
        words += [post_process(mocr.tokenizer.decode(t, skip_special_tokens=True)) for t in tokens]
    return words



def detect_ocr_page(file, classes=("text",)):
    image = file.convert("RGB")
    arr = np.array(image)

    d = model.predict(image)
    xyxy, names = d.xyxy, d.data["class_name"]
    text_boxes = [tuple(max(0,int(v)) for v in b) for b, n in zip(xyxy, names) if n in classes]
    bubbles = [tuple(max(0,int(v)) for v in b) for b, n in zip(xyxy, names) if n == "bubble"]

    prob, line_map = get_word_line_maps(image)
    page_mask = filter_expand_ctd_mask(prob)
    ink = (np.array(image.convert("L")) < 100) & page_mask       # 실제 잉크 픽셀 (줄 나누기용)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(page_mask.astype(np.uint8))
    bbox = {i: (int(x), int(y), int(x + w), int(y + h)) for i, (x, y, w, h, a) in enumerate(stats) if i > 0}
    erase_boxes = [expand_RF(labels, bbox, b) for b in text_boxes]

    #긴 상자는 줄 조각으로 나누고, 조각 전부를 한 번에 OCR 한 뒤 상자별로 이어 붙인다
    pieces = [put_detect_box2ocr(line_map, ink, b) for b in text_boxes]
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

def assign_bubbles(boxes, bubbles):
    def owner(box):
        cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
        hit = [b for b in bubbles if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]]
        return min(hit, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])) if hit else None
    owners = [owner(b) for b in boxes]
    shared = {b for b in owners if b is not None and owners.count(b) > 1}
    return [None if b in shared else b for b in owners]


def expand_RF(labels, bbox, box):
    x1, y1, x2, y2 = box
    for i in set(np.unique(labels[y1:y2, x1:x2])) - {0}:
        bx1, by1, bx2, by2 = bbox[i]
        x1, y1, x2, y2 = min(x1, bx1), min(y1, by1), max(x2, bx2), max(y2, by2)
    return (x1, y1, x2, y2)


# DEF of text masks(for cutting box and accurate inpainting)  ctd model returns separate lines and word masks by prob

CTD_MODEL = os.environ.get("CTD_MODEL", "comictextdetector.pt.onnx")
CTD_SIZE = 1024
BINARY_THRESHOLD = 60 / 255
CLOSE_RADIUS = 10
DILATE_RADIUS = 3

_ctd = None
def get_ctd():
    global _ctd
    if _ctd is None:
        import torch
        import onnxruntime as ort
        path = CTD_MODEL
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), CTD_MODEL)
        _ctd = ort.InferenceSession(path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    return _ctd



def get_word_line_maps(image):
    W, H = image.size
    s = CTD_SIZE / max(W, H)
    rw, rh = round(W * s), round(H * s)

    canvas = np.zeros((CTD_SIZE, CTD_SIZE, 3), np.uint8)
    canvas[:rh, :rw] = np.array(image.convert("RGB").resize((rw, rh)))
    inp = canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255.0

    _, word, line = get_ctd().run(None, {"images": inp})
    up = lambda m: cv2.resize(m[:rh, :rw], (W, H), interpolation=cv2.INTER_LINEAR)
    return up(word[0, 0]), up(line[0, 0])




def square(r):
    return np.ones((2 * r + 1, 2 * r + 1), np.uint8)



def filter_expand_ctd_mask(ctd_mask):
    m = (ctd_mask >= BINARY_THRESHOLD).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, square(CLOSE_RADIUS))
    return cv2.dilate(m, square(DILATE_RADIUS)) > 0


def mask_to_text(mask_box):
    buf = io.BytesIO()
    Image.fromarray(mask_box.astype(np.uint8)*255).save(buf,format="PNG")
    return base64.b64encode(buf.getvalue()).decode()



#DEF of cutting box (for ocr) by lines

SPLIT_LIMIT = 448        # 긴 변이 이보다 크면 나눈다 (224 의 2배까지는 manga-ocr 이 버팀)
LINE_THRESHOLD = 0.5
MIN_LINE_AREA = 50       # 이보다 작은 심지는 잡음


def length(box):
    return max(box[2] - box[0], box[3] - box[1])


def thickness(box):
    return min(box[2] - box[0], box[3] - box[1])



#상자가 클떄 상자를 여러개로 쪼개서 돌려주는 함수
def cut_box(line_map, ink, box): #ink 는 줄 마스크  영역
    x1, y1, x2, y2 = box
    box_and_lines = (line_map[y1:y2, x1:x2] >= LINE_THRESHOLD).astype(np.uint8)
    _, _, st, _ = cv2.connectedComponentsWithStats(box_and_lines)
    cut_lines = [(int(x), int(y), int(x + w), int(y + h)) for x, y, w, h, a in st[1:] if a >= MIN_LINE_AREA]
    if not cut_lines:
        return []

    sub_ink = ink[y1:y2, x1:x2]
    W, H = x2 - x1, y2 - y1
    out = []
    for cx1, cy1, cx2, cy2 in cut_lines:
        vertical = (cy2 - cy1) > (cx2 - cx1)  #세로 줄이라고 판단
        thick = (cx2 - cx1) if vertical else (cy2 - cy1)
        if vertical:
            lo, hi = 0, W                                   # 가로 한계: 옆 심지와의 중간
            for ox1, oy1, ox2, oy2 in cut_lines:
                if (ox1, oy1, ox2, oy2) == (cx1, cy1, cx2, cy2) or oy1 >= cy2 or oy2 <= cy1:
                    continue
                if ox2 <= cx1:
                    lo = max(lo, (ox2 + cx1) // 2)
                elif ox1 >= cx2:
                    hi = min(hi, (ox1 + cx2) // 2)
            win = sub_ink[max(0, cy1 - thick):min(H, cy2 + thick), lo:hi]
            ox, oy = lo, max(0, cy1 - thick)
        else:
            lo, hi = 0, H
            for ox1, oy1, ox2, oy2 in cut_lines:
                if (ox1, oy1, ox2, oy2) == (cx1, cy1, cx2, cy2) or ox1 >= cx2 or ox2 <= cx1:
                    continue
                if oy2 <= cy1:
                    lo = max(lo, (oy2 + cy1) // 2)
                elif oy1 >= cy2:
                    hi = min(hi, (oy1 + cy2) // 2)
            win = sub_ink[lo:hi, max(0, cx1 - thick):min(W, cx2 + thick)]
            ox, oy = max(0, cx1 - thick), lo
        ys, xs = np.nonzero(win)
        if xs.size == 0:
            out.append((x1 + cx1, y1 + cy1, x1 + cx2, y1 + cy2))
        else:
            out.append((x1 + ox + int(xs.min()), y1 + oy + int(ys.min()),
                        x1 + ox + int(xs.max()) + 1, y1 + oy + int(ys.max()) + 1))
    return out


#줄 상자들을 읽는 순서로 (재귀 XY-cut). 위아래로 갈리면 위 → 아래, 좌우로 갈리면 오른쪽 → 왼쪽 (세로쓰기)
def reading_order(boxes):
    if len(boxes) <= 1:
        return list(boxes)
    for axis, first in ((1, "top"), (0, "right")):
        lo, hi = axis, axis + 2
        order = sorted(boxes, key=lambda b: b[lo])
        end = order[0][hi]
        for k in range(1, len(order)):
            if order[k][lo] >= end:                       # 여기서 틈이 생김
                a, b = order[:k], order[k:]
                if first == "right":
                    a, b = b, a
                return reading_order(a) + reading_order(b)
            end = max(end, order[k][hi])
    #겹쳐서 못 가르면: 세로줄이 많으면 오른쪽부터, 아니면 위부터
    vertical = sum((b[3] - b[1]) > (b[2] - b[0]) for b in boxes) * 2 > len(boxes)
    return sorted(boxes, key=(lambda b: -b[2]) if vertical else (lambda b: b[1]))


#한 줄이 아직도 길면 글자 사이 빈틈(잉크 없는 행/열)에서 나눈다. 가운데 근처에서 가장 넓은 틈을 고른다
def split_long_line(ink, box, limit=SPLIT_LIMIT):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if max(w, h) <= limit:
        return [box]
    vertical = h > w
    profile = ink[y1:y2, x1:x2].sum(1 if vertical else 0)
    n = len(profile)
    lo, hi = int(n * 0.3), int(n * 0.7)          # 가운데 40% 구간에서만 자른다 (조각 크기 균형)
    best, best_w, i = None, 0, lo
    while i < hi:
        if profile[i] == 0:
            j = i
            while j < n and profile[j] == 0:
                j += 1
            if j - i > best_w:
                best, best_w = (i + j) // 2, j - i
            i = j
        else:
            i += 1
    if best is None:
        return [box]
    if vertical:
        a, b = (x1, y1, x2, y1 + best), (x1, y1 + best, x2, y2)
    else:
        a, b = (x1, y1, x1 + best, y2), (x1 + best, y1, x2, y2)
    return split_long_line(ink, a, limit) + split_long_line(ink, b, limit)



def put_detect_box2ocr(line_map, ink, box, limit=SPLIT_LIMIT):
    if length(box) <= limit:
        return [box]
    lines = reading_order(cut_box(line_map, ink, box))
    if not lines:
        return [box]
    return [piece for line in lines for piece in split_long_line(ink, line, limit)]


def font_size(line_map, ink, box):
    lines = cut_box(line_map, ink, box)
    return int(np.median([thickness(l) for l in lines])) if lines else thickness(box)
