import { memo, useEffect, useRef, useState } from "react";
import { loadImage, parallel } from "./render";

//왼쪽 페이지 목록. 성능을 위해
//  1) 썸네일은 원본(수 MB) 대신 작은 JPEG 를 한 번 만들어 쓴다 (코하루도 128px 썸네일을 따로 만든다)
//  2) 항목은 memo 로 감싸서 진행 문구(setProgress) 같은 상위 갱신에 다시 그리지 않는다
//  3) 스크롤 따라가기는 현재 페이지가 바뀔 때만 한다
const THUMB_W = 96;

const thumbCache = new Map<string, Promise<string>>();
function makeThumb(page: string) {
  let p = thumbCache.get(page);
  if (!p) {
    p = (async () => {
      //createImageBitmap 은 축소 크기로 바로 디코드해서 원본(수 MB)을 메인 스레드에서 안 푼다. 안 되는 브라우저면 일반 로드
      let bmp: ImageBitmap | HTMLImageElement;
      try {
        const blob = await (await fetch(page)).blob();
        bmp = await createImageBitmap(blob, { resizeWidth: THUMB_W, resizeQuality: "medium" });
      } catch {
        bmp = await loadImage(page);
      }
      const bw = "naturalWidth" in bmp ? bmp.naturalWidth : bmp.width;
      const bh = "naturalHeight" in bmp ? bmp.naturalHeight : bmp.height;
      const c = document.createElement("canvas");
      c.width = THUMB_W;
      c.height = Math.max(1, Math.round((bh / bw) * THUMB_W));
      c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
      if ("close" in bmp) bmp.close();
      return c.toDataURL("image/jpeg", 0.75);
    })();
    p.catch(() => thumbCache.delete(page)); //실패(서버 재시작 중 등)한 건 캐시에서 빼서 다음에 다시 만든다
    thumbCache.set(page, p);
  }
  return p;
}

//실패하면 1초 뒤 한 번 더. 그래도 안 되면 빈 칸으로 둔다 (한 장이 실패해도 나머지는 계속)
async function makeThumbRetry(page: string) {
  try {
    return await makeThumb(page);
  } catch {
    await new Promise((r) => setTimeout(r, 1000));
    try {
      return await makeThumb(page);
    } catch {
      return undefined;
    }
  }
}

const PageItem = memo(function PageItem({
  page,
  index,
  count,
  thumb,
  current,
  picked,
  onClick,
}: {
  page: string;
  index: number;
  count?: number; //감지된 글자 상자 수 (detect 전이면 undefined)
  thumb?: string;
  current: boolean;
  picked: boolean;
  onClick: (page: string, ctrl: boolean, shift: boolean) => void;
}) {
  return (
    <button
      data-page={page}
      className={`flex w-full items-center gap-3 rounded-lg border p-2 text-left transition-colors ${
        current ? "border-primary bg-accent text-accent-foreground shadow-sm" : picked ? "border-primary/40 bg-accent/50" : "border-transparent hover:bg-muted"
      }`}
      onClick={(e) => onClick(page, e.ctrlKey || e.metaKey, e.shiftKey)}
    >
      {thumb ? (
        <img src={thumb} alt={`page ${index + 1}`} className="h-14 w-11 shrink-0 rounded object-cover ring-1 ring-black/10" />
      ) : (
        <div className="h-14 w-11 shrink-0 rounded bg-muted" />
      )}
      <div className="min-w-0">
        <p className="text-sm font-medium">{index + 1} page</p>
        <p className={`truncate text-[11px] ${current ? "text-accent-foreground/80" : "text-muted-foreground"}`}>
          {count === undefined ? "—" : `${count} words`}
        </p>
      </div>
    </button>
  );
});

export function PageList({
  pages,
  counts,
  selectedPage,
  selectedPages,
  onClick,
}: {
  pages: string[];
  counts: Record<string, number>; //페이지별 글자 상자 수
  selectedPage: string | null;
  selectedPages: string[];
  onClick: (page: string, ctrl: boolean, shift: boolean) => void;
}) {
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const list = useRef<HTMLDivElement>(null);

  //썸네일은 4장씩 만들고, 만들어지는 대로 채운다
  useEffect(() => {
    let stale = false;
    parallel(pages.filter((p) => !thumbs[p]), 4, async (page) => {
      const t = await makeThumbRetry(page);
      if (t && !stale) setThumbs((prev) => (prev[page] ? prev : { ...prev, [page]: t }));
    });
    return () => {
      stale = true;
    };
  }, [pages]);

  //현재 페이지가 바뀔 때만 목록을 따라 스크롤
  useEffect(() => {
    if (!selectedPage) return;
    list.current?.querySelector<HTMLElement>(`[data-page="${CSS.escape(selectedPage)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selectedPage]);

  const picked = new Set(selectedPages);
  return (
    <div ref={list} className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
      {pages.map((page, index) => (
        <PageItem
          key={page}
          page={page}
          index={index}
          count={counts[page]}
          thumb={thumbs[page]}
          current={page === selectedPage}
          picked={picked.has(page)}
          onClick={onClick}
        />
      ))}
    </div>
  );
}
