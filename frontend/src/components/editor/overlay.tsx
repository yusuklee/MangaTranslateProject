import { useLayoutEffect, useRef, useState } from "react";
import type { Content, FontChoice } from "../../Project";

//영역: 말풍선(bubble) 안쪽 INSET, 없으면 글자 상자
//글자 크기: 원본 글자 크기(font_size, BallonsTranslator 방식)로 시작, 브라우저가 그린 결과가 영역을 넘치면 1px 씩 줄인다
//줄바꿈: 브라우저에 맡김. keep-all = 띄어쓰기에서만, overflow-wrap anywhere = 단어가 폭보다 길 때만 글자 단위
const FALLBACK = "Malgun Gothic, sans-serif";
const FONT_URL = "http://localhost:8000/fontfiles/";
const WEIGHT = 700;
const LINE_HEIGHT = 1.25;
const INSET = 4;
const MIN_SIZE = 8;
const SIZE_RATIO = 1.0;   // 원본 글자 크기(일본어 열 폭) → 한국어 폰트 크기 보정

//글 하나. 그려진 뒤 글 덩어리(inner)가 영역(outer)보다 크면 크기를 1px 씩 줄여 다시 잰다
function TextBlock({ c, x1, y1, w, h, family }: { c: Content; x1: number; y1: number; w: number; h: number; family: string }) {
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const start = Math.max(MIN_SIZE, Math.round((c.font_size ?? Math.min(w, h)) * SIZE_RATIO));
  const text = c.translated ?? "";
  const [size, setSize] = useState(start);

  useLayoutEffect(() => {
    const o = outer.current, i = inner.current;
    if (!o || !i) return;
    let s = start;
    i.style.fontSize = `${s}px`;
    const overflow = () => {
      const a = o.getBoundingClientRect(), b = i.getBoundingClientRect();   // 둘 다 같은 배율로 그려지니 화면 px 로 비교해도 됨
      return b.height > a.height + 0.5 || b.width > a.width + 0.5;
    };
    while (s > MIN_SIZE && overflow()) {
      s -= 1;
      i.style.fontSize = `${s}px`;
    }
    setSize(s);
  }, [text, start, w, h, family]);

  //테두리: 8방향 그림자로 외곽선 (HTML 은 -webkit-text-stroke 가 글자 안쪽을 깎아서)
  const sw = Math.max(1, size / 12);
  const shadow = c.stroke
    ? [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, -1], [-1, 1], [1, 1]]
        .map(([dx, dy]) => `${dx * sw}px ${dy * sw}px 0 ${c.stroke}`)
        .join(", ")
    : undefined;

  return (
    <foreignObject x={x1} y={y1} width={w} height={h} style={{ overflow: "visible" }}>
      <div ref={outer} className="flex h-full w-full items-center justify-center text-center">
        <div
          ref={inner}
          style={{
            fontSize: size,
            lineHeight: LINE_HEIGHT,
            fontFamily: `"${family}", ${FALLBACK}`,
            fontWeight: WEIGHT,
            color: c.color ?? "#000",
            textShadow: shadow,
            wordBreak: "keep-all",
            overflowWrap: "anywhere",
            maxWidth: "100%",
          }}
        >
          {text}
        </div>
      </div>
    </foreignObject>
  );
}

//번역문을 영역 위에 얹는다
export function RenderOverlay({
  contents,
  imgSize,
  font,
}: {
  contents: Content[];
  imgSize: { w: number; h: number };
  font: FontChoice;
}) {
  //백엔드 폰트 파일이면 @font-face 로 등록. regular 는 굵기 범위 100~900 (변수 폰트면 축을 쓰고, 아니면 브라우저가 굵게 흉내).
  //bold 파일이 따로 있으면 700 에 그걸 씀. 시스템 폰트면 그냥 이름만 씀
  const faces = font.regular
    ? [`@font-face{font-family:"${font.family}";font-weight:100 900;src:url("${FONT_URL}${font.regular}")}`,
       font.bold ? `@font-face{font-family:"${font.family}";font-weight:700;src:url("${FONT_URL}${font.bold}")}` : ""].join(" ")
    : "";
  return (
    <svg
      viewBox={`0 0 ${imgSize.w} ${imgSize.h}`}
      className="absolute inset-0 h-full w-full"
    >
      {faces && <style>{faces}</style>}
      {contents.map((c) => {
        if (!c.translated) return null;
        const [x1, y1, x2, y2] = c.bubble
          ? [c.bubble[0] + INSET, c.bubble[1] + INSET, c.bubble[2] - INSET, c.bubble[3] - INSET]
          : c.pos;
        return (
          <TextBlock key={c.line_id} c={c} x1={x1} y1={y1} w={Math.max(1, x2 - x1)} h={Math.max(1, y2 - y1)} family={font.family} />
        );
      })}
    </svg>
  );
}
