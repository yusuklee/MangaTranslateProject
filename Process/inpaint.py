import base64, io
import numpy as np
import cv2
from PIL import Image
from Process.detect_ocr import square



TILE = 512      # 한 번에 지울 조각의 최대 한 변
CTX = 128       # 조각 사방에 붙여 모델에 보여줄 배경
FONT_RATIO = 0.16         # koharu 0.61.2 LEGACY_BLOCK_DILATE_FONT_RATIO
MIN_R, MAX_R = 2, 8       # LEGACY_MIN/MAX_DILATE_RADIUS
MIN_PIXELS = 16
margin1 = 4     # 상자에서 이만큼 밖까지는 글자 번짐이라 버린다
margin2 = 3     # 그 바깥으로 이만큼이 색을 잴 고리


def box_masks(image, contents):
    W, H = image.size
    out = []
    for c in contents:
        x1, y1, x2, y2 = map(int, c.get("mask_area") or c["pos"])
        r = int(np.clip(round(min(x2 - x1, y2 - y1) * FONT_RATIO), MIN_R, MAX_R))
        ex1, ey1, ex2, ey2 = max(0, x1 - r), max(0, y1 - r), min(W, x2 + r), min(H, y2 + r)
        page = np.zeros((H, W), np.uint8)
        page[y1:y2, x1:x2] = np.array(Image.open(io.BytesIO(base64.b64decode(c["mask"])))) > 127 if c.get("mask") else 1
        out.append(((ex1, ey1, ex2, ey2), cv2.dilate(page[ey1:ey2, ex1:ex2], square(r)) > 0))
    return out



def uniform_color(arr, box, text_mask):
    x1, y1, x2, y2 = box
    sel = np.zeros(arr.shape[:2], bool)
    sel[max(y1 - margin1, 0):y2 + margin1, max(x1 - margin1, 0):x2 + margin1] = True
    sel[max(y1 - margin2, 0):y2 + margin2, max(x1 - margin2, 0):x2 + margin2] = False
    sel[y1:y2, x1:x2] = ~text_mask
    px = arr[sel]
    if len(px) < MIN_PIXELS:
        return None
    devs = px.std(0)
    if devs.max() >= (7.0 if devs.std() > 1.0 else 10.0):
        return None
    return np.median(px, 0).astype(np.uint8)



def merge_boxes(boxes, gap=CTX):
    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if b[0] <= a[2] + gap and a[0] - gap <= b[2] and b[1] <= a[3] + gap and a[1] - gap <= b[3]:
                boxes[i] = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                boxes.pop(j)
                return merge_boxes(boxes, gap)
    return boxes



def inpaint_white(image, contents):
    arr = np.array(image.convert("RGB"))
    for (x1, y1, x2, y2), m in box_masks(image, contents):
        arr[y1:y2, x1:x2][m] = 255
    return Image.fromarray(arr)


_lama = None
def call_lama(crop, mask):
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama
        _lama = SimpleLama()
    out = _lama(Image.fromarray(crop), Image.fromarray(mask))
    return np.array(out.convert("RGB"))[:crop.shape[0], :crop.shape[1]]



def inpaint_lama(image, contents, call_model=call_lama, tile=TILE):
    arr = np.array(image.convert("RGB"))
    h, w = arr.shape[:2]
    page_mask = np.zeros((h, w), bool)
    boxes = []
    for (x1, y1, x2, y2), m in box_masks(image, contents):
        color = uniform_color(arr, (x1, y1, x2, y2), m)
        if color is not None:
            arr[y1:y2, x1:x2][m] = color
        else:
            page_mask[y1:y2, x1:x2] |= m
            boxes.append((x1, y1, x2, y2))
    for bx1, by1, bx2, by2 in merge_boxes(boxes):
        for y1 in range(by1, by2, tile):
            for x1 in range(bx1, bx2, tile):
                x2, y2 = min(x1 + tile, bx2), min(y1 + tile, by2)
                cx1, cy1, cx2, cy2 = max(0, x1 - CTX), max(0, y1 - CTX), min(w, x2 + CTX), min(h, y2 + CTX)
                out = call_model(arr[cy1:cy2, cx1:cx2], page_mask[cy1:cy2, cx1:cx2].astype(np.uint8) * 255)
                m = page_mask[y1:y2, x1:x2]
                arr[y1:y2, x1:x2][m] = out[y1 - cy1:y2 - cy1, x1 - cx1:x2 - cx1][m]
    return Image.fromarray(arr)


# #FLUX2 (프롬프트로 지운 뒤 마스크 자리만 덮어씀). torch·diffusers 와 8bit 압축본 flux2-klein-8bit/ 필요
# import os
# FLUX2_MODEL = os.environ.get("FLUX2_MODEL", "black-forest-labs/FLUX.2-klein-4B")
# FLUX2_PROMPT = ("remove all text from the image, keep everything else exactly the same, "
#                 "preserve the exact composition, positions, poses, and proportions of every "
#                 "character and object, do not shift, resize, or move anything")
# FLUX2_STEPS = 4
# PLUS_TILE = 2000   # 마스크 뭉치 주변을 이 크기 이하로 잘라서 넣는다 (위치 어긋남 줄이기)
# FLUX2_8BIT_DIR = os.environ.get("FLUX2_8BIT_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flux2-klein-8bit"))
# TRANSFORMER_DIR = os.path.join(FLUX2_8BIT_DIR, "transformer")
# EMBEDS_FILE = os.path.join(FLUX2_8BIT_DIR, "prompt_embeds.pt")   # 고정 프롬프트를 인코딩한 벡터
#
# #트랜스포머를 8bit로. 압축본 폴더가 있으면 거기서, 없으면 원본(7.75GB)을 압축하면서
# def _load_transformer():
#     import torch
#     from diffusers import Flux2Transformer2DModel, BitsAndBytesConfig
#     if os.path.isdir(TRANSFORMER_DIR):
#         return Flux2Transformer2DModel.from_pretrained(TRANSFORMER_DIR, torch_dtype=torch.bfloat16)
#     return Flux2Transformer2DModel.from_pretrained(FLUX2_MODEL, subfolder="transformer",
#         quantization_config=BitsAndBytesConfig(load_in_8bit=True), torch_dtype=torch.bfloat16)
#
# #8bit 트랜스포머 + 프롬프트 벡터를 FLUX2_8BIT_DIR 에 저장 (한 번만 실행)
# def save_flux2_8bit():
#     import torch
#     os.makedirs(FLUX2_8BIT_DIR, exist_ok=True)
#     if not os.path.isdir(TRANSFORMER_DIR):
#         _load_transformer().save_pretrained(TRANSFORMER_DIR)
#     get_flux2()
#     torch.save(_prompt_embeds.cpu(), EMBEDS_FILE)
#
# _flux2 = _flux2_device = _prompt_embeds = None
# def get_flux2():
#     global _flux2, _flux2_device, _prompt_embeds
#     if _flux2 is None:
#         import gc, torch
#         from diffusers import Flux2KleinPipeline
#         from transformers import Qwen3ForCausalLM, BitsAndBytesConfig
#         _flux2_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#         #프롬프트 벡터가 저장돼 있으면 텍스트 인코더(8GB)는 아예 안 올린다
#         text_encoder = None if os.path.exists(EMBEDS_FILE) else Qwen3ForCausalLM.from_pretrained(FLUX2_MODEL, subfolder="text_encoder",
#             quantization_config=BitsAndBytesConfig(load_in_8bit=True), torch_dtype=torch.bfloat16)
#         _flux2 = Flux2KleinPipeline.from_pretrained(FLUX2_MODEL, transformer=_load_transformer(), text_encoder=text_encoder, torch_dtype=torch.bfloat16)
#         _flux2.to(_flux2_device)
#         if text_encoder is None:
#             _prompt_embeds = torch.load(EMBEDS_FILE).to(_flux2_device)
#         else:   # 고정 문장이라 한 번만 벡터로 바꾸고 텍스트 인코더는 GPU 에서 내린다
#             with torch.no_grad():
#                 _prompt_embeds, _ = _flux2.encode_prompt(FLUX2_PROMPT, device=_flux2_device)
#             _flux2.text_encoder = None
#             del text_encoder
#             gc.collect()
#             torch.cuda.empty_cache()
#     return _flux2
#
# #마스크 없이 프롬프트로만 "텍스트 지워라" 시키고 결과 전체를 돌려준다 (덮어쓰기는 inpaint_lama 가 마스크 자리만)
# def call_flux(crop, mask):
#     import torch
#     pipe = get_flux2()
#     h, w = crop.shape[:2]
#     rh, rw = ((h + 15) // 16) * 16, ((w + 15) // 16) * 16
#     out = pipe(prompt_embeds=_prompt_embeds, image=Image.fromarray(crop).resize((rw, rh)), width=rw, height=rh,
#                guidance_scale=1.0, num_inference_steps=FLUX2_STEPS,
#                generator=torch.Generator(device=_flux2_device).manual_seed(0)).images[0]
#     return np.array(out.resize((w, h)).convert("RGB"))
#
# def inpaint_flux(image, contents):
#     return inpaint_lama(image, contents, call_flux, PLUS_TILE)
