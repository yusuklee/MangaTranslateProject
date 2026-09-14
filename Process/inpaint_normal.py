import base64, io
import numpy as np
import cv2
from PIL import Image
from dotenv import load_dotenv
from Process.textmask import square
load_dotenv()

#글자 지우기 공통 부분. 마스크는 detect 가 만든 koharu 방식 글자 획 마스크(contents["mask"])를 쓰고,
#여기서는 인페인팅 직전 팽창(글자 크기 기준 2~8px)만 더한다. 단색 배경은 모델 없이 바로 채운다.
#inpaint_lama / inpaint_flux 는 여기의 prepare_jobs → run_model_merged 에 자기 모델 호출만 끼운다.

TILE = 512      # 한 번에 지울 조각의 최대 한 변
CTX = 128       # 조각 사방에 붙여 모델에 보여줄 배경

FONT_RATIO = 0.16         # koharu 0.61.2 LEGACY_BLOCK_DILATE_FONT_RATIO
MIN_R, MAX_R = 2, 8       # LEGACY_MIN/MAX_DILATE_RADIUS

MIN_PIXELS = 16
margin1 = 4     # 상자에서 이만큼 밖까지는 글자 번짐이라 버린다
margin2 = 3     # 그 바깥으로 이만큼이 색을 잴 고리


#base64 PNG → bool 배열
def decode_mask(mask_b64):
    return np.array(Image.open(io.BytesIO(base64.b64decode(mask_b64)))) > 127


#인페인팅 직전 팽창 반지름. 글자 크기(상자의 짧은 변으로 대신) × 0.16, 2~8px
def block_radius(box):
    x1, y1, x2, y2 = box
    return int(np.clip(round(min(x2 - x1, y2 - y1) * FONT_RATIO), MIN_R, MAX_R))


#상자마다 (r 만큼 넓힌 상자, 그 안의 글자 마스크) 목록
def box_masks(image, contents):
    W, H = image.size
    out = []
    for c in contents:
        x1, y1, x2, y2 = map(int, c.get("erase") or c["pos"])
        r = block_radius((x1, y1, x2, y2))
        ex1, ey1, ex2, ey2 = max(0, x1 - r), max(0, y1 - r), min(W, x2 + r), min(H, y2 + r)
        page = np.zeros((H, W), np.uint8)
        page[y1:y2, x1:x2] = decode_mask(c["mask"]) if c.get("mask") else 1   # 마스크 없으면 상자 전체
        text_mask = cv2.dilate(page[ey1:ey2, ex1:ex2], square(r)) > 0
        out.append(((ex1, ey1, ex2, ey2), text_mask))
    return out


#상자 둘레 고리 + 상자 안 배경 픽셀이 단색이면 그 색, 아니면 None
def uniform_color(arr, box, text_mask):
    x1, y1, x2, y2 = box
    h, w = arr.shape[:2]

    ring = np.zeros(arr.shape[:2], bool)
    ring[max(y1 - margin1, 0):min(y2 + margin1, h), max(x1 - margin1, 0):min(x2 + margin1, w)] = True
    ring[max(y1 - margin2, 0):min(y2 + margin2, h), max(x1 - margin2, 0):min(x2 + margin2, w)] = False

    inside_bg = np.zeros(arr.shape[:2], bool)
    inside_bg[y1:y2, x1:x2] = ~text_mask   # 상자 안에서 글자가 아닌 곳 = 진짜 배경

    pixels = arr[ring | inside_bg]
    if len(pixels) < MIN_PIXELS:
        return None
    devs = np.std(pixels, axis=0)
    threshold = 7.0 if np.std(devs) > 1.0 else 10.0
    if devs.max() >= threshold:
        return None
    return np.median(pixels, axis=0).astype(np.uint8)


#두 상자가 겹치는지 (닿기만 해도 겹친 것으로 침)
def boxes_overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


#gap 안에서 만나는 상자끼리 하나로 합친다. 합친 뒤 또 만날 수 있으니 더 합칠 게 없을 때까지 반복
def merge_boxes(boxes, gap=CTX):
    boxes = list(boxes)
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                x1, y1, x2, y2 = boxes[i]
                if boxes_overlap((x1 - gap, y1 - gap, x2 + gap, y2 + gap), boxes[j]):
                    boxes[i] = (min(x1, boxes[j][0]), min(y1, boxes[j][1]), max(x2, boxes[j][2]), max(y2, boxes[j][3]))
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    return boxes


#tile 넘는 상자를 tile 이하 조각으로 쪼갠다
def split_tile(box, tile=TILE):
    x1, y1, x2, y2 = box
    return [(tx, ty, min(tx + tile, x2), min(ty + tile, y2))
            for ty in range(y1, y2, tile) for tx in range(x1, x2, tile)]


#단색 상자는 바로 채우고, 모델이 필요한 것만 (arr, 페이지 마스크, 조각 목록) 으로 정리한다
#split: 합친 상자를 더 쪼개는 함수 (LaMa 는 512, FLUX2 는 2000). None 이면 합친 덩어리 그대로
def prepare_jobs(image, contents, split=split_tile):
    arr = np.array(image.convert("RGB"))
    page_mask = np.zeros(arr.shape[:2], bool)
    boxes = []
    for (x1, y1, x2, y2), text_mask in box_masks(image, contents):
        color = uniform_color(arr, (x1, y1, x2, y2), text_mask)
        if color is not None:
            arr[y1:y2, x1:x2][text_mask] = color
        else:
            page_mask[y1:y2, x1:x2] |= text_mask
            boxes.append((x1, y1, x2, y2))
    merged = merge_boxes(boxes)
    tiles = [t for b in merged for t in split(b)] if split else merged
    return arr, page_mask, tiles


#조각마다 페이지 마스크에서 그 부분만 잘라 call_model 에 넣고, 글자였던 자리만 갈아끼운다
#→ crop 안에 다른 상자의 글자가 들어와도 page_mask 에 이미 표시돼 있어서 배경으로 착각하지 않는다
def run_model_merged(arr, page_mask, tiles, call_model):
    h, w = arr.shape[:2]
    for x1, y1, x2, y2 in tiles:
        cy1, cy2 = max(0, y1 - CTX), min(h, y2 + CTX)
        cx1, cx2 = max(0, x1 - CTX), min(w, x2 + CTX)
        out = call_model(arr[cy1:cy2, cx1:cx2], page_mask[cy1:cy2, cx1:cx2].astype(np.uint8) * 255)
        tile_mask = page_mask[y1:y2, x1:x2]
        arr[y1:y2, x1:x2][tile_mask] = out[y1 - cy1:y2 - cy1, x1 - cx1:x2 - cx1][tile_mask]
    return arr


#모델 없이 글자 자리만 흰색으로
def inpaint_white(image, contents):
    arr = np.array(image.convert("RGB"))
    for (x1, y1, x2, y2), text_mask in box_masks(image, contents):
        arr[y1:y2, x1:x2][text_mask] = 255
    return Image.fromarray(arr)
