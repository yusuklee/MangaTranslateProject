import type { Content, FontChoice } from "../../Project";

//페이지 렌더러 (canvas 2D). 화면 표시와 내보내기가 이 함수 하나를 같이 쓴다 (코하루 방식: 렌더 결과를 저장하지 않고 매번 같은 렌더러로 그림)
//영역: 말풍선(bubble) 안쪽 INSET, 없으면 글자 상자
//글자 크기: 원본 글자 크기(font_size)에서 시작해, 영역에 들어가는 가장 큰 크기를 이분 탐색으로 찾는다
//줄바꿈: 띄어쓰기에서만 (keep-all). 단어 하나가 폭보다 길면 그때만 글자 단위
const FALLBACK = "Malgun Gothic, sans-serif";
import { FONT_URL } from "../../api";
const WEIGHT = 700;
const LINE_HEIGHT = 1.25;
const INSET = 4;
const MIN_SIZE = 8;

//디코드된 이미지 캐시. 큰 페이지(2000×3000)는 한 장에 24MB 라 무한정 들고 있으면 메모리가 터진다 → 최근 8장만 유지 (LRU)
const IMAGE_CACHE_MAX = 8;
const imageCache = new Map<string, Promise<HTMLImageElement>>();

//이미지 URL → 디코드된 Image. 같은 URL 은 한 번만 받는다
export function loadImage(src: string) {
  let p = imageCache.get(src);
  if (p) {
    imageCache.delete(src); //최근 사용으로 순서 갱신
  } else {
    p = new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = "anonymous"; //개발 중엔 프런트(5173)와 서버(8000) 주소가 달라서, 이게 없으면 캔버스가 오염돼 썸네일·내보내기가 막힌다
      img.onload = () => resolve(img);
      img.onerror = () => {
        imageCache.delete(src); //실패한 건 캐시에 남기지 않는다 (다음에 다시 시도)
        reject(new Error(`image load failed: ${src.slice(0, 60)}`));
      };
      img.src = src;
    });
  }
  imageCache.set(src, p);
  while (imageCache.size > IMAGE_CACHE_MAX) {
    const oldest = imageCache.keys().next().value!;
    imageCache.delete(oldest);
  }
  return p;
}

const loadedFonts = new Set<string>();

//백엔드 폰트면 파일을 받아 등록하고 로드가 끝날 때까지 기다린다. canvas 는 폰트가 안 떠 있으면 대체 폰트로 그려버리기 때문
export async function ensureFont(font: FontChoice) {
  if (!font.regular || loadedFonts.has(font.family)) return;
  const faces = [new FontFace(font.family, `url("${FONT_URL}${font.regular}")`, { weight: "100 900" })];
  if (font.bold) faces.push(new FontFace(font.family, `url("${FONT_URL}${font.bold}")`, { weight: "700" }));
  for (const f of faces) document.fonts.add(await f.load());
  loadedFonts.add(font.family);
}

const fontSpec = (size: number, family: string) => `${WEIGHT} ${size}px "${family}", ${FALLBACK}`;

//글을 maxW 폭에 맞게 줄로 나눈다. \n 은 무조건 줄바꿈
function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number) {
  const fits = (s: string) => ctx.measureText(s).width <= maxW;
  const lines: string[] = [];
  for (const para of text.split("\n")) {
    let line = "";
    for (const word of para.split(" ")) {
      const cand = line ? `${line} ${word}` : word;
      if (fits(cand)) {
        line = cand;
        continue;
      }
      if (line) lines.push(line);
      if (fits(word)) {
        line = word;
        continue;
      }
      //단어 하나가 폭보다 김 → 글자 단위로
      let cur = "";
      for (const ch of word) {
        if (!cur || fits(cur + ch)) cur += ch;
        else {
          lines.push(cur);
          cur = ch;
        }
      }
      line = cur;
    }
    lines.push(line);
  }
  return lines;
}

//영역에 맞는 글자 크기와 줄 목록. 작을수록 잘 들어가니 이분 탐색으로 맞는 최대 크기를 찾는다 (1px 씩 줄이면 큰 상자에서 50번 넘게 잼)
function layout(ctx: CanvasRenderingContext2D, text: string, family: string, start: number, w: number, h: number) {
  const tryFit = (size: number) => {
    ctx.font = fontSpec(size, family);
    const lines = wrapLines(ctx, text, w);
    const ok = lines.length * size * LINE_HEIGHT <= h + 0.5 && !lines.some((l) => ctx.measureText(l).width > w + 0.5);
    return { ok, lines };
  };
  let lo = MIN_SIZE, hi = Math.max(MIN_SIZE, Math.round(start));
  let best = { size: MIN_SIZE, lines: tryFit(MIN_SIZE).lines };
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const r = tryFit(mid);
    if (r.ok) {
      best = { size: mid, lines: r.lines };
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return best;
}

//페이지 하나를 canvas 에 그린다: 이미지 + (translated 가 있는 상자마다) 번역문
export function renderPage(
  canvas: HTMLCanvasElement,
  image: HTMLImageElement,
  contents: Content[],
  font: FontChoice,
  withText: boolean
) {
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(image, 0, 0);
  if (!withText) return;

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  for (const c of contents) {
    if (!c.translated) continue;
    const [x1, y1, x2, y2] = c.bubble
      ? [c.bubble[0] + INSET, c.bubble[1] + INSET, c.bubble[2] - INSET, c.bubble[3] - INSET]
      : c.pos;
    const w = Math.max(1, x2 - x1), h = Math.max(1, y2 - y1);
    const { size, lines } = layout(ctx, c.translated, font.family, c.font_size ?? Math.min(w, h), w, h);

    ctx.font = fontSpec(size, font.family);
    const step = size * LINE_HEIGHT;
    const cx = x1 + w / 2;
    const top = y1 + (h - lines.length * step) / 2;
    lines.forEach((line, i) => {
      const y = top + (i + 0.5) * step;
      if (c.stroke) {
        ctx.strokeStyle = c.stroke;
        ctx.lineWidth = Math.max(2, size / 6);   // DOM 의 8방향 그림자(size/12)와 같은 두께
        ctx.strokeText(line, cx, y);
      }
      ctx.fillStyle = c.color ?? "#000";
      ctx.fillText(line, cx, y);
    });
  }
}

//내보내기용: 새 canvas 에 그려서 PNG Blob 으로. toBlob 은 인코딩을 메인 스레드 밖에서 해서 여러 장을 동시에 굽기 좋다
export async function renderToPng(src: string, contents: Content[], font: FontChoice) {
  const canvas = document.createElement("canvas");
  renderPage(canvas, await loadImage(src), contents, font, true);
  return new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG 인코딩 실패"))), "image/png")
  );
}

//배열을 n 개씩 동시에 처리 (코하루의 buffer_unordered(4) 와 같은 역할)
export async function parallel<T>(items: T[], n: number, work: (item: T, i: number) => Promise<void>) {
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      await work(items[i], i);
    }
  };
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, worker));
}
