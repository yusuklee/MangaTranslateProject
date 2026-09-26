import os, json, sys
from fontTools.ttLib import TTFont

#렌더용 한글 폰트. 우선순위: 환경변수 KOHARU_FONTS → 프로젝트의 fonts/ (앱에 같이 묶는 17종, Google Fonts OFL) → koharu 설치 폴더
#fonts/index.json 이 있으면 폴더를 훑지 않고 그걸 쓴다 (앱에서는 폴더가 읽기 전용일 수 있어서)
def _resource_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _pick_fonts_dir():
    env = os.environ.get("KOHARU_FONTS")
    if env and os.path.isdir(env):
        return env
    bundled = os.path.join(_resource_dir(), "fonts")
    if os.path.isdir(bundled):
        return bundled
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Koharu", "fonts", "google")

FONTS_DIR = _pick_fonts_dir()
INDEX = os.path.join(FONTS_DIR, "index.json")
HANGUL = 0xAC00   # '가'


#16 = 대표 가족명 ("Noto Sans KR"), 1 = 스타일 포함 이름 ("Noto Sans KR Thin"). 16 부터 찾는다
def family_name(font):
    names = font["name"].names
    for want in (16, 1):
        for rec in names:
            if rec.nameID == want:
                try:
                    return rec.toUnicode()
                except Exception:
                    pass
    return None


#[{family, regular, bold}] — regular/bold 는 FONTS_DIR 기준 상대 경로
def list_korean_fonts():
    if os.path.exists(INDEX):
        return json.load(open(INDEX, encoding="utf-8"))
    out = []
    for d in sorted(os.listdir(FONTS_DIR)):
        folder = os.path.join(FONTS_DIR, d)
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".ttf", ".otf"))) if os.path.isdir(folder) else []
        if not files:
            continue
        try:
            font = TTFont(os.path.join(folder, files[0]), lazy=True)
            has_hangul = HANGUL in font.getBestCmap()
            name = family_name(font) or d
            font.close()
        except Exception:
            continue
        if not has_hangul:
            continue
        pick = lambda key: next((f for f in files if key in f.lower()), None)
        regular = pick("regular") or pick("[wght]") or files[0]
        bold = pick("bold") if "bold" not in regular.lower() else None
        out.append({"family": name, "regular": f"{d}/{regular}", "bold": f"{d}/{bold}" if bold else None})
    try:
        json.dump(out, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except OSError:
        pass   # 읽기 전용 폴더면 캐시 없이 간다
    return out
