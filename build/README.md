# 데스크톱 앱 빌드 (BallonsTranslator 방식: 포터블 파이썬 + 첫 실행 때 설치)

전부 프로젝트 루트에서 실행 (conda env `yusuk1`).

```
# 1) 프런트 빌드 → frontend/dist
cd frontend && npm run build && cd ..

# 2) 앱 폴더 → dist/MangaTranslator/  (약 380MB: 파이썬 embeddable + pip + pywebview + 앱 코드 + 글꼴 + ctd·LaMa 가중치)
python build/make_portable.py

# 3) 설치 파일 → build/out/MangaTranslator-Setup-<버전>.exe  (Inno Setup 6: winget install JRSoftware.InnoSetup)
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" build\installer.iss
```

개발 PC 에서 앱처럼 실행만 해 보려면 `python app.py` (frontend/dist 가 있어야 함). 포터블 폴더를 직접 시험하려면
`dist\MangaTranslator\python\pythonw.exe launch.py` (환경변수 `MANGA_DATA_DIR` 로 데이터 폴더를 바꿀 수 있다).

## 사용자 PC 에서 일어나는 일
- 설치 파일(약 250MB)을 실행하면 `%LOCALAPPDATA%\MangaTranslatorpp` 에 풀리고 바로 가기가 생긴다 (`python\pythonw.exe launch.py`).
- 처음 켜면 `launch.py` 가 창을 띄우고, `requirements.txt` 를 pip 으로 `%LOCALAPPDATA%\MangaTranslator\pylib` 에 설치한다
  (torch cu128 포함 약 3GB, 진행 상황 표시). 이어서 RF-DETR·manga-ocr 가중치를 Hugging Face 에서 `...\hf` 에 받고 서버를 띄운다.
- 두 번째부터는 설치·다운로드 없이 바로 뜬다. `requirements.txt` 가 바뀐 버전으로 업데이트하면 다시 설치한다 (해시로 판단).
- 앱을 지워도 `projects`·`pylib`·`hf` 는 남는다. 로그는 `%LOCALAPPDATA%\MangaTranslator\logspp.log`.
- NVIDIA 드라이버가 없으면 torch 가 CPU 로 돈다 (느림). CUDA 툴킷 설치는 필요 없다 (torch 가 갖고 있음).

## 구조
- `launch.py`: 포터블 실행기. 설치·다운로드·서버 시작을 뒤에서 하고 로딩 화면(pywebview)에 진행 상황을 보여 준다.
- `app.py`: 개발 PC 용 실행기 (설치 과정 없음). `launch.py` 와 같은 창 구조.
- `backend.py`: API + `frontend/dist` 정적 서빙.
- 프로젝트 저장: `%LOCALAPPDATA%\MangaTranslator\projects\<이름>\` (`project.json`, `pages/`, `erased/`). `Process/projects.py`.
- 가중치: ctd·LaMa 는 앱 폴더에 동봉 (`CTD_MODEL`, `LAMA_MODEL` 환경변수로 launch.py 가 지정), RF-DETR·manga-ocr 는 HF 캐시(`HF_HOME`).
- 아이콘: `build/icon.ico`. FLUX 는 포함하지 않는다 (`/inpaint_flux` 는 501, 설정창에서 숨김).
