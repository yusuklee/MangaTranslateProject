import { useState } from "react";
import type { Content } from "../../Project";

export function Text({
  contents,
  selectedArea,
  onSelect,
}: {
  contents: Content[];
  selectedArea: string | null;
  onSelect: (key: string | null) => void;
}) {
  const [openGroup, setOpenGroup] = useState(true);

  return (
    <div className="p-4">
      <button
        onClick={() => setOpenGroup(!openGroup)}
        className="flex w-full items-center gap-2 text-xs font-semibold text-gray-500"
      >
        <span>{openGroup ? "▼" : "▶"}</span>
        <span>TEXT</span>
        <span className="rounded-full bg-black/5 px-2 py-0.5">
          {contents.length}
        </span>
      </button>

      {openGroup && (
        <div className="mt-3 grid gap-2">
          {contents.map((c) => {
            const key = `${c.line_id}`;
            const open = selectedArea === key;
            return (
              <div
                key={c.line_id}
                onClick={() => onSelect(open ? null : key)}
                className={`cursor-pointer rounded-md border p-2 ${
                  open ? "border-red-500" : "border-gray-200"
                }`}
              >
                <p className="text-sm">{c.translated ?? c.original}</p>
                {open && (
                  <div className="mt-1 border-t pt-1">
                    <p className="text-[10px] text-gray-400">source</p>
                    <p className="text-xs text-gray-500">{c.original}</p>
                    <p className="mt-1 text-[10px] text-gray-400">translation</p>
                    <input
                      key={c.translated ?? ""}
                      defaultValue={c.translated ?? ""}
                      onClick={(e) => e.stopPropagation()}
                      className="w-full text-sm outline-none"
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
}
