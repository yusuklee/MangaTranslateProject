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
        ),
    )
    data = json.loads(resp.text)
    return {r["id"]: r["text"] for r in data["translations"]}
