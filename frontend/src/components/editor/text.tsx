import { memo, useState } from "react";
import type { Content } from "../../Project";

//오른쪽 글자 목록. 항목을 누르면 원문과 번역문 입력칸이 펼쳐진다
export const Text = memo(function Text({
  contents,
  selectedArea,
  onSelect,
  onEdit,
  onCollapse,
}: {
  contents: Content[];
  selectedArea: string | null;
  onSelect: (key: string | null) => void;
  onEdit: (id: number, translated: string) => void; //번역문 직접 고치기 → 그림·내보내기에 반영
  onCollapse?: () => void; //패널 접기 (VS Code 사이드바처럼)
}) {
  const [openGroup, setOpenGroup] = useState(true);

  return (
    <div>
      <div className="flex h-9 items-center border-b pr-2 text-[11px] font-semibold tracking-wide text-muted-foreground">
        <button onClick={() => setOpenGroup(!openGroup)} className="flex h-full flex-1 items-center gap-2 px-3 hover:bg-muted">
          <span className="text-[9px]">{openGroup ? "▼" : "▶"}</span>
          <span>TEXT</span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">{contents.length}</span>
        </button>
        {onCollapse && (
          <button className="rounded px-1 text-[10px] hover:bg-muted" onClick={onCollapse} title="Collapse">▶</button>
        )}
      </div>

      {openGroup && (
        <div className="grid gap-1.5 p-2">
          {contents.length === 0 && (
            <div className="flex flex-col items-center gap-1 px-2 py-10 text-center">
              <span className="text-2xl">💬</span>
              <p className="text-sm font-medium text-muted-foreground">No detections</p>
            </div>
          )}
          {contents.map((c) => {
            const key = `${c.id}`;
            const open = selectedArea === key;
            return (
              <div
                key={c.id}
                onClick={() => onSelect(open ? null : key)}
                className={`cursor-pointer rounded-lg border p-2.5 transition-colors ${
                  open ? "border-primary bg-accent/60" : "border-border bg-background hover:bg-muted"
                }`}
              >
                <p className="text-sm leading-snug">{c.translated ?? c.word}</p>
                {open && (
                  <div className="mt-2 border-t pt-2">
                    <p className="text-[10px] font-medium text-muted-foreground">Source</p>
                    <p className="text-xs text-muted-foreground">{c.word}</p>
                    <p className="mt-2 text-[10px] font-medium text-muted-foreground">Translation</p>
                    <textarea
                      value={c.translated ?? ""}
                      rows={2}
                      placeholder="Type the translation"
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => onEdit(c.id, e.target.value)}
                      className="mt-0.5 w-full resize-y rounded-md border bg-background px-2 py-1 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});
