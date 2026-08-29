import { Group, Panel, Separator } from "react-resizable-panels";

type Line = {
  id: number;
  pos: [number, number, number, number];
  word: string;
  ko: string;
};

const FAKE_LINES: Line[] = [
  { id: 0, pos: [100, 50, 180, 200], word: "おはよう", ko: "안녕" },
  { id: 1, pos: [300, 80, 380, 240], word: "遅刻するぞ", ko: "늦겠어" },
];

export function Project({
  name,
  onBack,
}: {
  name: string;
  onBack: () => void;
}) {
  return (
    <div className=" h-screen flex">
      <aside className="w-35 overflow-y-auto border-r border-gray-200 p-2 flex flex-col gap-1">
        <div className="mb-2">
          <span>PAGES </span>
          <span className="rounded-full bg-black/5 px-2 py-0.5 text-[10px]">
            3
          </span>
        </div>

        {[1, 2, 3].map((n) => (
          <button
            key={n}
            className="mb-2 grid h-[120px] w-full place-items-center rounded-md border border-gray-200 text-xs text-gray-400
             hover:border-gray-900"
          >
            페이지 {n}
          </button>
        ))}
      </aside>

      <div className=" flex flex-1 flex-col  bg-gray-100 p-1 border-1 rounded-2xl">
        <div className="flex gap-10  border-b-1 border-black ">
          <button
            onClick={onBack}
            className="text-sm text-gray-500 hover:text-black mr-auto"
           
            
          >
            ← 뒤로
          </button>
          <span className="text-sm font-semibold text-cen">{name}</span>
          <button className=" h-8 rounded-md bg-gray-900 px-3 text-xs text-white  ">
            번역 실행
          </button>
        </div>

        <div
          className="relative bg-white shadow"
          style={{ width: 500, height: 700 }}
        >
          {FAKE_LINES.map((line) => (
            <div
              key={line.id}
              className="absolute border-2 border-red-500"
              style={{
                left: line.pos[0],
                top: line.pos[1],
                width: line.pos[2] - line.pos[0],
                height: line.pos[3] - line.pos[1],
              }}
            />
          ))}
        </div>
      </div>

      <aside className="w-[280px] shrink-0 overflow-y-auto border-l border-gray-200 p-4">
        <h3 className="text-xs font-semibold text-gray-500">텍스트</h3>
        <div className="mt-3 grid gap-3">
          {FAKE_LINES.map((line) => (
            <div
              key={line.id}
              className="rounded-md border border-gray-200 p-2"
            >
              <p className="text-xs text-gray-400">{line.word}</p>
              <input
                defaultValue={line.ko}
                className="mt-1 w-full text-sm outline-none"
              />
            </div>
          ))}
        </div>
      </aside>

      <footer className="flex h-7 shrink-0 items-center border-t border-gray-200 px-4 text-xs text-gray-400">
        {FAKE_LINES.length}개 텍스트
      </footer>
    </div>
  );
}
