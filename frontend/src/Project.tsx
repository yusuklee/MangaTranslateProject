import { Group, Panel, Separator } from "react-resizable-panels";
import { Button } from "@/components/ui/button";
import { useState } from "react";

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
  pages,
}: {
  name: string;
  onBack: () => void;
  pages: string[];
}) {
  const [selectedPage, setSelectedPage] = useState<string | null>(pages[0]);
  
  const [detectedLines, setDetectedLines] = useState<any[]>([]);

  const handleDetect = async () => {
    const res = await fetch(selectedPage!);
    const blob = await res.blob();

    const form = new FormData();
    form.append("file", blob, "image.png");

    const r = await fetch("http://localhost:8000/detect", {
      method: "POST",
      body: form,
    });
    const { lines, detected_img } = await r.json();
    setDetectedLines(lines);
    setSelectedPage(detected_img);
  };

  return (
    <Group className=" h-screen flex ">
      <Panel
        defaultSize={10}
        className="  border-r border-gray-200 p-2 flex flex-col gap-1 h-screen "
      >
        <div className="mb-2">
          <span>PAGES </span>
          <span className="rounded-full bg-black/5 px-2 py-0.5 text-[10px]">
            {pages.length}
          </span>
        </div>

        <div className="overflow-y-auto">
          {pages.map((page, index) => (
            <button
              className="h-25 w-full   items-center gap-3 rounded-lg p-2 text-left hover:bg-black/5
                overflow-hidden shrink-0 flex"
              onClick={() => setSelectedPage(page)}
            >
              <img
                src={page}
                alt={`페이지 ${index + 1}`}
                className="h-15 w-15 object-cover "
              />
              <div className="min-w-0">
                <p className="truncate text-sm">{index + 1}</p>
                <p className="text-xs text-gray-400">... layers</p>
              </div>
            </button>
          ))}
        </div>
      </Panel>

      <Separator />

      <Panel
        defaultSize={60}
        className=" flex flex-1 flex-col  bg-gray-100 p-1 border-1 rounded-2xl h-screen"
      >
        <div className="flex gap-10  border-b-1 border-black ">
          <Button size="sm" onClick={onBack} className="mr-auto">
            ← 뒤로
          </Button>
          <div>
            <Button size="sm" onClick={handleDetect}>
              DETECT
            </Button>
            <Button size="sm">OCR</Button>
            <Button size="sm">TRANSLATE</Button>
            <Button size="sm">RENDER</Button>
            <Button size="sm">PROCESS</Button>
          </div>
        </div>

        <div
          className="relative bg-white shadow flex-1 h-screen border-3 flex overflow-hidden
          justify-center items-center p-10
          "
        >
          <img
            className=" object-cover max-w-full max-h-full"
            src={selectedPage ?? undefined}
          ></img>
        </div>
      </Panel>

      <Separator></Separator>

      <Panel
        defaultSize={15}
        className="overflow-y-auto border-l border-gray-200 p-4 h-screen"
      >
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
      </Panel>

      <footer className="flex h-7 shrink-0 items-center border-t border-gray-200 px-4 text-xs text-gray-400">
        {FAKE_LINES.length}개 텍스트
      </footer>
    </Group>
  );
}
