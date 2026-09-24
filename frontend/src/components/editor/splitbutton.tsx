import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

//왼쪽 = 고른 항목 이름, 누르면 실행. 오른쪽 짧은 화살표 = 항목 고르기 (고르기만 하고 실행은 안 함)
export function SplitButton<T extends string>({
  value,
  options,
  onSelect,
  onRun,
  suffix = "",
}: {
  value: T;
  options: { value: T; label: string }[];
  onSelect: (v: T) => void;
  onRun: () => void;
  suffix?: string; //라벨 뒤에 붙는 것 (예: " (3)")
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const current = options.find((o) => o.value === value) ?? options[0];

  //바깥 클릭하면 닫기
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div ref={box} className="relative flex">
      <Button size="sm" className="min-w-24 rounded-r-none" onClick={onRun}>
        {current.label}{suffix}
      </Button>
      <Button size="sm" className="rounded-l-none border-l border-white/30 px-1.5" onClick={() => setOpen(!open)} title="Choose step">
        ▾
      </Button>
      {open && (
        <div className="absolute right-0 top-8 z-50 w-40 rounded-lg border bg-popover p-1 shadow-xl">
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              className={`block w-full rounded-md px-3 py-1.5 text-left text-xs transition-colors hover:bg-muted ${
                o.value === value ? "bg-accent text-accent-foreground" : ""
              }`}
              onClick={() => {
                onSelect(o.value);
                setOpen(false);
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
