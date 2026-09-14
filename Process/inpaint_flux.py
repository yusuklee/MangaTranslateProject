import numpy as np
from PIL import Image
from dotenv import load_dotenv
import os
load_dotenv()

from Process.inpaint_normal import prepare_jobs, run_model_merged, split_tile

FLUX2_MODEL = os.environ.get("FLUX2_MODEL", "black-forest-labs/FLUX.2-klein-4B")
FLUX2_PROMPT = (
    "remove all text from the image, keep everything else exactly the same, "
    "preserve the exact composition, positions, poses, and proportions of every "
    "character and object, do not shift, resize, or move anything"
)
FLUX2_STEPS = 4
PLUS_TILE = 2000   # 마스크 뭉치 주변을 이 크기 이하로 잘라서 넣는다 (위치 어긋남 줄이기)

# 8bit로 압축해서 저장해 둘 폴더 (프로젝트 루트/flux2-klein-8bit). 없으면 원본에서 매번 압축
FLUX2_8BIT_DIR = os.environ.get(
    "FLUX2_8BIT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "flux2-klein-8bit"),
)


TRANSFORMER_DIR = os.path.join(FLUX2_8BIT_DIR, "transformer")
EMBEDS_FILE = os.path.join(FLUX2_8BIT_DIR, "prompt_embeds.pt")   # 고정 프롬프트를 인코딩한 벡터


#트랜스포머를 8bit로 올린다. 압축본 폴더가 있으면 거기서, 없으면 원본(7.75GB)을 압축하면서
def _load_transformer():
    import torch
    from diffusers import Flux2Transformer2DModel, BitsAndBytesConfig
    if os.path.isdir(TRANSFORMER_DIR):
        return Flux2Transformer2DModel.from_pretrained(TRANSFORMER_DIR, torch_dtype=torch.bfloat16)
    return Flux2Transformer2DModel.from_pretrained(
        FLUX2_MODEL, subfolder="transformer",
        quantization_config=BitsAndBytesConfig(load_in_8bit=True),
        torch_dtype=torch.bfloat16,
    )


#텍스트 인코더(8GB)를 8bit로 올린다. 프롬프트 벡터를 한 번 만들 때만 필요
def _load_text_encoder():
    import torch
    from transformers import Qwen3ForCausalLM, BitsAndBytesConfig
    return Qwen3ForCausalLM.from_pretrained(
        FLUX2_MODEL, subfolder="text_encoder",
        quantization_config=BitsAndBytesConfig(load_in_8bit=True),
        torch_dtype=torch.bfloat16,
    )


#8bit 트랜스포머 + 프롬프트 벡터를 FLUX2_8BIT_DIR에 저장한다 (한 번만 실행)
#텍스트 인코더는 저장하지 않는다 (transformers의 8bit 저장이 안 되고, 벡터만 있으면 필요도 없음)
def save_flux2_8bit():
    import torch
    os.makedirs(FLUX2_8BIT_DIR, exist_ok=True)
    if not os.path.isdir(TRANSFORMER_DIR):
        _load_transformer().save_pretrained(TRANSFORMER_DIR)
    torch.save(get_prompt_embeds().cpu(), EMBEDS_FILE)


_flux2 = None
_flux2_device = None
_prompt_embeds = None
def get_flux2():
    global _flux2, _flux2_device, _prompt_embeds
    if _flux2 is None:
        import gc, torch
        from diffusers import Flux2KleinPipeline
        _flux2_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # 프롬프트 벡터가 저장돼 있으면 텍스트 인코더는 아예 안 올린다
        text_encoder = None if os.path.exists(EMBEDS_FILE) else _load_text_encoder()
        _flux2 = Flux2KleinPipeline.from_pretrained(
            FLUX2_MODEL, transformer=_load_transformer(), text_encoder=text_encoder,
            torch_dtype=torch.bfloat16,
        )
        _flux2.to(_flux2_device)

        if text_encoder is None:
            _prompt_embeds = torch.load(EMBEDS_FILE).to(_flux2_device)
        else:
            # 프롬프트가 고정 문장이라 한 번만 벡터로 바꿔두고, 텍스트 인코더(4.3GB)는 GPU에서 내린다
            with torch.no_grad():
                _prompt_embeds, _ = _flux2.encode_prompt(FLUX2_PROMPT, device=_flux2_device)
            _flux2.text_encoder = None
            del text_encoder
            gc.collect()
            torch.cuda.empty_cache()
    return _flux2


#고정 프롬프트를 미리 인코딩한 벡터. pipe(prompt=...) 대신 pipe(prompt_embeds=...)로 쓴다
def get_prompt_embeds():
    get_flux2()
    return _prompt_embeds


#마스크 없이 프롬프트로만 "텍스트 지워라" 시키고, 결과 전체를 그대로 돌려준다
#(실제 원본에 덮어씌우는 건 run_model_merged가 mask 부분만 골라서 함)
def call_flux(crop, mask):
    import torch
    pipe = get_flux2()
    h, w = crop.shape[:2]
    rh, rw = ((h + 15) // 16) * 16, ((w + 15) // 16) * 16

    img = Image.fromarray(crop).resize((rw, rh))
    out = pipe(
        prompt_embeds=get_prompt_embeds(),
        image=img,
        width=rw,
        height=rh,
        guidance_scale=1.0,
        num_inference_steps=FLUX2_STEPS,
        generator=torch.Generator(device=_flux2_device).manual_seed(0),
    ).images[0]

    return np.array(out.resize((w, h)).convert("RGB"))


#마스크 뭉치 주변만 잘라서(최대 PLUS_TILE+CTX) 모델에 주고,
#결과에서 마스크였던 자리만 원본에 덮어씌운다
def inpaint_flux(image, contents):
    arr, page_mask, tiles = prepare_jobs(image, contents, split=lambda b: split_tile(b, PLUS_TILE))
    if tiles:
        arr = run_model_merged(arr, page_mask, tiles, call_flux)
    return Image.fromarray(arr)

