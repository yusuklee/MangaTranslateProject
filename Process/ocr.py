from manga_ocr import MangaOcr
from PIL import Image

mocr = MangaOcr()
#이미지 넣으면 끝
print(mocr(Image.open("bubble.png")))
