import { memo, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { API } from "@/api";
import { FontPicker } from "./fontpicker";
import type { FontChoice } from "../../Project";

//설정 창 (오른쪽 아래 ⚙ SETTINGS 버튼으로 연다). 코하루처럼 왼쪽에 영역 탭, 오른쪽에 그 영역의 설정
type InpaintModel = "inpaint_normal" | "inpaint_lama" | "inpaint_flux";
type Lang = string; //Gemini 에 그대로 넘기는 영어 언어명

//calls: 번역 API 호출 횟수. "auto" = 30페이지당 1번 (150페이지면 5번), 숫자 = 그 횟수로 문장을 나눠 보냄
//apiKey: 사용자의 Gemini 키. 브라우저 localStorage 에만 저장되고 요청 헤더로 백엔드에 전달된다 (비어 있으면 서버 .env 키)
//onomatopoeia: 의성어(효과음) 상자도 글자로 잡아 번역할지. RF-DETR 가 text 와 onomatopoeia 를 같이 뽑으니 포함 여부만 고른다
//provider: 번역 API. model·apiKey 는 Gemini, gptModel·gptKey 는 ChatGPT, claudeModel·claudeKey 는 Claude,
//openaiUrl·openaiModel·openaiKey 는 사용자가 직접 등록하는 OpenAI 방식 API (Ollama·LM Studio, Cohere, DeepSeek 등),
//localModel 은 앱이 직접 받아 이 PC 에서 돌리는 모델 (백엔드 Process/local_llm.py)
//키들은 설정과 따로 localStorage 에 저장한다
export type Provider = "gemini" | "chatgpt" | "claude" | "openai" | "local";
export type AppSettings = {
  source: Lang; target: Lang; inpaintModel: InpaintModel; calls: "auto" | number; onomatopoeia: boolean;
  provider: Provider; model: string; gptModel: string; claudeModel: string; openaiUrl: string; openaiModel: string; localModel: string;
  apiKey: string; gptKey: string; claudeKey: string; openaiKey: string;
};

//Gemini 는 Gemini SDK 로 (503 이면 대체 모델). ChatGPT·Claude·OpenAI·Local 은 OpenAI 방식(/chat/completions) 으로 보낸다
export const PROVIDERS: Record<Provider, { label: string; url: string; models: string[]; keyUrl: string }> = {
  gemini: { label: "Gemini", url: "", models: ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"], keyUrl: "https://aistudio.google.com/apikey" },
  chatgpt: { label: "ChatGPT", url: "https://api.openai.com/v1", models: ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra"], keyUrl: "https://platform.openai.com/api-keys" },
  claude: { label: "Claude", url: "https://api.anthropic.com/v1", models: ["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5-5", "claude-fable-5-1"], keyUrl: "https://platform.claude.com/settings/keys" },
  openai: { label: "OpenAI", url: "", models: [], keyUrl: "" },
  local: { label: "Local", url: "", models: [], keyUrl: "" },
};
//provider 별로 쓰는 설정 칸
const FIELDS = {
  gemini: { model: "model", key: "apiKey" },
  chatgpt: { model: "gptModel", key: "gptKey" },
  claude: { model: "claudeModel", key: "claudeKey" },
} as const;

//Local 모델 (코하루에 있던 것). 처음 번역할 때 백엔드가 받는다. id 는 백엔드 local_llm.MODELS 와 같아야 한다
export const LOCAL_MODELS: { id: string; name: string; size: string }[] = [
  { id: "qwen3.5-9b", name: "Qwen 3.5 9B", size: "5.7 GB" },
  { id: "qwen3.5-9b-uncensored", name: "Qwen 3.5 9B Uncensored", size: "5.6 GB" },
  { id: "qwen3.6-27b-uncensored", name: "Qwen 3.6 27B Uncensored", size: "15 GB" },
  { id: "qwen3.6-35b-a3b-uncensored", name: "Qwen 3.6 35B A3B Uncensored", size: "23 GB" },
  { id: "vntl-llama3-8b", name: "VNTL Llama 3 8B v2", size: "5.7 GB" },
  { id: "gemma4-e2b-it", name: "Gemma 4 E2B Instruct", size: "2.6 GB" },
  { id: "gemma4-e4b-it", name: "Gemma 4 E4B Instruct", size: "4.2 GB" },
  { id: "gemma4-12b-it", name: "Gemma 4 12B Instruct", size: "6.7 GB" },
  { id: "gemma4-26b-a4b-it", name: "Gemma 4 26B A4B Instruct", size: "14 GB" },
  { id: "gemma4-31b-it", name: "Gemma 4 31B Instruct", size: "17 GB" },
];

export const DEFAULT_SETTINGS: AppSettings = {
  source: "Japanese", target: "Korean", inpaintModel: "inpaint_lama", calls: "auto", onomatopoeia: false,
  provider: "gemini", model: "gemini-3.6-flash", gptModel: "gpt-6-luna", claudeModel: "claude-haiku-4-5-20251001", openaiUrl: "", openaiModel: "", localModel: "gemma4-12b-it",
  apiKey: "", gptKey: "", claudeKey: "", openaiKey: "",
};

//번역 요청에 넣을 모델·주소·키 헤더. local 이면 백엔드가 띄운 llama-server, baseUrl 도 local 도 없으면 Gemini
export const translateTarget = (s: AppSettings): { model: string; baseUrl?: string; local?: boolean; headers: Record<string, string> } => {
  const key = (k: string, h = "X-Api-Key"): Record<string, string> => (k ? { [h]: k } : {});
  if (s.provider === "chatgpt") return { model: s.gptModel, baseUrl: PROVIDERS.chatgpt.url, headers: key(s.gptKey) };
  if (s.provider === "claude") return { model: s.claudeModel, baseUrl: PROVIDERS.claude.url, headers: key(s.claudeKey) };
  if (s.provider === "openai") return { model: s.openaiModel, baseUrl: s.openaiUrl, headers: key(s.openaiKey) };
  if (s.provider === "local") return { model: s.localModel, local: true, headers: {} };
  return { model: s.model, headers: key(s.apiKey, "X-Gemini-Key") };
};
export const PAGES_PER_CALL = 20;
const CALL_PRESETS = ["auto", 1, 2, 5] as const;

//설정은 브라우저 localStorage 에 남긴다 (앱을 껐다 켜도 유지). API 키는 따로 저장
const SETTINGS_STORAGE = "manga_settings";
export const loadSettings = (): Partial<AppSettings> & { fontFamily?: string } => {
  try { return JSON.parse(localStorage.getItem(SETTINGS_STORAGE) ?? "{}"); } catch { return {}; }
};
export const saveSettings = (s: AppSettings, fontFamily: string) => {
  try {
    const { apiKey: _k, gptKey: _g, claudeKey: _c, openaiKey: _o, ...rest } = s;
    localStorage.setItem(SETTINGS_STORAGE, JSON.stringify({ ...rest, fontFamily }));
  } catch { /* 저장 못 해도 동작엔 지장 없음 */ }
};

//키 저장 이름: gemini_api_key, chatgpt_api_key, claude_api_key, openai_api_key
export const loadKey = (p: Provider) => { try { return localStorage.getItem(`${p}_api_key`) ?? ""; } catch { return ""; } };
const saveKey = (p: Provider, k: string) => { try { k ? localStorage.setItem(`${p}_api_key`, k) : localStorage.removeItem(`${p}_api_key`); } catch { /* 저장 못 해도 동작엔 지장 없음 */ } };

//OK 버튼: 키를 백엔드로 보내 .env 에 저장 (앱을 껐다 켜도 서버가 이 키를 쓴다)
const postApiKey = async (k: string) => {
  const body = new FormData();
  body.append("api_key", k);
  const r = await fetch(`${API}/api_key`, { method: "POST", body });
  if (!r.ok) throw new Error(`${r.status}`);
};

//Show/Hide 버튼용 눈 아이콘 (off = 사선)
function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
      {off && <line x1="3" y1="3" x2="21" y2="21" />}
    </svg>
  );
}

const INPAINT_MODELS: { value: InpaintModel; label: string; hint: string }[] = [
  { value: "inpaint_normal", label: "None", hint: "Fill text areas with white. Fastest." },
  { value: "inpaint_lama", label: "LaMa", hint: "AI inpainting. Good for most pages." },
  { value: "inpaint_flux", label: "FLUX", hint: "Diffusion inpainting. Slow, best quality." },
];

//Gemini 는 언어를 가리지 않으니 넉넉히. 값 = 표시 = 영어 이름
const LANGS: Lang[] = [
  "Japanese", "Korean", "English", "Chinese (Simplified)", "Chinese (Traditional)",
  "Spanish", "French", "German", "Italian", "Portuguese", "Russian", "Ukrainian", "Polish", "Dutch",
  "Swedish", "Norwegian", "Danish", "Finnish", "Czech", "Hungarian", "Romanian", "Greek", "Turkish",
  "Arabic", "Hebrew", "Persian", "Hindi", "Bengali", "Urdu", "Tamil",
  "Vietnamese", "Thai", "Indonesian", "Malay", "Filipino", "Burmese", "Khmer", "Mongolian",
];

type Tab = "language" | "models";
const TABS: { id: Tab; label: string }[] = [
  { id: "language", label: "Language" },
  { id: "models", label: "Models" },
];

const selectCls = "h-8 rounded-lg border bg-background px-2 text-sm outline-none hover:bg-muted focus:border-primary focus:ring-2 focus:ring-primary/20";

//영역 안의 한 묶음: 제목 + 설명 + 내용
function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="border-b py-4 first:pt-0 last:border-b-0">
      <h3 className="text-sm font-semibold">{title}</h3>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

//한 줄 설정: 왼쪽 라벨, 오른쪽 입력
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-4 py-1.5 text-sm">
      <span>{label}</span>
      <span className="flex min-w-0 items-center gap-1">{children}</span>
    </label>
  );
}

//API 키 입력칸 + Show/Hide
function KeyInput({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (k: string) => void }) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex items-center gap-1">
      <input
        className={`${selectCls} w-64 min-w-0 font-mono`}
        type={show ? "text" : "password"}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value.trim())}
      />
      <button className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border hover:bg-muted" onClick={() => setShow(!show)} title={show ? "Hide" : "Show"}>
        <EyeIcon off={show} />
      </button>
    </div>
  );
}

export const SettingsDialog = memo(function SettingsDialog({
  open,
  settings,
  fluxAvailable = true,
  fonts,
  font,
  onFont,
  onChange,
  onClose,
}: {
  open: boolean;
  settings: AppSettings;
  fluxAvailable?: boolean; //false 면 FLUX 를 목록에서 뺀다 (앱 빌드)
  fonts: FontChoice[]; //렌더 글꼴 선택지
  font: FontChoice;
  onFont: (f: FontChoice) => void;
  onChange: (s: AppSettings) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("language");
  const [customCalls, setCustomCalls] = useState(typeof settings.calls === "number" && !CALL_PRESETS.includes(settings.calls as never));
  const [customStr, setCustomStr] = useState(typeof settings.calls === "number" ? String(settings.calls) : "3");

  //Esc 로 닫기
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const set = (patch: Partial<AppSettings>) => onChange({ ...settings, ...patch });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onMouseDown={onClose}>
      <div className="flex h-[30rem] w-[42rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border bg-background shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        {/* 왼쪽: 영역 탭 */}
        <aside className="flex w-40 shrink-0 flex-col border-r bg-muted/40 p-2">
          <div className="px-2 py-2 text-[11px] font-semibold tracking-wide text-muted-foreground">SETTINGS</div>
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`rounded-lg px-3 py-2 text-left text-sm transition-colors ${tab === t.id ? "bg-accent font-medium text-accent-foreground" : "hover:bg-muted"}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
          <div className="mt-auto px-2 pb-1 text-[10px] text-muted-foreground">Esc to close</div>
        </aside>

        {/* 오른쪽: 내용 */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-11 shrink-0 items-center justify-between border-b px-5">
            <h2 className="text-sm font-semibold">{TABS.find((t) => t.id === tab)?.label}</h2>
            <button className="rounded px-1.5 text-muted-foreground hover:bg-muted" onClick={onClose} title="Close">✕</button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5">
            {tab === "language" && (
              <Section title="Translation direction">
                <div className="flex items-end gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="mb-1 text-[11px] font-medium text-muted-foreground">Source</p>
                    <select className={`${selectCls} w-full`} value={settings.source} onChange={(e) => set({ source: e.target.value })}>
                      {LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                    </select>
                  </div>
                  <button
                    className="h-8 shrink-0 rounded-lg border px-2 text-xs hover:bg-muted"
                    onClick={() => set({ source: settings.target, target: settings.source })}
                    title="Swap"
                  >
                    ⇄
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="mb-1 text-[11px] font-medium text-muted-foreground">Target</p>
                    <select className={`${selectCls} w-full`} value={settings.target} onChange={(e) => set({ target: e.target.value })}>
                      {LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                    </select>
                  </div>
                </div>
              </Section>
            )}
            {tab === "language" && (
              <Section title="Detect">
                <label className="flex items-center gap-2 py-1 text-sm">
                  <input type="checkbox" checked disabled className="accent-primary" />
                  <span>Text</span>
                  <span className="text-[11px] text-muted-foreground">(dialogue, narration)</span>
                </label>
                <label className="flex items-center gap-2 py-1 text-sm">
                  <input type="checkbox" className="accent-primary" checked={settings.onomatopoeia} onChange={(e) => set({ onomatopoeia: e.target.checked })} />
                  <span>Onomatopoeia</span>
                  <span className="text-[11px] text-muted-foreground">(sound effects)</span>
                </label>
              </Section>
            )}
            {tab === "language" && (
              <Section title="Font" hint="Font used to draw the translated text. Bundled fonts come from the backend; the default is a system font.">
                <FontPicker fonts={fonts} value={font} onChange={onFont} inline />
              </Section>
            )}

            {tab === "models" && (
              <>
                <Section title="Inpainting model">
                  <select className={`${selectCls} w-40`} value={settings.inpaintModel} onChange={(e) => set({ inpaintModel: e.target.value as InpaintModel })}>
                    {INPAINT_MODELS.filter((m) => fluxAvailable || m.value !== "inpaint_flux").map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                  </select>
                </Section>
                <Section title="Translation model">
                  <Row label="Provider">
                    <select className={`${selectCls} w-64`} value={settings.provider} onChange={(e) => set({ provider: e.target.value as Provider })}>
                      {(Object.keys(PROVIDERS) as Provider[]).map((p) => <option key={p} value={p}>{PROVIDERS[p].label}</option>)}
                    </select>
                  </Row>
                  {settings.provider === "local" ? (
                    <>
                      <Row label="Model">
                        <select className={`${selectCls} w-64`} value={settings.localModel} onChange={(e) => set({ localModel: e.target.value })}>
                          {LOCAL_MODELS.map((m) => <option key={m.id} value={m.id}>{m.name}{m.size && ` (${m.size})`}</option>)}
                        </select>
                      </Row>
                      <p className="mt-1.5 text-[11px] text-muted-foreground">
                        Runs on this PC's GPU with llama.cpp. The model is downloaded the first time you translate (several GB) and kept in the app folder.
                      </p>
                    </>
                  ) : settings.provider === "openai" ? (
                    <>
                      <Row label="Base URL">
                        <input className={`${selectCls} w-64 min-w-0 font-mono`} placeholder="http://localhost:11434/v1" spellCheck={false} value={settings.openaiUrl} onChange={(e) => set({ openaiUrl: e.target.value.trim() })} />
                      </Row>
                      <Row label="Model">
                        <input className={`${selectCls} w-64 min-w-0 font-mono`} placeholder="e.g. qwen3:8b" spellCheck={false} value={settings.openaiModel} onChange={(e) => set({ openaiModel: e.target.value.trim() })} />
                      </Row>
                      <p className="mb-1 mt-3 text-[11px] font-medium text-muted-foreground">API key</p>
                      <KeyInput value={settings.openaiKey} placeholder="optional" onChange={(k) => { saveKey("openai", k); set({ openaiKey: k }); }} />
                      <p className="mt-1.5 text-[11px] text-muted-foreground">
                        Any OpenAI-compatible /chat/completions API: a server on this PC (Ollama, LM Studio, llama.cpp) or a cloud API. Leave the key empty if not needed.
                      </p>
                    </>
                  ) : (() => {
                    const p = settings.provider;
                    const f = FIELDS[p];
                    return (
                      <>
                        {PROVIDERS[p].url && (
                          <Row label="Base URL">
                            <input className={`${selectCls} w-64 min-w-0 font-mono opacity-60`} value={PROVIDERS[p].url} readOnly />
                          </Row>
                        )}
                        <Row label="Model">
                          <select className={`${selectCls} w-64`} value={settings[f.model]} onChange={(e) => set({ [f.model]: e.target.value })}>
                            {PROVIDERS[p].models.map((m) => <option key={m} value={m}>{m}</option>)}
                          </select>
                        </Row>
                        <p className="mb-1 mt-3 text-[11px] font-medium text-muted-foreground">API key</p>
                        <KeyInput value={settings[f.key]} placeholder={p === "gemini" ? "AIza..." : "sk-..."} onChange={(k) => { saveKey(p, k); set({ [f.key]: k }); }} />
                        <p className="mt-1.5 text-[11px] text-muted-foreground">
                          Stored only in this browser, sent to your local backend.{p === "gemini" && " Empty = server default key."} Get one at{" "}
                          <a className="underline" href={PROVIDERS[p].keyUrl} target="_blank" rel="noreferrer">{PROVIDERS[p].keyUrl.replace("https://", "")}</a>
                        </p>
                      </>
                    );
                  })()}
                  <Row label="API calls">
                    <select
                      className={selectCls}
                      value={customCalls ? "custom" : String(settings.calls)}
                      onChange={(e) => {
                        const v = e.target.value;
                        if (v === "custom") { setCustomCalls(true); set({ calls: Math.max(1, Number(customStr) || 1) }); }
                        else { setCustomCalls(false); set({ calls: v === "auto" ? "auto" : Number(v) }); }
                      }}
                    >
                      {CALL_PRESETS.map((c) => <option key={String(c)} value={String(c)}>{c === "auto" ? "auto" : String(c)}</option>)}
                      <option value="custom">custom</option>
                    </select>
                    {customCalls && (
                      <input
                        className={`${selectCls} w-16 text-right`}
                        type="number"
                        min={1}
                        value={customStr}
                        onChange={(e) => { setCustomStr(e.target.value); const n = Number(e.target.value); if (n >= 1) set({ calls: Math.round(n) }); }}
                      />
                    )}
                  </Row>
                  <p className="text-[11px] text-muted-foreground">
                    How many API calls PROCESS ALL uses. 1 = send all text in one call, 2 = split it into two calls. auto = 1 call per {PAGES_PER_CALL} pages.
                  </p>
                </Section>
              </>
            )}
          </div>
          <div className="flex h-12 shrink-0 items-center justify-end border-t px-5">
            <Button size="sm" onClick={() => { if (settings.apiKey) postApiKey(settings.apiKey).catch(() => {}); onClose(); }}>OK</Button>
          </div>
        </div>
      </div>
    </div>
  );
});
