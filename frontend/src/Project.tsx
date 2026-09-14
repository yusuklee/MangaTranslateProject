import { Group, Panel, Separator } from "react-resizable-panels";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { Text } from "./components/editor/text";
import { RenderOverlay } from "./components/editor/overlay";
import { FontPicker } from "./components/editor/fontpicker";

const API = "http://localhost:8000";

//백엔드 /detect 응답 한 줄
type Line = {
  id: number;
  pos: [number, number, number, number];
  word: string;
  page: number;
  mask?: string;
  erase?: [number, number, number, number];
  bubble?: [number, number, number, number] | null;
  font_size?: number;
  color?: string;
  stroke?: string | null;
};

export type Content = {
  line_id: number;
  original: string | null; //원본 글자
  translated: string | null; //번역된 글자
  pos: [number, number, number, number]; //글자 상자 (OCR·번역·렌더용)
  mask?: string; //실제 글자 모양 (base64 PNG), 지우기용
  erase?: [number, number, number, number]; //지우기용 상자 (획 덩어리에 맞게 넓힌 것). mask 는 이 크기
  bubble?: [number, number, number, number] | null; //글자를 담은 말풍선 상자. 렌더 영역
  font_size?: number; //원본 글자 크기(px). 렌더 시작 크기
  color?: string; //원본 글자색
  stroke?: string | null; //테두리색 (밝은 글자일 때)
};

//폰트 선택지. regular/bold 는 백엔드 /fontfiles/ 아래 상대 경로 (없으면 시스템 폰트)
export type FontChoice = { family: string; regular?: string | null; bold?: string | null };
export const DEFAULT_FONT: FontChoice = { family: "Malgun Gothic" };

type PageContents = { [page: string]: { contents: Content[] } };

//응답이 200 이 아니면 본문(백엔드 에러 내용)을 담아 던진다
const okJson = async (r: Response) => {
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
  return r.json();
};

const postJson = (path: string, body: unknown) =>
  fetch(`${API}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(okJson);

//이미지 + contents 를 multipart 로
const postImage = async (path: string, page: string, contents?: Content[]) => {
  const form = new FormData();
  form.append("file", await (await fetch(page)).blob(), "image.png");
  if (contents) form.append("contents", JSON.stringify(contents));
  return fetch(`${API}/${path}`, { method: "POST", body: form }).then(okJson);
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
  const [showBoxes, setShowBoxes] = useState(false); //파란 글자 상자 표시
  const [inpainted, setInpainted] = useState<{ [page: string]: string }>({}); //페이지별로 글자를 지운 이미지
  const [render, setRender] = useState(false);
  const [progress, setProgress] = useState(""); //진행 상황 / 에러 (하단 표시)

  //렌더 폰트. 기본은 시스템 Malgun Gothic, 나머지는 백엔드(/fonts)가 주는 koharu 내장 폰트
  const [font, setFont] = useState<FontChoice>(DEFAULT_FONT);
  const [fonts, setFonts] = useState<FontChoice[]>([]);
  useEffect(() => {
    fetch(`${API}/fonts`)
      .then((r) => r.json())
      .then((list: FontChoice[]) => setFonts(list))
      .catch(() => setFonts([]));
  }, []);

  //DETECT + OCR (page 안 주면 현재 페이지)
  const handleDetect = async (page = selectedPage!) => {
    setInpainted((prev) => {
      const next = { ...prev };
      delete next[page];
      return next;
    }); //새로 DETECT 하면 이전 결과는 의미 없으니까
    setRender(false);

    const lines: Line[] = await postImage("detect", page);
    const contents: Content[] = lines.map((l) => ({
      line_id: l.id,
      original: l.word,
      translated: null,
      pos: l.pos,
      mask: l.mask,
      erase: l.erase,
      bubble: l.bubble,
      font_size: l.font_size,
      color: l.color,
      stroke: l.stroke,
    }));
    setPageContent((prev) => ({ ...prev, [page]: { contents } }));
    return contents;
  };

  //TRANSLATE: 페이지의 원문들을 보내고 번역문을 받아 채운다
  const handleTranslate = async (target?: Content[], page = selectedPage!) => {
    const contents = target ?? pageContents[page]?.contents ?? [];
    if (!contents.length) return;

    const translations = await postJson("translate", contents.map((c) => ({ id: c.line_id, word: c.original })));
    setPageContent((prev) => ({
      ...prev,
      [page]: {
        contents: prev[page].contents.map((c) => ({ ...c, translated: translations[c.line_id] ?? c.translated })),
      },
    }));
  };

  //INPAINT: 원본 + 상자들을 보내 글자를 지운 이미지를 받는다. endpoint: inpaint_lama / inpaint_normal(흰색) / inpaint_flux
  const handleInpaint = async (target?: Content[], endpoint = "inpaint_lama", page = selectedPage!) => {
    const contents = target ?? pageContents[page]?.contents ?? [];
    if (!contents.length) return;
    const { image } = await postImage(endpoint, page, contents);
    setInpainted((prev) => ({ ...prev, [page]: image }));
  };

  //현재 페이지: DETECT → TRANSLATE → INPAINT → 렌더
  const handleProcess = async () => {
    setProgress("DETECT");
    const detected = await handleDetect();
    setProgress("TRANSLATE");
    await handleTranslate(detected);
    setProgress("INPAINT");
    await handleInpaint(detected);
    setRender(true);
    setProgress("완료");
  };

  //모든 페이지: 1) 전 페이지 DETECT  2) 글자를 반으로 갈라 번역 2번 동시 요청 (기다리지 않음)
  //3) 그동안 INPAINT  4) 번역 도착하면 배분·렌더
  const handleAll = async (endpoint: string) => {
    //line_id 는 페이지마다 0부터라 겹치니까 페이지 번호를 붙여 전역 id 로 만든다
    const gid = (pageIndex: number, lineId: number) => pageIndex * 10000 + lineId;

    const detected: { page: string; contents: Content[] }[] = [];
    for (const [i, page] of pages.entries()) {
      setProgress(`DETECT ${i + 1}/${pages.length}`);
      detected.push({ page, contents: await handleDetect(page) });
    }

    const lines = detected.flatMap(({ contents }, pi) =>
      contents.map((c) => ({ id: gid(pi, c.line_id), word: c.original }))
    );
    const half = Math.ceil(lines.length / 2);
    const translating = Promise.all(
      [lines.slice(0, half), lines.slice(half)]
        .filter((part) => part.length)
        .map((part) => postJson("translate", part))
    ).then((parts) => Object.assign({}, ...parts) as Record<string, string>);
    translating.catch(() => {}); //inpaint 도중 먼저 실패해도 "처리 안 된 거부"로 안 뜨게. 아래 await 에서 잡음

    for (const [i, { page, contents }] of detected.entries()) {
      setProgress(`INPAINT ${i + 1}/${pages.length} (번역 동시 진행)`);
      await handleInpaint(contents, endpoint, page);
    }

    setProgress("번역 응답 대기");
    const translations = await translating;
    setPageContent((prev) => {
      const next = { ...prev };
      detected.forEach(({ page, contents }, pi) => {
        next[page] = {
          contents: contents.map((c) => ({ ...c, translated: translations[gid(pi, c.line_id)] ?? null })),
        };
      });
      return next;
    });
    setRender(true);
    setProgress(`완료 ${pages.length}페이지`);
  };

  //버튼용: 에러가 나면 푸터에 표시 (안 그러면 조용히 멈춘 것처럼 보임)
  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (e) {
      setProgress(`에러: ${(e as Error).message}`);
    }
  };

  const contents = pageContents[selectedPage!]?.contents ?? [];

  return (
    <Group className="flex">
      <Panel defaultSize="10%" className="border-r border-gray-200 p-2 flex flex-col gap-1 h-screen overflow-hidden">
        <div className="mb-2">
          <span>PAGES </span>
          <span className="rounded-full bg-black/5 px-2 py-0.5 text-[10px]">{pages.length}</span>
        </div>
        <div className="overflow-y-auto">
          {pages.map((page, index) => (
            <button
              key={page}
              className="h-25 w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-black/5 overflow-hidden shrink-0 flex"
              onClick={() => setSelectedPage(page)}
            >
              <img src={page} alt={`페이지 ${index + 1}`} className="h-15 w-15 object-cover" />
              <div className="min-w-0">
                <p className="truncate text-sm">{index + 1}</p>
                <p className="text-xs text-gray-400">{name}</p>
              </div>
            </button>
          ))}
        </div>
      </Panel>

      <Separator />

      <Panel defaultSize="60%" className="grid grid-rows-[auto_1fr] bg-gray-100 p-1 border-1 rounded-2xl">
        <div className="overflow-x-hidden w-[60vw]">
          <div className="flex shrink-0 items-center gap-2 border-b-1 border-black">
            <Button size="sm" onClick={onBack}>← 뒤로</Button>
            <FontPicker fonts={[DEFAULT_FONT, ...fonts]} value={font} onChange={setFont} />
            <Button className="mr-auto" size="sm" onClick={() => setShowBoxes(!showBoxes)}>BOX</Button>
            <Button size="sm" onClick={() => run(() => handleDetect())}>DETECT</Button>
            <Button size="sm" onClick={() => run(() => handleTranslate())}>TRANSLATE</Button>
            <Button size="sm" onClick={() => run(() => handleInpaint())}>INPAINT</Button>
            <Button size="sm" onClick={() => run(() => handleInpaint(undefined, "inpaint_flux"))}>INPAINT_FLUX</Button>
            <Button size="sm" onClick={() => setRender(!render)}>RENDER</Button>
            <Button size="sm" onClick={() => run(handleProcess)}>PROCESS</Button>
            <Button size="sm" onClick={() => run(() => handleAll("inpaint_normal"))}>ALL_DEFAULT</Button>
            <Button size="sm" onClick={() => run(() => handleAll("inpaint_lama"))}>ALL_LAMA</Button>
          </div>

          <div className="overflow-y-auto h-screen">
            <div className="bg-white shadow border-3 justify-center items-center p-10">
              <div className="relative w-fit">
                <img
                  className="object-cover"
                  src={inpainted[selectedPage!] ?? selectedPage ?? undefined}
                  onLoad={(e) => setImgSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                />
                {showBoxes && (
                  <svg viewBox={`0 0 ${imgSize.w} ${imgSize.h}`} className="absolute inset-0 h-full w-full">
                    {contents.map((c) => (
                      <rect
                        key={c.line_id}
                        x={c.pos[0]}
                        y={c.pos[1]}
                        width={c.pos[2] - c.pos[0]}
                        height={c.pos[3] - c.pos[1]}
                        fill="transparent"
                        stroke={selectedArea === `${c.line_id}` ? "#ff2d2d" : "#0064ff"}
                        strokeWidth={6}
                        className="cursor-pointer"
                        onClick={() => setSelectedArea(`${c.line_id}`)}
                      />
                    ))}
                  </svg>
                )}
                {render && <RenderOverlay contents={contents} imgSize={imgSize} font={font} />}
              </div>
            </div>
          </div>
        </div>
      </Panel>

      <Separator />

      <Panel defaultSize="15%" className="overflow-y-auto border-l border-gray-200 h-screen">
        <Text contents={contents} selectedArea={selectedArea} onSelect={setSelectedArea} />
      </Panel>

      <footer className="flex h-7 shrink-0 items-center border-t border-gray-200 px-4 text-xs text-gray-400">
        {contents.length}개 텍스트
        {progress && <span className="ml-4 text-blue-600">{progress}</span>}
      </footer>
    </Group>
  );
}
