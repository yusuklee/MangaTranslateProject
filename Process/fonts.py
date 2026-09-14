import os, json
from fontTools.ttLib import TTFont

#koharu 가 내장한 Google Fonts 폴더 (fonts/google/<family>/<Style>.ttf). 한글 글리프('가')가 있는 폰트만 골라 목록을 만든다
FONTS_DIR = os.environ.get("KOHARU_FONTS", os.path.join(os.environ.get("LOCALAPPDATA", ""), "Koharu", "fonts", "google"))
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts_cache.json")
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


#[{family, regular, bold}] — regular/bold 는 FONTS_DIR 기준 상대 경로. 한 번 훑으면 파일에 저장해 둔다
def list_korean_fonts():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
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
    json.dump(out, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out
