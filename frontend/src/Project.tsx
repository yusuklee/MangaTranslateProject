import { useState } from "react";

type Line = {
  id: number
  pos: [number, number, number, number]
  word: string
  ko: string
}
let [imageUrl, setImageUrl] = useState('')

const FAKE_LINES: Line[] = [
  { id: 0, pos: [100, 50, 180, 200], word: 'おはよう', ko: '안녕' },
  { id: 1, pos: [300, 80, 380, 240], word: '遅刻するぞ', ko: '늦겠어' },
]

export function Project({ name, onBack }: { name: string; onBack: () => void }) {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-gray-200 px-4">
        <button onClick={onBack} className="text-sm text-black hover:text-black border-2 rounded-md bg-amber-300">
          ← Back
        </button>
        <span className="text-sm font-semibold">{name}</span>
        <button className="ml-auto h-8 rounded-md bg-pink-700 px-3 text-xs text-black">
          Run
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="w-[140px] shrink-0 overflow-y-auto border-r border-gray-200 p-2">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              className="mb-2 grid h-[120px] w-full place-items-center rounded-md border border-gray-200 text-xs text-gray-400 hover:border-gray-900"
            >
              Page {n}
            </button>
          ))}
        </aside>

        <main className="grid min-w-0 flex-1 place-items-center overflow-auto bg-gray-100 p-8">
          <div className="relative bg-white shadow" style={{ width: 500, height: 700 }}>
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
        </main>

        <aside className="w-[280px] shrink-0 overflow-y-auto border-l border-gray-200 p-4">
          <h3 className="text-xs font-semibold text-gray-500">텍스트</h3>
          <div className="mt-3 grid gap-3">
            {FAKE_LINES.map((line) => (
              <div key={line.id} className="rounded-md border border-gray-200 p-2">
                <p className="text-xs text-gray-400">{line.word}</p>
                <input defaultValue={line.ko} className="mt-1 w-full text-sm outline-none" />
              </div>
            ))}
          </div>
        </aside>
      </div>

      <footer className="flex h-7 shrink-0 items-center border-t border-gray-200 px-4 text-xs text-gray-400">
        {FAKE_LINES.length}개 텍스트
      </footer>
    </div>
  )
}
