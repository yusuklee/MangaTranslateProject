import { Group, Panel, Separator } from "react-resizable-panels";
import { Button } from "@/components/ui/button";
import { useState } from "react";

type Line = {
    id: number;
    pos: [number, number, number, number];
    word: string;
    page: number;
  };

type Content = {
  pos: [number, number, number, number]; //글자의 위치
  original: string | null; //원본 글자
  translated: string | null; //번역된 글자
};

type PageContents = {
  [page_name: string]: {
    changed: string | null; // base64 data URL 수정된 이미지가 들어가는곳
    contents: Content[];
  };
};

const example_word = [
  { id: 0, pos: [100, 50, 180, 200], word: "おはよう", ko: "안녕" },
  { id: 1, pos: [300, 80, 380, 240], word: "遅刻するぞ", ko: "늦겠어" },
];

export function Project({
  name,
  onBack,
  pages, //프로젝트에 있는 파일
}: {
  name: string;
  onBack: () => void;
  pages: string[];
}) {
  const [selectedPage, setSelectedPage] = useState<string | null>(pages[0]);
  const [pageContents, setPageContent] = useState<PageContents>({});
  const [lines, setLines] = useState<Line[]>([]);

  const handleDetect = async () => {
    //api 보내는 부분
    const res = await fetch(selectedPage!);
    const blob = await res.blob();
    const form = new FormData();
    form.append("file", blob, "image.png");
    const r = await fetch("http://localhost:8000/detect", {
      method: "POST",
      body: form,
    });

    //호출해서 받는 부분
    const { lines, detected_img } = await r.json();

    //받은걸로 수정하는 곳
    setLines(lines);

    setPageContent({
      ...pageContents,
      [selectedPage!]: {
        changed: detected_img,
        contents: lines.map((l: Line) => ({
          pos: l.pos,
          original: l.word,
          translated: null,
        })),
      },
    });
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
              {/*detect를 누르면 수정본 사진이 하나 더생기고 이름은 원래 사진명_changed로 저장 */}
            </Button>
            <Button size="sm">OCR</Button>
            {/** detect 하고난다음에 할테니까 changed로 저장되잇는걸 수정하는식? ㄴㄴ */}
            <Button size="sm">TRANSLATE</Button>
            {/**ocr과 동일한 방식 */}
            <Button size="sm">RENDER</Button>
            {/**동일 */}
            <Button size="sm">PROCESS</Button>
            {/**위에 4개를 한방에 실행하는 식으로 할듯 */}
          </div>
        </div>

        <div
          className="relative bg-white shadow flex-1 h-screen border-3 flex overflow-hidden
          justify-center items-center p-10
          "
        >
          <img
            className=" object-cover max-w-full max-h-full"
            src={
              pageContents[selectedPage!]?.changed ?? selectedPage ?? undefined
            }
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
          {example_word.map((line) => ( //추후 수정
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
        {example_word.length}개 텍스트
      </footer>
    </Group>
  );
}
