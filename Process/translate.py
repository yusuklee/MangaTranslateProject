import os, json, re, time
from google import genai
from google.genai import types, errors

PROMPT = """You are a professional manga translator.

  Translation requirements:
  - Translate every input segment from Japanese into natural Korean.
  - Preserve meaning, character voice, emotional tone, relationship nuance, emphasis, and sound effects.
  - Localize idioms and sound effects naturally while keeping wording concise enough for speech bubbles.
  - Use surrounding segments only for disambiguation and continuity; never merge or split segments.
  - Write every translated `text` value only in Korean; do not include source text, notes, explanations, or alternatives.
  - Never preserve or repeat original-language text; translate names, terms, and sound effects using natural Korean
  conventions.

  Output requirements:
  - Each input segment has a numeric `id`.
  - Return only a JSON object whose `translations` array contains one object with `id` and translated `text` for every input
  segment.
  - Copy every input ID exactly once; order does not matter.
  - Never merge, split, omit, duplicate, or add segments."""


#응답 형태를 고정해서 모델이 다른 걸 붙이지 못하게 한다
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "translations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"id": {"type": "INTEGER"}, "text": {"type": "STRING"}},
                "required": ["id", "text"],
            },
        }
    },
    "required": ["translations"],
}


#JSON 객체가 여러 개 붙어 와도 전부 읽어서 합친다
def parse_translations(text):
    dec = json.JSONDecoder()
    out = {}
    i = 0
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return out
        obj, i = dec.raw_decode(text, i)
        for r in obj.get("translations", []):
            out[r["id"]] = r["text"]


client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龯]")   # 가나·한자가 번역문에 남았는지 검사용

MODEL = os.environ.get("TRANSLATE_MODEL", "gemini-3.6-flash")          # 바로 번역, 검토 없음
THINKING = "minimal"                                                    # 생각 끔 (3.x는 thinking_budget=0 안 먹음)
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]        # 503(과부하)·429(일일 한도)면 순서대로 대체


#503이면 2·4·8초 쉬고 재시도, 429(한도 초과)면 바로 다음 모델. 전부 실패하면 마지막 에러를 던진다
def ask(model, system, payload, retries=3, thinking=THINKING):
    candidates = [model] + [m for m in FALLBACK_MODELS if m != model]
    last = None
    n = len(payload.get("segments", []))
    t0 = time.time()
    for m in candidates:
        for attempt in range(retries + 1):
            try:
                t = time.time()
                resp = client.models.generate_content(
                    model=m,
                    contents=json.dumps(payload, ensure_ascii=False),
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=SCHEMA,
                        thinking_config=types.ThinkingConfig(thinking_level=thinking) if thinking else None,
                    ),
                )
                u = resp.usage_metadata
                print(f"[translate] {m} {n}문장 {time.time()-t:.1f}s (총 {time.time()-t0:.1f}s, 시도 {attempt+1}"
                      f"{', 대체' if m != model else ''}) 생각={getattr(u, 'thoughts_token_count', None)} 출력={u.candidates_token_count}", flush=True)
                return parse_translations(resp.text)
            except errors.APIError as e:
                last = e
                print(f"[translate] {m} {e.code} (시도 {attempt+1}, {time.time()-t:.1f}s)", flush=True)
                if e.code == 429:          # 이 모델 오늘 한도 끝 → 기다려봤자 소용없으니 다음 모델로
                    break
                if e.code < 500:           # 그 외 4xx는 우리 요청 문제 → 그대로 에러
                    raise
                if attempt < retries:
                    time.sleep(2 ** (attempt + 1))
    raise last


def request_translations(lines):
    payload = {
        "source_language": "Japanese",
        "target_language": "Korean",
        "context": [],
        "segments": [{"id": t["id"], "text": t["word"]} for t in lines],
    }
    return ask(MODEL, PROMPT, payload)


#번역 1번. 재요청 없음 — 모델이 빼먹은 문장은 원문 그대로 둔다 (koharu와 동일). 개수는 로그로만 알림
def translate_lines(lines):
    out = request_translations(lines)
    missing = [t for t in lines if not out.get(t["id"], "").strip()]
    leftover = [t for t in lines if JAPANESE.search(out.get(t["id"], ""))]
    print(f"[translate] 빠진 문장 {len(missing)}, 일본어 남은 문장 {len(leftover)} / {len(lines)}", flush=True)
    for t in missing:
        out[t["id"]] = t["word"]
    return out
