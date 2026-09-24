<h1 align="center">Manga Translator</h1>

<p align="center">
<a href="https://github.com/yusuklee/MangaTranslateProject/releases/latest"><img alt="Download" src="https://img.shields.io/github/v/release/yusuklee/MangaTranslateProject?style=for-the-badge&label=Download&color=f2760a"></a>
</p>

---

 Detection, OCR and inpainting run locally on your GPU. Translation uses Gemini with your own API key.

## Install

1. Download `MangaTranslator-Setup-x.y.z.exe` from the [latest release](https://github.com/yusuklee/MangaTranslateProject/releases/latest) and run it. No admin rights needed.
2. Start **Manga Translator** from the Start menu. The first start downloads PyTorch and the models (about 4 GB, one time) and shows the progress. Later starts open right away.
3. Open **Settings** and paste your [Gemini API key](https://aistudio.google.com/apikey).

> [!NOTE]
> Works on any Windows 10/11 PC. With an NVIDIA GPU (driver 570 or newer, no CUDA toolkit needed) a page takes about a second. Without one it falls back to the CPU and is much slower.

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
- Translation: Gemini 3.5 / 3.6 / 3.7 / 3.8 flash and flash-lite, chosen in Settings. If a model is overloaded the app falls back to the next one.



## Build from source

Python 3.13 and Node.js.

```
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python app.py                       # run the desktop app
python -m uvicorn backend:app        # or just the API server for development (frontend: npm run dev)
```

Installer: `python build/make_portable.py` then compile `build/installer.iss` with Inno Setup 6.

## Thanks

Built on the models above and inspired by [Koharu](https://github.com/mayocream/koharu) and [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator).
