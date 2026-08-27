import warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
from huggingface_hub import hf_hub_download
from rfdetr import RFDETRSeg2XLarge
from safetensors.torch import load_file
from PIL import Image
import numpy as np
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


# 2 OCR

from manga_ocr import MangaOcr
mocr = MangaOcr()

# 3 INPAINT
#d.xyxy 말풍선을 감싸는 직사각형 좌상단, 우상단
#d.mask 말풍선의 실제모양 픽셀 하나하나 True/False

out = np.array(image)
for box, name, bm in zip(d.xyxy, d.data["class_name"], d.mask):
    if name=="bubble":
        out[bm]=255

Image.fromarray(out).save("results/4-Koma_EP1_inpainted.png")
