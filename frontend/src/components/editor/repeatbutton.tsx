import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

//자동 넘기기: 왼쪽 버튼 = 시작/정지, 오른쪽 화살표 = 간격(초)과 구간(start page ~ end page) 입력
//돌아가는 동안 interval 초마다 다음 페이지로 가고, end 를 지나면 start 로 돌아온다
export function RepeatButton({
  pages,
  selectedPage,
  onGo,
}: {
  pages: string[];
  selectedPage: string | null;
  onGo: (page: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState(false);
  //입력칸은 문자열로 둔다 (지우고 다시 치는 동안 값이 되돌아가지 않게). 숫자는 쓸 때만 읽는다
  const [intervalStr, setIntervalStr] = useState("3");
  const [startStr, setStartStr] = useState("1");
  const [endStr, setEndStr] = useState(String(pages.length));
  const num = (v: string, fallback: number) => {
    const n = Number(v);
    return v.trim() !== "" && Number.isFinite(n) && n > 0 ? n : fallback;
  };
  const interval = num(intervalStr, 3);
  const start = Math.min(pages.length, Math.max(1, Math.round(num(startStr, 1))));
  const end = Math.min(pages.length, Math.max(1, Math.round(num(endStr, pages.length))));
  const box = useRef<HTMLDivElement>(null);
  const selectedRef = useRef(selectedPage);
  selectedRef.current = selectedPage;

  //페이지 수가 바뀌면 끝 페이지를 맞춘다
  useEffect(() => setEndStr(String(pages.length)), [pages.length]);

  //바깥 클릭하면 닫기
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  //반복 타이머
  useEffect(() => {
    if (!running || !pages.length) return;
    const lo = Math.max(1, Math.min(start, end)) - 1;
    const hi = Math.min(pages.length, Math.max(start, end)) - 1;
    const tick = () => {
      const i = selectedRef.current ? pages.indexOf(selectedRef.current) : -1;
      const next = i < lo || i >= hi ? lo : i + 1; //구간 밖이거나 끝이면 start 로
      onGo(pages[next]);
    };
    const id = window.setInterval(tick, Math.max(0.2, interval) * 1000);
    return () => window.clearInterval(id);
  }, [running, interval, start, end, pages, onGo]);

  const field = "h-7 w-20 rounded-md border bg-background px-2 text-right text-xs outline-none focus:border-primary focus:ring-2 focus:ring-primary/20";

  return (
    <div ref={box} className="relative flex">
      <Button
        size="sm"
        variant={running ? "default" : "outline"}
        className="min-w-20 rounded-r-none"
        onClick={() => setRunning(!running)}
        title={running ? "Stop" : "Auto-advance pages"}
      >
        {running ? "■ STOP" : "▶ REPEAT"}
      </Button>
      <Button size="sm" variant={running ? "default" : "outline"} className="rounded-l-none border-l-0 px-1.5" onClick={() => setOpen(!open)} title="Repeat settings">
        ▾
      </Button>
      {open && (
        <div className="absolute right-0 top-8 z-50 w-56 rounded-lg border bg-popover p-3 text-xs shadow-xl">
          <label className="flex items-center justify-between gap-2">
            <span>Interval</span>
            <span className="flex items-center gap-1">
              <input className={field} type="number" min={0.2} step={0.5} value={intervalStr} onChange={(e) => setIntervalStr(e.target.value)} />
              <span className="text-muted-foreground">sec</span>
            </span>
          </label>
          <label className="mt-2 flex items-center justify-between gap-2">
            <span>Start</span>
            <span className="flex items-center gap-1">
              <input className={field} type="number" min={1} max={pages.length} value={startStr} onChange={(e) => setStartStr(e.target.value)} />
              <span className="text-muted-foreground">page</span>
            </span>
          </label>
          <label className="mt-2 flex items-center justify-between gap-2">
            <span>End</span>
            <span className="flex items-center gap-1">
              <input className={field} type="number" min={1} max={pages.length} value={endStr} onChange={(e) => setEndStr(e.target.value)} />
              <span className="text-muted-foreground">page</span>
            </span>
          </label>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Every {interval}s · page {Math.min(start, end)} → {Math.max(start, end)} · loops
          </p>
        </div>
      )}
    </div>
  );
}
