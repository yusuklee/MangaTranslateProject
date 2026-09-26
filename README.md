<h1 align="center">Manga Translator</h1>

<p align="center">
<a href="https://github.com/yusuklee/MangaTranslateProject/releases/latest/download/MangaTranslator.zip"><img alt="Download" src="https://img.shields.io/github/v/release/yusuklee/MangaTranslateProject?style=for-the-badge&label=Download&color=f2760a"></a>
</p>

---

 Detection, OCR and inpainting run locally on your GPU. Translation uses Gemini with your own API key.

## Install

1. [Download MangaTranslator.zip](https://github.com/yusuklee/MangaTranslateProject/releases/latest/download/MangaTranslator.zip) and extract it anywhere (a short path like `C:\MangaTranslator` is best). Do not run it from inside the zip.
2. Run **MangaTranslator.bat** in the extracted folder. The first start downloads PyTorch and the models (about 4 GB, one time) into the `app` folder and shows the progress. Later starts open right away.
3. Open **Settings** and paste your [Gemini API key](https://aistudio.google.com/apikey).

Everything (packages, models, your projects) stays inside that folder. To uninstall, delete the folder.

> [!NOTE]
> Works on any Windows 10/11 PC. With an NVIDIA GPU (driver 570 or newer, no CUDA toolkit needed) a page takes about a second. Without one it falls back to the CPU and is much slower.

## setup

![스크린샷 2026-09-25 005338.png](guide_imgs/%EC%8A%A4%ED%81%AC%EB%A6%B0%EC%83%B7%202026-09-25%20005338.png)![alt text](<스크린샷 2026-09-25 005338.png>)

---

![스크린샷 2026-09-25 005357.png](guide_imgs/%EC%8A%A4%ED%81%AC%EB%A6%B0%EC%83%B7%202026-09-25%20005357.png)![alt text](<스크린샷 2026-09-25 005357.png>)

---
![스크린샷 2026-09-25 005427.png](guide_imgs/%EC%8A%A4%ED%81%AC%EB%A6%B0%EC%83%B7%202026-09-25%20005427.png)![alt text](<스크린샷 2026-09-25 005427.png>)

---

![설정 버튼 위치.png](guide_imgs/%EC%84%A4%EC%A0%95%20%EB%B2%84%ED%8A%BC%20%EC%9C%84%EC%B9%98.png)![alt text](<설정 버튼 위치.png>)

---

![스크린샷 2026-09-25 010132.png](guide_imgs/%EC%8A%A4%ED%81%AC%EB%A6%B0%EC%83%B7%202026-09-25%20010132.png)![alt text](<스크린샷 2026-09-25 010132.png>)


## How it works

| Step | What happens | Model |
|---|---|---|
| Detect | Finds text, speech bubbles and onomatopoeia | RF-DETR |
| OCR | Reads the Japanese text in every box | manga-ocr |
| Translate | Sends the page text to Gemini (Japanese → Korean by default, 38 languages available) | Gemini flash |
| Erase | Removes the original text | LaMa |
| Render | Typesets the translation into the bubbles with the font you pick | – |
| Export | Writes the finished pages to a folder | – |



## Models

- Detection: [Koharu Layout RF-DETR Seg 2XL](https://huggingface.co/mayocream/koharu-layout-rfdetr-seg-2xl-1152)
- OCR: [manga-ocr](https://huggingface.co/kha-white/manga-ocr-base)
- Text mask: [comic-text-detector](https://github.com/dmMaze/comic-text-detector)
- Inpainting: [LaMa (anime-manga-big-lama)](https://github.com/advimman/lama)
- Translation: Gemini 3.5 / 3.6 / 3.7 / 3.8 flash and 3.5 flash-lite,
- Gemini 3.5 Flash, 3.6 Flash and 3.5 Flash-Lite are the most reliable choices right now.
- Newer preview models (3.7, 3.8) are often overloaded and fall back to 3.5 Flash automatically.



## requirements

Python 3.13 and Node.js.

```
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python app.py                       # run the desktop app
python -m uvicorn backend:app        # or just the API server for development (frontend: npm run dev)
```


## Acknowledgements

  - Text mask and layout approach: Koharu
  - Detection / OCR / inpainting models: linked above
