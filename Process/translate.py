import os, json, re, time, zipfile, subprocess, threading, atexit
import requests
from google import genai
from google.genai import types, errors

#{source}/{target} 자리에 설정에서 고른 언어가 들어간다
PROMPT = """You are a professional manga translator.

  Translation requirements:
  - Translate every input segment from {source} into natural {target}.
  - Preserve meaning, character voice, emotional tone, relationship nuance, emphasis, and sound effects.
  - Localize idioms and sound effects naturally while keeping wording concise enough for speech bubbles.
  - Use surrounding segments only for disambiguation and continuity; never merge or split segments.
  - Write every translated `text` value only in {target}; do not include source text, notes, explanations, or alternatives.
  - Never preserve or repeat original-language text; translate names, terms, and sound effects using natural {target}
  conventions.
  - Translate only the {source} parts. Leave words in other languages or scripts (e.g. "TikTok", brand names, usernames)
  exactly as written.

  Output requirements:
  - Each input segment has a numeric `id`.
  - Return only a JSON object whose `translations` array contains one object with `id` and translated `text` for every input
  segment.
  - Copy every input ID exactly once; order does not matter.
  - Never merge, split, omit, duplicate, or add segments."""


#응답 형태를 고정
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


#사용자 키(설정 창) 우선, 없으면 .env 의 GEMINI_API_KEY. 키마다 클라이언트를 하나씩 만들어 재사용
_clients = {}
def get_client(api_key=None):
    key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise ValueError("Gemini API key is required. Enter it in Settings → API key.")
    if key not in _clients:
        _clients[key] = genai.Client(api_key=key)
    return _clients[key]


JAPANESE = re.compile(r"[ぁ-んァ-ヶ一-龯]")   # 가나·한자가 번역문에 남았는지 검사용

#설정 창에 보여줄 모델 목록: API 에서 받아 텍스트 모델만 남긴다 (image/tts/transcribe 등 제외). 한 번 받으면 캐시
MODEL = os.environ.get("TRANSLATE_MODEL", "gemini-3.6-flash")          # 바로 번역, 검토 없음
THINKING = None                                                         # None = 모델 기본 생각 수준(보통). "minimal" 은 빨랐지만 번역이 거칠고, 지원 안 하는 모델도 있다
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]        # 503(과부하)·429(일일 한도)면 순서대로 대체


#503이면 2·4·8초 쉬고 재시도, 429(한도 초과)면 바로 다음 모델. 전부 실패하면 마지막 에러를 던진다
def ask(model, system, payload, retries=1, thinking=THINKING, api_key=None):   # 5xx 는 1번만 더 해 보고(2초 뒤) 다음 모델로. 3번 재시도는 대체까지 37초 걸렸다
    client = get_client(api_key)
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
                if e.code == 400 and thinking and "thinking" in str(e.message).lower():   # 이 모델이 그 생각 수준을 안 받음 → 기본값으로 다시
                    thinking = None
                    continue
                if e.code < 500:           # 그 외 4xx는 우리 요청 문제 → 그대로 에러
                    raise
                if attempt < retries:
                    time.sleep(2 ** (attempt + 1))
    #전부 실패: 429 면 어떤 모델들을 시도했는지 붙여서 알려준다 (프런트가 사용자에게 보여줌)
    if isinstance(last, errors.APIError) and last.code == 429:
        raise errors.APIError(429, {"error": {"message": f"quota exceeded for {', '.join(candidates)}", "status": "RESOURCE_EXHAUSTED"}})
    raise last



#여러 모델들로 번역


#JSON 이 깨져 오면 (작은 모델) {"id": N, "text": "..."} 조각만 골라 읽는다
PAIR = re.compile(r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"text"\s*:\s*("(?:[^"\\]|\\.)*")')
def parse_loose(text):
    try:
        return parse_translations(text[text.find("{"):text.rfind("}") + 1])
    except ValueError:
        return {int(i): json.loads(t) for i, t in PAIR.findall(text)}


#SCHEMA 를 JSON Schema 표기로 (llama-server 가 이 형태로만 출력하게 강제)
JSON_SCHEMA = {"type": "object", "required": ["translations"], "properties": {"translations": {"type": "array", "items": {
    "type": "object", "required": ["id", "text"], "properties": {"id": {"type": "integer"}, "text": {"type": "string"}}}}}}


#ChatGPT·Claude·OpenAI(사용자 등록)·Local = OpenAI 방식(/chat/completions) API. 대체 모델 없이 1번만. model 이 비면 안 보낸다
#JSON 형식 강제는 곳마다 지원이 달라 Local(llama-server) 에만 쓴다. Local 은 느려서 기다리는 시간도 길게
def ask_openai(base_url, model, system, payload, api_key=None, local=False):
    t = time.time()
    try:
        r = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            json={**({"model": model} if model else {}),
                  **({"response_format": {"type": "json_schema", "json_schema": {"name": "translations", "schema": JSON_SCHEMA}}} if local else {}),
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]},
            timeout=880 if local else 170,
        )
    except requests.RequestException as e:
        raise errors.APIError(502, {"error": {"message": f"cannot reach {base_url}: {e}"}})
    if not r.ok:
        raise errors.APIError(r.status_code, {"error": {"message": r.text[:300]}})
    text = r.json()["choices"][0]["message"]["content"] or ""
    print(f"[translate] {model} {len(payload['segments'])}문장 {time.time()-t:.1f}s ({base_url})", flush=True)
    return parse_loose(text)





LLAMA_ZIP_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b11195/llama-b11195-bin-win-vulkan-x64.zip"
LLAMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llama")
GGUF_DIR = os.path.join(os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "gguf")
LLAMA_PORT = 8790
LLAMA_CONTEXT = 16384   # 요청 하나에 들어갈 토큰 수 (문장 + 번역문). -np 1 이라 요청은 줄 서서 하나씩

#이 PC 의 코하루가 받아 둔 Qwen·VNTL 5개 + 코하루 목록의 Gemma 4 5개. id: (HF 저장소, 파일). 프런트 LOCAL_MODELS 와 id 가 같아야 한다
LOCAL_MODELS = {
    "qwen3.5-9b": ("unsloth/Qwen3.5-9B-GGUF", "Qwen3.5-9B-Q4_K_M.gguf"),
    "qwen3.5-9b-uncensored": ("HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive", "Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"),
    "qwen3.6-27b-uncensored": ("HauhauCS/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive", "Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-IQ4_XS.gguf"),
    "qwen3.6-35b-a3b-uncensored": ("HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive", "Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"),
    "vntl-llama3-8b": ("lmg-anon/vntl-llama3-8b-v2-gguf", "vntl-llama3-8b-v2-hf-q5_k_m.gguf"),
    "gemma4-e2b-it": ("unsloth/gemma-4-E2B-it-qat-GGUF", "gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf"),
    "gemma4-e4b-it": ("unsloth/gemma-4-E4B-it-qat-GGUF", "gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"),
    "gemma4-12b-it": ("unsloth/gemma-4-12B-it-qat-GGUF", "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"),
    "gemma4-26b-a4b-it": ("unsloth/gemma-4-26B-A4B-it-qat-GGUF", "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"),
    "gemma4-31b-it": ("unsloth/gemma-4-31B-it-qat-GGUF", "gemma-4-31B-it-qat-UD-Q4_K_XL.gguf"),
}

local_status = {"state": "idle", "text": "", "done": 0, "total": 0}   # idle / downloading / starting / ready / error. 프런트가 진행 표시에 씀
_llama_proc = None
_llama_model = None
_llama_lock = threading.Lock()




def download(url, path, label):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        local_status.update(state="downloading", text=label, done=0, total=int(r.headers.get("content-length", 0)))
        with open(path + ".part", "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                local_status["done"] += len(chunk)
    os.replace(path + ".part", path)


#zip 에서 llama-server 에 필요한 것만 푼다 (llama-cli·bench·quantize 등 도구 exe 20개와 그 dll 은 안 씀)
#ggml-cpu-*.dll 은 CPU 종류별이라 전부 둔다 (실행할 때 이 PC CPU 에 맞는 것 하나를 고름)
LLAMA_KEEP = re.compile(r"^(llama-server\.exe|llama-server-impl\.dll|llama-common\.dll|llama\.dll|mtmd\.dll|ggml.*\.dll|libomp\.dll|LICENSE.*)$")

def llama_exe():
    exe = os.path.join(LLAMA_DIR, "llama-server.exe")
    if not os.path.exists(exe):
        z = os.path.join(LLAMA_DIR, "llama.zip")
        download(LLAMA_ZIP_URL, z, "llama.cpp")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(LLAMA_DIR, [n for n in zf.namelist() if LLAMA_KEEP.match(os.path.basename(n))])
        os.remove(z)
    return exe


def local_stop():
    global _llama_proc, _llama_model
    if _llama_proc and _llama_proc.poll() is None:
        _llama_proc.terminate()
        _llama_proc.wait(10)
    _llama_proc = _llama_model = None

atexit.register(local_stop)


def local_running(model_id):
    return _llama_model == model_id and _llama_proc is not None and _llama_proc.poll() is None


#그 모델로 llama-server 가 떠 있게 한다 (없으면 받고, 다른 모델이 떠 있으면 바꾼다). 이미 떠 있으면 바로 주소를 돌려줌
def local_ensure(model_id):
    global _llama_proc, _llama_model
    with _llama_lock:
        if local_running(model_id):
            return f"http://127.0.0.1:{LLAMA_PORT}/v1"
        try:
            repo, file = LOCAL_MODELS[model_id]
            exe = llama_exe()
            path = os.path.join(GGUF_DIR, file)
            download(f"https://huggingface.co/{repo}/resolve/main/{file}", path, file)
            local_stop()
            local_status.update(state="starting", text=model_id, done=0, total=0)
            log = open(os.path.join(LLAMA_DIR, "server.log"), "w", encoding="utf-8")
            #GPU 에 올릴 양은 llama-server 가 VRAM 에 맞춰 정한다 (--fit 기본 on, 넘치면 일부는 RAM). --reasoning-budget 0: 생각 끄기 (번역엔 느리기만 함)
            _llama_proc = subprocess.Popen([exe, "-m", path, "--host", "127.0.0.1", "--port", str(LLAMA_PORT), "-c", str(LLAMA_CONTEXT), "-np", "1",
                                            "--reasoning-budget", "0"], stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            t = time.time()
            while True:
                if _llama_proc.poll() is not None:
                    raise RuntimeError("llama-server stopped (see llama/server.log)")
                try:
                    if requests.get(f"http://127.0.0.1:{LLAMA_PORT}/health", timeout=2).ok:
                        break
                except requests.RequestException:
                    pass
                if time.time() - t > 300:
                    raise RuntimeError("llama-server did not start in 5 minutes")
                time.sleep(0.5)
            _llama_model = model_id
            local_status.update(state="ready", text=model_id)
            return f"http://127.0.0.1:{LLAMA_PORT}/v1"
        except Exception as e:
            local_status.update(state="error", text=str(e))
            raise


#프런트가 번역 전에 부른다: 바로 돌아가고, 받기·띄우기는 뒤에서. 진행은 local_status 로
def local_prepare(model_id):
    if model_id not in LOCAL_MODELS:
        raise ValueError(f"unknown local model: {model_id}")
    if local_running(model_id):
        local_status.update(state="ready", text=model_id)
        return
    local_status.update(state="starting", text=model_id, done=0, total=0)
    threading.Thread(target=lambda: local_ensure(model_id), daemon=True).start()


def request_translations(lines, source="Japanese", target="Korean", model=None, api_key=None, base_url=None, local=False):
    payload = {
        "source_language": source,
        "target_language": target,
        "context": [],
        "segments": [{"id": t["id"], "text": t["word"]} for t in lines],
    }
    system = PROMPT.format(source=source, target=target)
    if local:
        return ask_openai(local_ensure(model), model, system, payload, local=True)
    if base_url:
        return ask_openai(base_url, model, system, payload, api_key)
    return ask(model or MODEL, system, payload, api_key=api_key)


#번역 1번. 재요청 없음 — 모델이 빼먹은 문장은 원문 그대로 둔다 (koharu와 동일). 개수는 로그로만 알림
#Gemini: model 은 설정에서 고른 모델 (없으면 MODEL), 429/503 이면 FALLBACK_MODELS 로. base_url 이 있으면 그 OpenAI 방식 API, local 이면 llama-server
def translate_lines(lines, source="Japanese", target="Korean", model=None, api_key=None, base_url=None, local=False):
    out = request_translations(lines, source, target, model, api_key, base_url, local)
    missing = [t for t in lines if not out.get(t["id"], "").strip()]
    leftover = [t for t in lines if source == "Japanese" and JAPANESE.search(out.get(t["id"], ""))]
    print(f"[translate] {source}→{target} 빠진 문장 {len(missing)}, 원어 남은 문장 {len(leftover)} / {len(lines)}", flush=True)
    for t in missing:
        out[t["id"]] = t["word"]
    return out



