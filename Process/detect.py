
from huggingface_hub import hf_hub_download
from rfdetr import RFDETRSeg2XLarge
from safetensors.torch import load_file
from PIL import Image

repo = "mayocream/koharu-layout-rfdetr-seg-2xl-1152"
params = hf_hub_download(repo,"model.safetensors")
model = RFDETRSeg2XLarge(pretrain_weights=None, resolution=1152,
                         num_select =160, num_classes=4)
model.model.model.load_state_dict(load_file(params,device="cpu"), strict=True)
model.model.class_names=["text", "onomatopoeia","bubble","panel"]

#--검출용
image = Image.open("../images/4-Koma_EP1.webp").convert("RGB")
d= model.predict(image)
print(d)


