import { Group, Panel, Separator } from "react-resizable-panels";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { Text } from "./components/editor/text";
import { RenderOverlay } from "./components/editor/overlay";

type Line = {
  id: number;
  pos: [number, number, number, number];
  word: string;
  page: number;
  mask?: string;
};   //백엔드 /detect 응답 형식

export type Content = {
  line_id: number;
  original: string | null; //원본 글자
  translated: string | null; //번역된 글자
  pos: [number, number, number, number];
  mask?: string; //실제 글자 모양 (base64 PNG), 백엔드 inpaint_lama 용
};

type PageContents = {
  [page_name: string]: {
    contents: Content[];
  };
};

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
  const [imgSize, setImgSize] = useState({ w: 1, h: 1 });
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [mode, setMode] = useState(false);
  const [inpainted, setInpainted] = useState<{ [page: string]: string }>({}); //페이지별로 글자를 지운 이미지
  const [render, setRender] = useState(false);

  //DETECT + OCR
  const handleDetect = async () => {
    setInpainted((prev) => {
      const next = { ...prev };
      delete next[selectedPage!];
      return next;
    }); //새로 DETECT 하면 이전 결과는 의미 없으니까
    setRender(false);

    //api 보내는 부분
    const res = await fetch(selectedPage!);
    const blob = await res.blob();
    const form = new FormData();
    form.append("file", blob, "image.png");
    const r = await fetch("http://localhost:8000/detect", {
      method: "POST",
      body: form,
    });

    // 받는 부분
    const lines: Line[] = await r.json();

    const contents: Content[] = lines.map((l) => ({
      line_id: l.id,
      original: l.word,
      translated: null,
      pos: l.pos,
      mask: l.mask,
    }));

    setPageContent((prev) => ({
      ...prev,
      [selectedPage!]: { contents },
    }));

    return contents;
  };

  //현재 페이지의 contents 를 보낸다
  const handleTranslate = async (target?: Content[]) => {
    const contents = target ?? pageContents[selectedPage!]?.contents ?? [];
    if (!contents.length) return;

    const r = await fetch("http://localhost:8000/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        contents.map((c) => ({ id: c.line_id, word: c.original }))
      ),
    });
    const translations = await r.json(); // {"0": "안녕", "1": "뭐야"}

    setPageContent((prev) => ({
      ...prev,
      [selectedPage!]: {
        ...prev[selectedPage!],
        contents: prev[selectedPage!].contents.map((c) => ({
          ...c,
          translated: translations[c.line_id] ?? c.translated,
        })),
      },
    }));
  };

  //INPAINT : 원본 + 상자들을 백엔드에 보내 글자를 지운 이미지를 받는다
  const handleInpaint = async (target?: Content[]) => {
    const contents = target ?? pageContents[selectedPage!]?.contents ?? [];
    if (!contents.length) return;

    const blob = await (await fetch(selectedPage!)).blob();
    const form = new FormData();
    form.append("file", blob, "image.png");
    form.append("contents", JSON.stringify(contents));

    const r = await fetch("http://localhost:8000/inpaint", {
      method: "POST",
      body: form,
    });
    const { image } = await r.json();
    setInpainted((prev) => ({ ...prev, [selectedPage!]: image }));
  };

  //DETECT → TRANSLATE → 글자 지우기 → 글자 얹기
  const handleProcess = async () => {
    const detected = await handleDetect();
    await handleTranslate(detected);
    await handleInpaint(detected);
    setRender(true);
  };

  return (
    <Group className="flex">
      <Panel
        defaultSize="10%"
        className="  border-r border-gray-200 p-2 flex flex-col gap-1  h-screen overflow-hidden"
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
        defaultSize="60%"
        className=" grid grid-rows-[auto_1fr]  bg-gray-100 p-1 border-1 rounded-2xl  "
      >
        <div className="overflow-x-hidden w-[60vw]">
          <div className="flex shrink-0 gap-10 border-b-1 border-black">
            <Button size="sm" onClick={onBack}>
              ← 뒤로
            </Button>
            <Button
              className="mr-auto"
              size="sm"
              onClick={() => setMode(!mode)}
            >
              mode
            </Button>
            <div>
              <Button size="sm" onClick={handleDetect}>
                DETECT
              </Button>
              <Button size="sm" onClick={() => handleTranslate()}>
                TRANSLATE
              </Button>
              <Button size="sm" onClick={() => handleInpaint()}>
                INPAINT
              </Button>
              <Button size="sm" onClick={() => setRender(!render)}>
                RENDER
              </Button>
              <Button size="sm" onClick={handleProcess}>
                PROCESS
              </Button>
            </div>
          </div>

          <div className="overflow-y-auto  h-screen">
            <div className=" bg-white shadow  border-3  justify-center items-center p-10 ">
              <div className="relative w-fit">
                <img
                  className="object-cover"
                  src={
                    inpainted[selectedPage!] ??
                    selectedPage ??
                    undefined
                  }
                  onLoad={(e) =>
                    setImgSize({
                      w: e.currentTarget.naturalWidth,
                      h: e.currentTarget.naturalHeight,
                    })
                  }
                />
                {!mode && (
                  <svg
                    viewBox={`0 0 ${imgSize.w} ${imgSize.h}`}
                    className="absolute inset-0 h-full w-full"
                  >
                    {pageContents[selectedPage!]?.["contents"].map((c) => (
                      <rect
                        key={c.line_id}
                        x={c.pos[0]}
                        y={c.pos[1]}
                        width={c.pos[2] - c.pos[0]}
                        height={c.pos[3] - c.pos[1]}
                        fill="transparent"
                        stroke={
                          selectedArea === `${c.line_id}` ? "#ff2d2d" : "#0064ff"
                        }
                        strokeWidth={6}
                        className="cursor-pointer"
                        onClick={() => setSelectedArea(`${c.line_id}`)}
                      />
                    ))}
                  </svg>
                )}
                {render && (
                  <RenderOverlay
                    contents={pageContents[selectedPage!]?.contents ?? []}
                    imgSize={imgSize}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </Panel>

      <Separator />

      <Panel
        defaultSize="15%"
        className="overflow-y-auto border-l border-gray-200 h-screen"
      >
        <Text
          contents={pageContents[selectedPage!]?.contents ?? []}
          selectedArea={selectedArea}
          onSelect={setSelectedArea}
        />
      </Panel>

      <footer className="flex h-7 shrink-0 items-center border-t border-gray-200 px-4 text-xs text-gray-400">
        {pageContents[selectedPage!]?.contents.length ?? 0}개 텍스트
      </footer>
    </Group>
  );
}
