import os
import numpy as np
import cv2
from dotenv import load_dotenv
load_dotenv()

#BallonsTranslator 의 comic-text-detector (koharu 도 마스크용으로 씀). 입력 1024x1024, 출력 세 가지:
#  seg : 글자 영역 확률맵 (지우기 마스크용)
#  det : DBNet 줄 심지 확률맵 (줄 나누기·글자 크기용, textlines.py)
#  blk : YOLO 글자 상자 (안 씀. 큰 덩어리만 잡고 작은 대사를 놓쳐서 상자는 RF-DETR 이 맡음)
CTD_MODEL = os.environ.get("CTD_MODEL", "comictextdetector.pt.onnx")
CTD_SIZE = 1024

_ctd = None
def get_ctd():
    global _ctd
    if _ctd is None:
        import torch          # torch 가 묶어 온 CUDA/cuDNN DLL 을 먼저 올려야 onnxruntime-gpu 가 GPU 를 잡음
        import onnxruntime as ort
        path = CTD_MODEL
        if not os.path.exists(path):   # Process/ 안에서 실행해도 프로젝트 루트의 파일을 찾게
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), CTD_MODEL)
        _ctd = ort.InferenceSession(path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    return _ctd


#ctd 1번 실행 → (글자 확률맵, 줄 맵). 둘 다 원본 크기 HxW float 0~1
def ctd_maps(image):
    W, H = image.size
    s = CTD_SIZE / max(W, H)
    rw, rh = round(W * s), round(H * s)

    canvas = np.zeros((CTD_SIZE, CTD_SIZE, 3), np.uint8)   # 긴 변을 1024 에 맞추고 나머지는 검게 채움
    canvas[:rh, :rw] = np.array(image.convert("RGB").resize((rw, rh)))
    inp = canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255.0

    _, seg, det = get_ctd().run(None, {"image_samples": inp})
    up = lambda m: cv2.resize(m[:rh, :rw], (W, H), interpolation=cv2.INTER_LINEAR)
    return up(seg[0, 0]), up(det[0, 0])


BINARY_THRESHOLD = 60 / 255   # koharu 0.61.2: BINARY_THRESHOLD = 60
CLOSE_RADIUS = 10             # HOLE_CLOSE_RADIUS
DILATE_RADIUS = 3             # DILATION_RADIUS


def square(r):
    return np.ones((2 * r + 1, 2 * r + 1), np.uint8)


#글자 확률맵 → 글자 획 마스크 (HxW bool). koharu 0.61.2 방식: 이진화 → 틈 메우기(close) → 살짝 팽창
def koharu_mask(prob):
    m = (prob >= BINARY_THRESHOLD).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, square(CLOSE_RADIUS))
    return cv2.dilate(m, square(DILATE_RADIUS)) > 0
