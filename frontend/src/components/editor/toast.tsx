import { useEffect } from "react";

//코하루식 알림: 오른쪽 위에 제목 + 설명 카드. 에러는 사용자가 닫을 때까지, 그 외는 몇 초 뒤 사라짐
export type Toast = { id: number; kind: "error" | "info"; title: string; description?: string };

//에러를 사람이 읽을 문장으로. okJson 이 던지는 메시지는 "<HTTP 코드> <본문>" 꼴이라 코드로 종류를 나눈다
export function describeError(e: unknown): { title: string; description: string } {
  const msg = e instanceof Error ? e.message : String(e);
  const code = Number(msg.match(/^(\d{3})\b/)?.[1]);
  const body = msg.replace(/^\d{3}\s*/, "").replace(/^\{"detail":"(.*)"\}$/s, "$1");
  if (e instanceof DOMException && e.name === "AbortError") {
    return { title: "The translation took too long", description: "We waited 3 minutes and got no answer. Check your internet connection, or choose a faster model in Settings → Models and try again." };
  }
  if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
    return { title: "Can't reach the app server", description: "The local server isn't running. Start it and try again." };
  }
  if (code === 429 || /RESOURCE_EXHAUSTED|quota/i.test(body)) {
    return { title: "Daily limit reached", description: "You've used up today's free requests for this model. Choose a different model in Settings → Models, or try again tomorrow." };
  }
  if (code === 400 && /API key/i.test(body)) {
    return { title: "API key doesn't work", description: "The key you entered was rejected. Check it in Settings → Models. You can get a new one at aistudio.google.com/apikey." };
  }
  if (code === 400 && /key is required/i.test(body)) {
    return { title: "API key needed", description: "Add your Gemini API key in Settings → Models to translate." };
  }
  if (code === 503 || code === 502) {
    return { title: "Translation service is busy", description: "Gemini is overloaded right now. Wait a minute and try again." };
  }
  if (code === 404 && /model/i.test(body)) {
    return { title: "Model not available", description: "This model can't be used with your key. Pick another one in Settings → Models." };
  }
  return { title: "Something went wrong", description: body || msg };
}

export function Toasts({ items, onClose }: { items: Toast[]; onClose: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed right-4 top-14 z-[60] flex w-80 flex-col gap-2">
      {items.map((t) => (
        <ToastCard key={t.id} toast={t} onClose={() => onClose(t.id)} />
      ))}
    </div>
  );
}

function ToastCard({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  //info 는 4초 뒤 자동으로 닫힘, error 는 직접 닫을 때까지
  useEffect(() => {
    if (toast.kind === "error") return;
    const id = window.setTimeout(onClose, 4000);
    return () => window.clearTimeout(id);
  }, [toast.kind, onClose]);

  const error = toast.kind === "error";
  return (
    <div className={`pointer-events-auto rounded-xl border bg-background p-3 shadow-xl ${error ? "border-destructive/40" : "border-border"}`}>
      <div className="flex items-start gap-2">
        <span className={`mt-0.5 text-sm ${error ? "text-destructive" : "text-primary"}`}>{error ? "⚠" : "ℹ"}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{toast.title}</p>
          {toast.description && <p className="mt-0.5 break-words text-xs text-muted-foreground">{toast.description}</p>}
        </div>
        <button className="rounded px-1 text-xs text-muted-foreground hover:bg-muted" onClick={onClose} title="Dismiss">✕</button>
      </div>
    </div>
  );
}
