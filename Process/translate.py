import os, json
from google import genai
from google.genai import types

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
def translate_lines(lines):
    payload = {
        "source_language": "Japanese",
        "target_language": "Korean",
        "context": [],
        "segments": [{"id": t["id"], "text": t["word"]} for t in lines],
    }
    resp = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=json.dumps(payload, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=PROMPT,
            response_mime_type="application/json",
            response_schema=SCHEMA,
        ),
    )
    return parse_translations(resp.text)
