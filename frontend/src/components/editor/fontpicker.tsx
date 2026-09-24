import { memo, useEffect, useMemo, useRef, useState } from "react";
import type { FontChoice } from "../../Project";

//폰트 고르기. <select> 는 항목마다 다른 폰트로 못 그려서 직접 만든 목록. 항목마다 그 폰트로 미리보기 글자를 보여준다
import { FONT_URL } from "../../api";
const SAMPLE = "가나다 만화 번역 ABC";

//백엔드 폰트 파일들을 @font-face 로 등록. 실제 파일은 그 폰트로 글자를 그릴 때만 받아온다 (목록을 열 때)
function faceCss(fonts: FontChoice[]) {
  return fonts
    .filter((f) => f.regular)
    .map((f) => `@font-face{font-family:"${f.family}";font-weight:100 900;font-display:swap;src:url("${FONT_URL}${f.regular}")}`)
    .join(" ");
}

export const FontPicker = memo(function FontPicker({
  fonts,
  value,
  onChange,
  inline = false,
}: {
  fonts: FontChoice[];   //기본 폰트 포함 전체 선택지
  value: FontChoice;
  onChange: (f: FontChoice) => void;
  inline?: boolean;      //true 면 목록을 버튼 아래에 흐르게 펼친다 (설정 창처럼 overflow 가 잘리는 곳용)
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const faceStyle = useMemo(() => faceCss(fonts), [fonts]);

  //바깥 클릭하면 닫기
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div ref={box} className="relative">
      <style>{faceStyle}</style>
      <button
        type="button"
        className={`rounded-lg border bg-background text-left transition-colors hover:bg-muted ${inline ? "h-8 w-full px-2.5 text-sm" : "h-7 min-w-36 px-2.5 text-xs"}`}
        style={{ fontFamily: `"${value.family}", Malgun Gothic, sans-serif` }}
        onClick={() => setOpen(!open)}
        title="Render font"
      >
        {value.family}
      </button>
      {open && (
        <div className={`z-50 overflow-y-auto rounded-lg border bg-popover p-1 shadow-xl ${inline ? "mt-1 max-h-56 w-full" : "absolute right-0 top-8 max-h-96 w-72"}`}>
          {fonts.map((f) => (
            <div
              key={f.family}
              className={`cursor-pointer rounded-md px-3 py-1.5 transition-colors hover:bg-muted ${f.family === value.family ? "bg-accent text-accent-foreground" : ""}`}
              onClick={() => {
                onChange(f);
                setOpen(false);
              }}
            >
              <div className="text-[10px] text-muted-foreground">{f.family}</div>
              <div className="text-lg leading-tight" style={{ fontFamily: `"${f.family}", Malgun Gothic, sans-serif` }}>
                {SAMPLE}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
