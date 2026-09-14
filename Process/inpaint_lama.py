import numpy as np
from PIL import Image
from dotenv import load_dotenv
from Process.inpaint_normal import prepare_jobs, run_model_merged
load_dotenv()

#LaMa (anime-manga-big-lama) 로 글자 지우기. 가중치는 LAMA_MODEL 환경변수

_lama = None
def get_lama():
    global _lama
    if _lama is None:
        from simple_lama_inpainting import SimpleLama
        _lama = SimpleLama()
    return _lama


#crop(HxWx3) 과 mask(HxW, 0/255) 를 받아 지운 이미지를 돌려주는 공통 형식. 모델마다 이 형식만 맞추면 됨
def call_lama(crop, mask):
    out = get_lama()(Image.fromarray(crop), Image.fromarray(mask))
    return np.array(out.convert("RGB"))[:crop.shape[0], :crop.shape[1]]


def inpaint_lama(image, contents):
    arr, page_mask, tiles = prepare_jobs(image, contents)
    if tiles:
        arr = run_model_merged(arr, page_mask, tiles, call_lama)
    return Image.fromarray(arr)
