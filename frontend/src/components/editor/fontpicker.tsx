import { useEffect, useRef, useState } from "react";
import type { FontChoice } from "../../Project";

//폰트 고르기. <select> 는 항목마다 다른 폰트로 못 그려서 직접 만든 목록. 항목마다 그 폰트로 미리보기 글자를 보여준다
const FONT_URL = "http://localhost:8000/fontfiles/";
const SAMPLE = "가나다 만화 번역 ABC";

//백엔드 폰트 파일들을 @font-face 로 등록. 실제 파일은 그 폰트로 글자를 그릴 때만 받아온다 (목록을 열 때)
function faceCss(fonts: FontChoice[]) {
  return fonts
    .filter((f) => f.regular)
    .map((f) => `@font-face{font-family:"${f.family}";font-weight:100 900;font-display:swap;src:url("${FONT_URL}${f.regular}")}`)
    .join(" ");
}

export function FontPicker({
  fonts,
  value,
  onChange,
}: {
  fonts: FontChoice[];   //기본 폰트 포함 전체 선택지
  value: FontChoice;
  onChange: (f: FontChoice) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

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
      <style>{faceCss(fonts)}</style>
      <button
        type="button"
        className="h-8 min-w-40 rounded border border-gray-300 bg-white px-2 text-left text-sm"
        style={{ fontFamily: `"${value.family}", Malgun Gothic, sans-serif` }}
        onClick={() => setOpen(!open)}
        title="렌더 폰트"
      >
        {value.family}
      </button>
      {open && (
        <div className="absolute left-0 top-9 z-50 max-h-96 w-72 overflow-y-auto rounded border border-gray-300 bg-white shadow-lg">
          {fonts.map((f) => (
            <div
              key={f.family}
              className={`cursor-pointer px-3 py-1.5 hover:bg-blue-50 ${f.family === value.family ? "bg-blue-100" : ""}`}
              onClick={() => {
                onChange(f);
                setOpen(false);
              }}
            >
              <div className="text-[10px] text-gray-400">{f.family}</div>
              <div className="text-lg leading-tight" style={{ fontFamily: `"${f.family}", Malgun Gothic, sans-serif` }}>
                {SAMPLE}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
