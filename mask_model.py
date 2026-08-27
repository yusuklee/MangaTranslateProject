import torch, numpy as np, torch.nn as nn, torch.nn.functional as F
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2
from huggingface_hub import hf_hub_download
import cv2
from scipy.ndimage import binary_fill_holes

ENCODER = "tu-efficientnetv2_rw_m"


def convert_batchnorm_to_groupnorm(module):
    for name, child in module.named_children():
        if isinstance(child, nn.BatchNorm2d):
            num_channels = child.num_features
            num_groups = 8
            if num_channels < num_groups or num_channels % num_groups != 0:
                for i in range(min(num_channels, 8), 1, -1):
                    if num_channels % i == 0:
                        num_groups = i
                        break
                else:
                    num_groups = 1
            setattr(module, name, nn.GroupNorm(num_groups=num_groups,
                                               num_channels=num_channels))
        else:
            convert_batchnorm_to_groupnorm(child)



ckpt = hf_hub_download("a-b-c-x-y-z/Manga-Text-Segmentation-2025", "model.pth")

model = smp.UnetPlusPlus(encoder_name=ENCODER, encoder_weights=None,
                       in_channels=3, classes=1, activation=None,
                       decoder_attention_type='scse')
convert_batchnorm_to_groupnorm(model.decoder)
model.load_state_dict(torch.load(ckpt, map_location='cpu'))
model.eval().cuda()

tf = A.Compose([A.Normalize(mean=(0.485,0.456,0.406),
                          std=(0.229,0.224,0.225)), ToTensorV2()])

def text_mask(img_np, thr=0.5):
  h, w = img_np.shape[:2]
  x = tf(image=img_np)['image'][None].cuda()
  ph, pw = (32-h%32)%32, (32-w%32)%32
  x = F.pad(x, (0,pw,0,ph))
  with torch.no_grad(), torch.amp.autocast('cuda'):
      p = model(x).sigmoid()
  m = (p[0, 0, :h, :w].float().cpu().numpy() > thr).astype('uint8')

  k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
  m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
  m = binary_fill_holes(m).astype('uint8')
  m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=2)
  return m.astype(bool)
