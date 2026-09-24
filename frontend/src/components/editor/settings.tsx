import { memo, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FontPicker } from "./fontpicker";
import type { FontChoice } from "../../Project";

//설정 창 (오른쪽 아래 ⚙ SETTINGS 버튼으로 연다). 코하루처럼 왼쪽에 영역 탭, 오른쪽에 그 영역의 설정
type InpaintModel = "inpaint_normal" | "inpaint_lama" | "inpaint_flux";
type Lang = string; //Gemini 에 그대로 넘기는 영어 언어명

//calls: 번역 API 호출 횟수. "auto" = 30페이지당 1번 (150페이지면 5번), 숫자 = 그 횟수로 문장을 나눠 보냄
//apiKey: 사용자의 Gemini 키. 브라우저 localStorage 에만 저장되고 요청 헤더로 백엔드에 전달된다 (비어 있으면 서버 .env 키)
//onomatopoeia: 의성어(효과음) 상자도 글자로 잡아 번역할지. RF-DETR 가 text 와 onomatopoeia 를 같이 뽑으니 포함 여부만 고른다
export type AppSettings = { source: Lang; target: Lang; inpaintModel: InpaintModel; model: string; calls: "auto" | number; apiKey: string; onomatopoeia: boolean };
export const DEFAULT_SETTINGS: AppSettings = { source: "Japanese", target: "Korean", inpaintModel: "inpaint_lama", model: "gemini-3.6-flash", calls: "auto", apiKey: "", onomatopoeia: false };
export const PAGES_PER_CALL = 30;
const CALL_PRESETS = ["auto", 1, 2, 5] as const;

//설정은 브라우저 localStorage 에 남긴다 (앱을 껐다 켜도 유지). API 키는 따로 저장
const SETTINGS_STORAGE = "manga_settings";
export const loadSettings = (): Partial<AppSettings> & { fontFamily?: string } => {
  try { return JSON.parse(localStorage.getItem(SETTINGS_STORAGE) ?? "{}"); } catch { return {}; }
};
export const saveSettings = (s: AppSettings, fontFamily: string) => {
  try {
    const { apiKey: _k, ...rest } = s;
    localStorage.setItem(SETTINGS_STORAGE, JSON.stringify({ ...rest, fontFamily }));
  } catch { /* 저장 못 해도 동작엔 지장 없음 */ }
};

const KEY_STORAGE = "gemini_api_key";
export const loadApiKey = () => { try { return localStorage.getItem(KEY_STORAGE) ?? ""; } catch { return ""; } };
const saveApiKey = (k: string) => { try { k ? localStorage.setItem(KEY_STORAGE, k) : localStorage.removeItem(KEY_STORAGE); } catch { /* 저장 못 해도 동작엔 지장 없음 */ } };

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

export const SettingsDialog = memo(function SettingsDialog({
  open,
  settings,
  models,
  fluxAvailable = true,
  fonts,
  font,
  onFont,
  onChange,
  onClose,
}: {
  open: boolean;
  settings: AppSettings;
  models: string[]; //백엔드(/gemini_models)가 준 목록
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
  const [showKey, setShowKey] = useState(false);

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
                  <select className={`${selectCls} w-64`} value={settings.model} onChange={(e) => set({ model: e.target.value })}>
                    {(models.length ? models : [settings.model]).map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <p className="mb-1 mt-3 text-[11px] font-medium text-muted-foreground">API key</p>
                  <div className="flex items-center gap-1">
                    <input
                      className={`${selectCls} w-0 min-w-0 flex-1 font-mono`}
                      type={showKey ? "text" : "password"}
                      placeholder="AIza..."
                      autoComplete="off"
                      spellCheck={false}
                      value={settings.apiKey}
                      onChange={(e) => { const k = e.target.value.trim(); saveApiKey(k); set({ apiKey: k }); }}
                    />
                    <button className="h-8 shrink-0 rounded-lg border px-2 text-xs hover:bg-muted" onClick={() => setShowKey(!showKey)} title={showKey ? "Hide" : "Show"}>
                      {showKey ? "Hide" : "Show"}
                    </button>
                  </div>
                  <p className="mt-1.5 text-[11px] text-muted-foreground">
                    Stored only in this browser, sent to your local backend. Empty = server default key. Get one at{" "}
                    <a className="underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">aistudio.google.com/apikey</a>
                  </p>
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
            <Button size="sm" onClick={onClose}>OK</Button>
          </div>
        </div>
      </div>
    </div>
  );
});
