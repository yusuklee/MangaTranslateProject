import base64, io
import numpy as np
from PIL import Image
from dotenv import load_dotenv
load_dotenv()

MIN_PIXELS = 16
margin1 = 4     # 상자에서 이만큼 밖까지는 글자 번짐이라 버린다
margin2 = 3     # 그 바깥으로 이만큼이 색을 잴 고리

TILE = 512      # 한 번에 지울 조각의 최대 한 변
CTX = 128       # 조각 사방에 붙여 모델에 보여줄 배경

_lama = None
def get_lama():
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama   # LAMA_MODEL 환경변수의 가중치를 씀
        _lama = SimpleLama()
    return _lama


#crop(HxWx3)과 mask(HxW, 0/255)를 받아 지운 이미지를 돌려주는 공통 형식. 모델마다 이 형식만 맞추면 됨
def call_lama(crop, mask):
    lama = get_lama()
    out = lama(Image.fromarray(crop), Image.fromarray(mask))
    return np.array(out.convert("RGB"))[:crop.shape[0], :crop.shape[1]]


#TILE 넘는 상자를 TILE 이하 조각으로 쪼갠다
def split_tile(box):
    x1,y1,x2,y2 = box
    tiles = []
    for ty in range(y1, y2, TILE):
        for tx in range(x1, x2, TILE):
            tiles.append((tx, ty, min(tx+TILE, x2), min(ty+TILE, y2)))
    return tiles


DILATE_RATIO = 6 / 1024   # 이미지가 클수록 글자 획도 두꺼워서 그만큼 더 넓힌다 (koharu와 동일 비율)


#base64 PNG → bool 배열 (상자 크기)
def decode_mask(mask_b64):
    raw = base64.b64decode(mask_b64)
    return np.array(Image.open(io.BytesIO(raw))) > 127


#글자인 픽셀 하나하나 주변을 r만큼 넓게 칠한다 (가장자리 흐릿한 픽셀까지 포함)
def dilate(mask, image_size):
    r = max(1, round(max(image_size) * DILATE_RATIO))
    h, w = mask.shape
    out = np.zeros_like(mask)

    ys, xs = np.where(mask)              # 글자인 픽셀들의 좌표 목록
    for y, x in zip(ys, xs):
        y1, y2 = max(0, y - r), min(h, y + r + 1)
        x1, x2 = max(0, x - r), min(w, x + r + 1)
        out[y1:y2, x1:x2] = True         # 그 픽셀 주변 정사각형을 전부 켠다

    return out


#상자 전체가 아니라 상자 안의 진짜 배경 픽셀(글자가 아닌 곳)도 같이 본다
def uniform_color_upgrade(arr, box, text_mask):
    x1, y1, x2, y2 = box
    h, w = arr.shape[:2]

    ring = np.zeros(arr.shape[:2], bool)
    oy1, oy2 = max(y1 - margin1, 0), min(y2 + margin1, h)
    ox1, ox2 = max(x1 - margin1, 0), min(x2 + margin1, w)
    ring[oy1:oy2, ox1:ox2] = True
    iy1, iy2 = max(y1 - margin2, 0), min(y2 + margin2, h)
    ix1, ix2 = max(x1 - margin2, 0), min(x2 + margin2, w)
    ring[iy1:iy2, ix1:ix2] = False

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


#상자마다 따로 마스크를 만들지 않고, 페이지 전체 크기 마스크 하나에 다 모아둔다
def build_page_mask(shape, boxes_and_masks):   # boxes_and_masks = [((x1,y1,x2,y2), text_mask), ...]
    page_mask = np.zeros(shape, bool)
    for (x1, y1, x2, y2), text_mask in boxes_and_masks:
        page_mask[y1:y2, x1:x2] |= text_mask
    return page_mask


#상자를 사방으로 gap만큼 넓힌다
def expand_box(box, gap):
    x1, y1, x2, y2 = box
    return (x1 - gap, y1 - gap, x2 + gap, y2 + gap)


#두 상자가 겹치는지 (닿기만 해도 겹친 것으로 침)
def boxes_overlap(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)


#gap(CTX) 안에서 만나는 상자끼리 하나로 합친다. 합친 뒤 또 만날 수 있으니 더 합칠 게 없을 때까지 반복한다
def merge_boxes(boxes, gap=CTX):
    boxes = list(boxes)
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if boxes_overlap(expand_box(boxes[i], gap), boxes[j]):
                    x1 = min(boxes[i][0], boxes[j][0])
                    y1 = min(boxes[i][1], boxes[j][1])
                    x2 = max(boxes[i][2], boxes[j][2])
                    y2 = max(boxes[i][3], boxes[j][3])
                    boxes[i] = (x1, y1, x2, y2)
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    return boxes


#조각(합쳐진 범위)마다, 페이지 전체 마스크에서 그 부분만 잘라 call_model에 넣는다
#→ crop 안에 다른 상자의 글자가 들어와도 page_mask엔 이미 표시돼 있어서 배경으로 착각하지 않는다
#call_model(crop, mask) 형식만 맞으면 어떤 가중치든 그대로 씀
def run_model_merged(arr, page_mask, tiles, call_model):
    h, w = arr.shape[:2]

    for x1, y1, x2, y2 in tiles:
        cy1, cy2 = max(0, y1 - CTX), min(h, y2 + CTX)
        cx1, cx2 = max(0, x1 - CTX), min(w, x2 + CTX)

        crop = arr[cy1:cy2, cx1:cx2]
        mask = page_mask[cy1:cy2, cx1:cx2].astype(np.uint8) * 255
        out = call_model(crop, mask)

        tile_mask = page_mask[y1:y2, x1:x2]   # 이 조각 범위 안에서 글자인 곳
        region = arr[y1:y2, x1:x2]
        painted = out[y1 - cy1:y2 - cy1, x1 - cx1:x2 - cx1]
        region[tile_mask] = painted[tile_mask]   # 글자였던 자리만 갈아끼움
    return arr


#상자별로 단색이면 바로 채우고, 모델이 필요한 것만 (page_mask, 조각목록)으로 정리한다
def prepare_jobs(image, contents):
    arr = np.array(image.convert("RGB"))
    boxes_and_masks = []

    for c in contents:
        x1, y1, x2, y2 = map(int, c["pos"])
        if c.get("mask"):
            text_mask = dilate(decode_mask(c["mask"]), image.size)
        else:
            text_mask = np.ones((y2 - y1, x2 - x1), bool)

        color = uniform_color_upgrade(arr, (x1, y1, x2, y2), text_mask)
        if color is not None:
            region = arr[y1:y2, x1:x2]
            region[text_mask] = color
        else:
            boxes_and_masks.append(((x1, y1, x2, y2), text_mask))

    page_mask, tiles = None, []
    if boxes_and_masks:
        page_mask = build_page_mask(arr.shape[:2], boxes_and_masks)
        merged = merge_boxes([box for box, _ in boxes_and_masks])
        tiles = [tile for box in merged for tile in split_tile(box)]   # 512 넘으면 마저 쪼갬

    return arr, page_mask, tiles


#상자 전체가 아니라 실제 글자 모양(contents[i]["mask"])만 지운다. mask 없으면 사각형 전체
#근처 상자끼리는 합쳐서 같이 지우기 때문에, 옆 텍스트가 배경으로 오인되지 않는다
def inpaint_lama(image, contents):
    arr, page_mask, tiles = prepare_jobs(image, contents)
    if tiles:
        arr = run_model_merged(arr, page_mask, tiles, call_lama)
    return Image.fromarray(arr)

