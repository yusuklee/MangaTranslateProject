import type { Content } from "../../Project";

//글자 수와 상자 크기로 폰트 크기 정하기
function fitFontSize(w: number, h: number, len: number) {
  if (!len) return 12;
  const size = Math.sqrt((w * h) / (len * 1.4));
  return Math.max(8, Math.min(40, Math.floor(size)));
}

//번역문을 상자 위에 얹는다
export function RenderOverlay({
  contents,
  imgSize,
}: {
  contents: Content[];
  imgSize: { w: number; h: number };
}) {
  return (
    <svg
      viewBox={`0 0 ${imgSize.w} ${imgSize.h}`}
      className="absolute inset-0 h-full w-full"
    >
      {contents.map((c) => {
        const [x1, y1, x2, y2] = c.pos;
        const w = x2 - x1;
        const h = y2 - y1;
        const text = c.translated ?? "";
        return (
          <foreignObject key={c.line_id} x={x1} y={y1} width={w} height={h}>
            <div
              className="flex h-full w-full items-center justify-center text-center leading-tight break-words"
              style={{
                fontSize: fitFontSize(w, h, text.length),
                fontFamily: "Malgun Gothic, sans-serif",
                fontWeight: 700,
              }}
            >
              {text}
            </div>
          </foreignObject>
        );
      })}
    </svg>
  );
}
