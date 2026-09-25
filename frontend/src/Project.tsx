import { Group, Panel, Separator } from "react-resizable-panels";
import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Text } from "./components/editor/text";
import { SettingsDialog, DEFAULT_SETTINGS, PAGES_PER_CALL, loadApiKey, loadSettings, saveSettings, type AppSettings } from "./components/editor/settings";
import { SplitButton } from "./components/editor/splitbutton";
import { PageList } from "./components/editor/pagelist";
import { RepeatButton } from "./components/editor/repeatbutton";
import { Toasts, describeError, type Toast } from "./components/editor/toast";
import { ensureFont, loadImage, renderPage, renderToPng, parallel } from "./components/editor/render";
import { pickFolder, saveToFolder, pageFileName, downloadZip, type ExportFile, isDesktopApp, pickFolderDesktop, saveToFolderDesktop } from "./components/editor/export";

import { API } from "./api";
import type { ProjectDetail } from "./App";

type area = [number, number, number, number];

//백엔드 /detect 응답 한 상자. translated 만 프런트가 채운다
export type Content = {
  id: number;
  pos: area; //글자 상자 (OCR·번역·렌더용)
  word: string; //원문
  translated?: string; //번역문
  page: number;
  mask?: string; //글자 모양 (base64 PNG), 지우기용
  mask_area?: area; //지우기용 넓힌 상자. mask 는 이 크기
  bubble?: area | null; //글자를 담은 말풍선 상자. 렌더 영역
  font_size?: number; //원본 글자 크기(px)
  color?: string; //글자색
  stroke?: string | null; //테두리색 (밝은 글자일 때)
};

//폰트 선택지. regular/bold 는 백엔드 /fontfiles/ 아래 상대 경로 (없으면 시스템 폰트)
export type FontChoice = { family: string; regular?: string | null; bold?: string | null };
const DEFAULT_FONT: FontChoice = { family: "Malgun Gothic" };

type PageContents = { [page: string]: Content[] };

//응답이 200 이 아니면 본문(백엔드 에러 내용)을 담아 던진다
const okJson = async (r: Response) => {
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
  return r.json();
};

//extra: 같이 보낼 폼 값 (detect 의 classes 등)
const post_image = async (path: string, page: string, contents?: Content[], extra: Record<string, string> = {}) => {
  const form = new FormData();
  form.append("file", await (await fetch(page)).blob(), "image.png");
  if (contents) form.append("contents", JSON.stringify(contents));
  for (const [k, v] of Object.entries(extra)) form.append(k, v);
  return fetch(`${API}/${path}`, { method: "POST", body: form }).then(okJson);
};

//인페인팅: 결과가 PNG 바이트로 오니 blob URL 로 받는다 (base64 문자열보다 작고 디코드가 없음)
//보내는 contents 는 지우기에 필요한 것만 (pos, mask_area, mask) — 번역문·색 같은 건 빼서 업로드를 줄인다
const post_inpaint = async (path: string, page: string, contents: Content[]) => {
  const form = new FormData();
  form.append("file", await (await fetch(page)).blob(), "image.png");
  form.append("contents", JSON.stringify(contents.map(({ pos, mask_area, mask }) => ({ pos, mask_area, mask }))));
  const r = await fetch(`${API}/${path}`, { method: "POST", body: form });
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
  return URL.createObjectURL(await r.blob());
};

export function Project({
  project,
  onBack,
}: {
  project: ProjectDetail; //백엔드가 디스크에서 읽어 준 프로젝트 (페이지 URL, 저장된 상자·번역, 지운 이미지)
  onBack: () => void;
}) {
  const name = project.name;
  //페이지 키 = 페이지 이미지 URL. 저장할 때는 파일명(file)으로 바꿔 쓴다
  const pages = useMemo(() => project.pages.map((p) => `${API}${p.url}`), [project]);
  const names = useMemo(() => project.pages.map((p) => p.name), [project]);
  const fileOf = useMemo(() => Object.fromEntries(project.pages.map((p) => [`${API}${p.url}`, p.file])) as Record<string, string>, [project]);
  const [selectedPage, setSelectedPage] = useState<string | null>(pages[0]);
  //여러 페이지 선택 (코하루 방식): 클릭 = 하나만, Ctrl+클릭 = 추가/해제, Shift+클릭 = 마지막 클릭부터 범위. EXPORT 대상
  const [selectedPages, setSelectedPages] = useState<string[]>(pages[0] ? [pages[0]] : []);
  const anchor = useRef<string | null>(pages[0]);
  const targetPages = selectedPages.length ? selectedPages : selectedPage ? [selectedPage] : []; //PROCESS·EXPORT 대상
  //방향키: ←/→ 이전·다음 페이지 (이동한 페이지 하나만 선택), ↑/↓ 가운데 그림 위아래 스크롤. 입력칸에 커서가 있을 땐 무시
  const scrollRef = useRef<HTMLDivElement>(null);
  //가운데 그림 영역만 전체화면 (PAGES·TEXT·상단바 없이, F11 처럼). fit 모드는 그대로 적용된다. F 키로도 켜고 끔
  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else scrollRef.current?.requestFullscreen();
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        scrollRef.current?.scrollBy({ top: e.key === "ArrowDown" ? 160 : -160, behavior: "smooth" });
        return;
      }
      if (e.key === "f" || e.key === "F") {
        if (e.ctrlKey || e.metaKey || e.altKey) return; //Ctrl+F(찾기) 같은 건 건드리지 않음
        e.preventDefault();
        toggleFullscreen();
        return;
      }
      const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!step || !selectedPage) return;
      const i = pages.indexOf(selectedPage) + step;
      if (i < 0 || i >= pages.length) return;
      e.preventDefault();
      clickPage(pages[i], false, false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pages, selectedPage]);
  //처음 열 때(또는 페이지 목록이 바뀌었을 때) 현재 페이지가 목록에 없으면 1페이지를 선택
  useEffect(() => {
    if (pages.length && (!selectedPage || !pages.includes(selectedPage))) {
      setSelectedPage(pages[0]);
      setSelectedPages([pages[0]]);
      anchor.current = pages[0];
    }
  }, [pages]);
  const clickPage = useCallback((page: string, ctrl: boolean, shift: boolean) => {
    setSelectedPage(page);
    if (shift && anchor.current) {
      const [a, b] = [pages.indexOf(anchor.current), pages.indexOf(page)].sort((x, y) => x - y);
      setSelectedPages(pages.slice(a, b + 1));
      return;
    }
    anchor.current = page;
    if (ctrl) setSelectedPages((prev) => (prev.includes(page) ? prev.filter((p) => p !== page) : [...prev, page]));
    else setSelectedPages([page]);
  }, [pages]);
  const goPage = useCallback((page: string) => clickPage(page, false, false), [clickPage]); //REPEAT 자동 넘기기용
  const pageIndex = selectedPage ? pages.indexOf(selectedPage) : -1;
  const stepPage = (d: number) => {
    const i = pageIndex + d;
    if (i >= 0 && i < pages.length) goPage(pages[i]);
  };
  const [pageContents, setPageContents] = useState<PageContents>(() => {
    const out: PageContents = {};
    for (const p of project.pages) if (project.contents[p.file]) out[`${API}${p.url}`] = project.contents[p.file];
    return out;
  });
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [progress, setProgress] = useState(""); //진행 상황 / 에러 (하단 표시)
  const [callBar, setCallBar] = useState<boolean[] | null>(null); //TRANSLATE 중 호출별 도착 여부 (하단 칸 막대). null = 막대 없음
  //보기 모드: 원본 / 글자 지운 그림 / 번역문 얹은 그림. 아직 없는 단계를 고르면 있는 것까지만 보여준다 (원본만 있으면 계속 원본)
  type View = "original" | "inpainted" | "rendered";
  const [view, setView] = useState<View>("original");
  const [leftOpen, setLeftOpen] = useState(true);   //PAGES 패널 (VS Code 처럼 접으면 가운데가 넓어짐)
  //가운데 보기: "width" = 폭에 맞춤(세로는 스크롤), "page" = 한 화면에 다 보이게. fullscreen 은 브라우저 전체화면
  const [fit, setFit] = useState<"width" | "page">("page"); //기본은 한 화면 맞춤
  const [fullscreen, setFullscreen] = useState(false);
  //앱(pywebview) 창은 그림 영역 전체화면을 해도 창 크기에 머문다 → 창 자체도 같이 모니터 전체로 켜고 끈다 (Esc 로 나가도 같이 꺼짐)
  const windowFullscreen = useRef(false);
  useEffect(() => {
    const onChange = () => {
      const on = !!document.fullscreenElement;
      setFullscreen(on);
      if (isDesktopApp() && on !== windowFullscreen.current) {
        windowFullscreen.current = on;
        void window.pywebview!.api.fullscreen();
      }
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const [rightOpen, setRightOpen] = useState(true); //TEXT·SETTINGS 패널
  //설정 (⚙ 버튼으로 여는 창): 원본→번역 언어, 인페인팅 모델
  const [settings, setSettings] = useState<AppSettings>(() => {
    const { fontFamily: _f, ...saved } = loadSettings();
    return { ...DEFAULT_SETTINGS, ...saved, apiKey: loadApiKey() };
  });
  const keyHeader = (): Record<string, string> => (settings.apiKey ? { "X-Gemini-Key": settings.apiKey } : {});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const inpaintModel = settings.inpaintModel;
  //번역 요청: 문장 목록 + 언어 방향 + 모델
  //응답이 3분 넘게 없으면 끊고 "No response" 로 알린다
  const translate = async (lines: { id: number; word: string }[]) => {
    const ctl = new AbortController();
    const timer = window.setTimeout(() => ctl.abort(), 180_000);
    try {
      const r = await fetch(`${API}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...keyHeader() },
        body: JSON.stringify({ lines, source: settings.source, target: settings.target, model: settings.model }),
        signal: ctl.signal,
      });
      return await okJson(r);
    } finally {
      window.clearTimeout(timer);
    }
  };
  //설정 창의 Gemini 모델 목록 (백엔드가 API 에서 받아옴)
  const [inpaintedImgs, setInpaintedImgs] = useState<{ [page: string]: string }>(() => {
    const out: Record<string, string> = {};
    for (const p of project.pages) if (project.erased[p.file]) out[`${API}${p.url}`] = `${API}${project.erased[p.file]}?t=${Date.now()}`;
    return out;
  }); //페이지별로 글자를 지운 이미지 (blob URL 또는 저장된 파일 URL)

  //자동 저장 (코하루처럼): 상자·번역이 바뀌면 0.8초 뒤 project.json 에 씀. 첫 렌더는 건너뜀
  const firstSave = useRef(true);
  useEffect(() => {
    if (firstSave.current) { firstSave.current = false; return; }
    const id = window.setTimeout(() => {
      const contents: Record<string, Content[]> = {};
      for (const [url, c] of Object.entries(pageContents)) if (fileOf[url]) contents[fileOf[url]] = c;
      fetch(`${API}/projects/${encodeURIComponent(name)}/state`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contents }),
      }).catch(() => {});
    }, 800);
    return () => window.clearTimeout(id);
  }, [pageContents, fileOf, name]);

  //인페인팅 결과 저장/삭제 (PNG 파일로)
  const saveErased = async (page: string, url: string) => {
    const file = fileOf[page];
    if (!file) return;
    const blob = await (await fetch(url)).blob();
    await fetch(`${API}/projects/${encodeURIComponent(name)}/erased/${encodeURIComponent(file)}`, { method: "PUT", body: blob, headers: { "Content-Type": "image/png" } }).catch(() => {});
  };
  const deleteErased = (page: string) => {
    const file = fileOf[page];
    if (file) fetch(`${API}/projects/${encodeURIComponent(name)}/erased/${encodeURIComponent(file)}`, { method: "DELETE" }).catch(() => {});
  };

  //렌더 폰트. 기본은 시스템 Malgun Gothic, 나머지는 백엔드(/fonts)가 주는 koharu 내장 폰트
  const [font, set_font] = useState<FontChoice>(DEFAULT_FONT);
  const [allFont, setAllFont] = useState<FontChoice[]>([]);
  const fontChoices = useMemo(() => [DEFAULT_FONT, ...allFont], [allFont]);
  //설정·글꼴을 바꿀 때마다 localStorage 에. 글꼴 목록이 오면 저장해 둔 글꼴을 다시 고른다
  useEffect(() => saveSettings(settings, font.family), [settings, font.family]);
  useEffect(() => {
    const saved = loadSettings().fontFamily;
    const f = saved && fontChoices.find((c) => c.family === saved);
    if (f) set_font(f);
  }, [fontChoices]);

  //백엔드가 뜰 때까지(=detect 모델 로드 끝날 때까지) 2초마다 확인하며 안내 문구를 띄운다
  const [backendUp, setBackendUp] = useState(false);
  const [fluxAvailable, setFluxAvailable] = useState(false); //데스크톱 앱 빌드에는 FLUX(torch) 가 없다 → 설정 목록에서 숨김
  useEffect(() => {
    let timer: number | undefined;
    const check = async () => {
      try {
        const m: { flux_available?: boolean } = await fetch(`${API}/models`).then(okJson);
        setFluxAvailable(!!m.flux_available);
        if (!m.flux_available) setSettings((s) => (s.inpaintModel === "inpaint_flux" ? { ...s, inpaintModel: "inpaint_lama" } : s));
        setBackendUp(true);
        setProgress((p) => (p.startsWith("Loading backend") ? "" : p));
      } catch {
        setProgress("Loading backend models... (DETECT · OCR)");
        timer = window.setTimeout(check, 2000);
      }
    };
    check();
    return () => window.clearTimeout(timer);
  }, []);

  //LaMa·FLUX 는 처음 쓸 때 서버가 올린다. 아직 안 올라왔으면 "불러오는 중" 을 보여주고 요청한다
  const MODEL_LABEL: Record<string, { key: "lama" | "flux"; name: string }> = {
    inpaint_lama: { key: "lama", name: "LaMa" },
    inpaint_flux: { key: "flux", name: "FLUX" },
  };
  const noteModelLoading = async (inpaint_model: string) => {
    const m = MODEL_LABEL[inpaint_model];
    if (!m) return;
    const loaded: Record<string, boolean> = await fetch(`${API}/models`).then(okJson).catch(() => ({}));
    if (!loaded[m.key]) setProgress(`Loading ${m.name} model... (first time only)`);
  };

  useEffect(() => {
    if (!backendUp) return;
    fetch(`${API}/fonts`)
      .then((r) => r.json())
      .then(setAllFont)
      .catch(() => {
        setAllFont([]);
      });
  }, [backendUp]);

const handle_detect = async (page=selectedPage!)=>{
  setInpaintedImgs((prev)=>{
      const tmp = {...prev};
      if (tmp[page]?.startsWith("blob:")) URL.revokeObjectURL(tmp[page]); //이전 결과 메모리 해제
      delete tmp[page]
      return tmp;
  })
  deleteErased(page);
  setView("original");

  const contents:Content[] = await post_image("detect",page,undefined,{ classes: settings.onomatopoeia ? "text,onomatopoeia" : "text" });
  setPageContents((prev)=>({...prev,[page]:contents}))
  return contents

}

//선택한 여러 페이지 번역 (TRANSLATE 단계). 줄을 모아 handle_all 처럼 settings.calls 번으로 나눠 동시에 보낸다
//호출이 하나 올 때마다 TRANSLATE k/n 과 하단 막대의 그 칸을 갱신. DETECT 안 한 페이지는 건너뜀
const handle_translate_pages = async (targets: string[]) => {
    const gid = (pageIndex: number, id: number) => pageIndex * 10000 + id;
    const detected = targets.filter((page) => pageContents[page]);
    const lines = detected.flatMap((page, pi) => pageContents[page].map((c) => ({ id: gid(pi, c.id), word: c.word })));

    const wanted = settings.calls === "auto" ? Math.ceil(detected.length / PAGES_PER_CALL) : settings.calls;
    const calls = Math.max(1, Math.min(wanted, lines.length));
    const size = Math.ceil(lines.length / calls);
    const parts = Array.from({ length: calls }, (_, k) => lines.slice(k * size, (k + 1) * size)).filter((p) => p.length);

    let arrived = 0;
    let failed = false; //하나가 실패하면 뒤늦게 온 응답이 에러 문구를 덮지 않게
    setCallBar(parts.map(() => false));
    setProgress(`TRANSLATE 0/${parts.length} (${settings.model})`);
    let translations: Record<string, string>;
    try {
      const res = await Promise.all(parts.map((part, k) => translate(part).then((r) => {
        if (!failed) {
          arrived++;
          setCallBar((bar) => bar && bar.map((v, j) => v || j === k));
          setProgress(`TRANSLATE ${arrived}/${parts.length} (${settings.model})`);
        }
        return r;
      })));
      translations = Object.assign({}, ...res);
    } catch (e) {
      failed = true;
      throw e;
    } finally {
      setCallBar(null);
    }

    setPageContents((prev) => {
      const next = { ...prev };
      detected.forEach((page, pi) => {
        next[page] = pageContents[page].map((c) => ({ ...c, translated: translations[gid(pi, c.id)] }));
      });
      return next;
    });
}

const handle_inpaint=async(inpaint_model:string=inpaintModel,page=selectedPage!, target?:Content[])=>{
    const contents = target ?? pageContents[page];
    if (!contents || !contents.length)return;
    await noteModelLoading(inpaint_model);
    const image = await post_inpaint(inpaint_model,page,contents);
    setInpaintedImgs((prev)=>{
        if (prev[page]?.startsWith("blob:")) URL.revokeObjectURL(prev[page]);
        return {...prev, [page]:image};
    })
    void saveErased(page, image); //기다리지 않음
}
  //파이프라인: 1) 대상 페이지 전부 DETECT  2) 글자를 반으로 갈라 번역 2번 동시 요청 (기다리지 않음)
  //3) 그동안 INPAINT (설정의 모델)  4) 번역 도착하면 배분·렌더.  PROCESS = 선택한 페이지들, PROCESS_ALL = 전체
  const handle_all = async (targets:string[]=pages)=>{
    const gid = (pageIndex:number, id:number)=> pageIndex*10000+id;

    const detected:PageContents={};
    for (const [page_num ,page ] of targets.entries()){
        setProgress(`DETECT ${page_num+1}/${targets.length}`);
        detected[page]=await handle_detect(page);
    }
    const lines = targets.flatMap((page,pi) => {
        return detected[page].map((c)=> {return {id:gid(pi,c.id), word:c.word}})
    })

    //호출 횟수: 설정값. auto 면 30페이지당 1번. 문장 수보다 많이 나눌 순 없다
    const wanted = settings.calls === "auto" ? Math.ceil(targets.length / PAGES_PER_CALL) : settings.calls;
    const calls = Math.max(1, Math.min(wanted, lines.length));
    const size = Math.ceil(lines.length / calls);
    const parts = Array.from({ length: calls }, (_, k) => lines.slice(k * size, (k + 1) * size)).filter((p) => p.length);
    setProgress(`TRANSLATE ${parts.length} call${parts.length > 1 ? "s" : ""} (${settings.model}) · inpainting meanwhile`);
    const translating = Promise.all(parts.map((part)=>translate(part)))
      .then((res)=>Object.assign({},...res)as Record<string,string>);
    translating.catch(()=>{});

    for (const [i, page] of targets.entries()) {
      setProgress(`INPAINT ${i + 1}/${targets.length} `);
      await handle_inpaint(inpaintModel, page, detected[page]);
    }

    setProgress("Waiting for translation...");
    const translations = await translating;
    setPageContents((prev) => {
      const next = { ...prev };
      targets.forEach((page, pi) => {
          next[page] = detected[page].map((c) => {
              return { ...c, translated: translations[gid(pi, c.id)] };
          });
      });
      return next;
  });
    setView("rendered");
    setProgress(`Done · ${targets.length} pages`);

    
}
  //화면: 현재 페이지를 canvas 에 그린다 (지운 이미지가 있으면 그것, RENDER 켜면 번역문까지). 페이지·결과·폰트가 바뀔 때마다 다시 그림
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const curInpainted = selectedPage ? inpaintedImgs[selectedPage] : undefined;
  const curContents = selectedPage ? pageContents[selectedPage] : undefined;
  const hasInpainted = !!curInpainted;
  const hasRendered = !!curContents?.some((c) => c.translated);
  const shownView: View = view === "rendered" && hasRendered ? "rendered" : view !== "original" && hasInpainted ? "inpainted" : "original";

  useEffect(() => {
    if (!selectedPage || !canvasRef.current) return;
    const canvas = canvasRef.current;
    let stale = false;
    (async () => {
      await ensureFont(font);
      const image = await loadImage(shownView === "original" ? selectedPage : curInpainted ?? selectedPage);
      if (stale) return;
      renderPage(canvas, image, curContents ?? [], font, shownView === "rendered");
    })().catch((e) => setProgress(`Error: ${(e as Error).message}`));
    return () => {
      stale = true;
    };
  }, [selectedPage, curInpainted, curContents, font, shownView]);

  //EXPORT: 왼쪽에서 선택한 페이지들(없으면 현재 페이지)을, 폴더를 고르게 한 뒤 같은 렌더러로 PNG 로 만들어 그 폴더에 쓴다
  //번호는 프로젝트 안 순서(0001_...) 그대로. 폴더 선택 미지원 브라우저면 zip 다운로드
  //EXPORT 는 항상 전체 페이지 (선택과 무관)
  const handle_export = async () => {
    const targets = pages;
    if (!targets.length) return;
    const desktop = isDesktopApp();
    //폴더 선택은 버튼 클릭 직후에 열어야 해서 맨 앞. 앱은 윈도우 창(권한 물음 없음), 브라우저는 File System Access API
    const folder = desktop ? await pickFolderDesktop() : null;
    const dir = desktop ? undefined : await pickFolder();
    if ((desktop && folder === null) || dir === null) return; //취소
    await ensureFont(font);
    const files: ExportFile[] = [];
    let done = 0;
    await parallel(targets, 4, async (page) => {   //4장씩 동시에 (코하루와 같음)
      const i = pages.indexOf(page);
      const file = { name: pageFileName(i, names?.[i]), blob: await renderToPng(inpaintedImgs[page] ?? page, pageContents[page] ?? [], font) };
      if (folder) await saveToFolderDesktop(folder, file);
      else if (dir) await saveToFolder(dir, file);
      else files.push(file);
      setProgress(`EXPORT ${++done}/${targets.length}`);
    });
    if (!folder && !dir) await downloadZip(name, files);
    setProgress(`Exported ${targets.length} pages`);
  };

  //실행 모드 (PROCESS 버튼의 드롭다운으로 고름). 왼쪽 버튼을 눌러야 실행된다
  type Action = "process" | "detect" | "translate" | "inpaint" | "render";
  const [action, setAction] = useState<Action>("process");
  const ACTIONS: { value: Action; label: string }[] = [
    { value: "process", label: "PROCESS" },
    { value: "detect", label: "DETECT" },
    { value: "translate", label: "TRANSLATE" },
    { value: "inpaint", label: "INPAINT" },
    { value: "render", label: "RENDER" },
  ];
  const run_action = async () => {
    if (action === "process") return handle_all(targetPages);
    if (action === "render") return setView("rendered");
    return run_step(action);
  };

  //단계 하나만 선택한 페이지 전부에 실행
  const run_step = async (step: "detect" | "translate" | "inpaint") => {
    const label = { detect: "DETECT", translate: "TRANSLATE", inpaint: "INPAINT" }[step];
    if (step === "translate") await handle_translate_pages(targetPages);
    else for (const [i, page] of targetPages.entries()) {
      setProgress(`${label} ${i + 1}/${targetPages.length}`);
      if (step === "detect") await handle_detect(page);
      else await handle_inpaint(inpaintModel, page);
    }
    if (step === "inpaint") setView("inpainted");
    setProgress(`${label} done · ${targetPages.length} pages`);
  };

  //알림 (오른쪽 위 카드). 에러는 직접 닫을 때까지 남는다
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);
  const notify = (t: Omit<Toast, "id">) => setToasts((prev) => [...prev.slice(-3), { ...t, id: ++toastId.current }]);
  const closeToast = useCallback((id: number) => setToasts((prev) => prev.filter((t) => t.id !== id)), []);

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
    } catch (e) {
      const { title, description } = describeError(e);
      setProgress(`Error: ${title}`);
      notify({ kind: "error", title, description });
    }
  };

  const contents = pageContents[selectedPage!] ?? [];
  //TEXT 패널에서 번역문을 고치면 그 상자만 바꾼다. 캔버스는 pageContents 가 바뀌니 알아서 다시 그려지고, EXPORT 도 이 값을 쓴다
  const editTranslation = useCallback((id: number, translated: string) => {
    const page = selectedPage;
    if (!page) return;
    setPageContents((prev) => ({
      ...prev,
      [page]: (prev[page] ?? []).map((c) => (c.id === id ? { ...c, translated } : c)),
    }));
  }, [selectedPage]);
  //왼쪽 목록에 보여줄 페이지별 글자 상자 수 (detect 전이면 없음)
  const wordCounts = useMemo(
    () => Object.fromEntries(Object.entries(pageContents).map(([p, c]) => [p, c.length])) as Record<string, number>,
    [pageContents]
  );

  const viewLabel: Record<View, string> = { original: "Original", inpainted: "Erased", rendered: "Translated" };
  const isError = progress.startsWith("Error");

  return (
    <div className="flex h-screen flex-col bg-muted/60 text-foreground">
      {/* 상단 바: 프로젝트 이름, 보기 모드, 작업 버튼 */}
      <header className="flex h-12 shrink-0 items-center gap-2 border-b bg-background px-3">
        <Button variant="ghost" size="sm" onClick={onBack} title="Projects">←</Button>
        <span className="truncate text-sm font-semibold">{name}</span>

        <div className="ml-3 flex overflow-hidden rounded-lg border bg-background text-xs">
          {(["original", "inpainted", "rendered"] as const).map((v) => (
            <button
              key={v}
              type="button"
              className={`px-3 py-1.5 transition-colors ${shownView === v ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
              onClick={() => setView(v)}
            >
              {viewLabel[v]}
            </button>
          ))}
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
          <RepeatButton pages={pages} selectedPage={selectedPage} onGo={goPage} />
          <span className="mx-1 h-5 w-px bg-border" />
          <SplitButton
            value={action}
            options={ACTIONS}
            onSelect={setAction}
            onRun={() => run(run_action)}
            suffix={targetPages.length > 1 ? ` (${targetPages.length})` : ""}
          />
          <Button variant="secondary" size="sm" onClick={() => run(() => handle_all())}>PROCESS ALL</Button>
          <Button variant="outline" size="sm" onClick={() => run(handle_export)}>EXPORT</Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* 접힌 PAGES: 얇은 띠 + 펼치기 */}
        {!leftOpen && (
          <button
            className="flex w-7 shrink-0 flex-col items-center gap-2 border-r bg-background pt-2 text-muted-foreground hover:bg-muted"
            onClick={() => setLeftOpen(true)}
            title="Expand PAGES"
          >
            <span className="text-[10px]">▶</span>
            <span className="text-[10px] [writing-mode:vertical-rl]">PAGES</span>
          </button>
        )}

        <Group className="flex min-h-0 flex-1">
          {/* 왼쪽: 페이지 목록 */}
          {leftOpen && (
            <Panel defaultSize="14%" minSize="10%" className="flex flex-col border-r bg-background">
              <div className="flex h-9 shrink-0 items-center gap-2 border-b px-3 text-[11px] font-semibold tracking-wide text-muted-foreground">
                <span>PAGES</span>
                <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">{pages.length}</span>
                {selectedPages.length > 1 && <span className="text-[10px] text-accent-foreground">{selectedPages.length} selected</span>}
                <button className="ml-auto rounded px-1 text-[10px] hover:bg-muted" onClick={() => setLeftOpen(false)} title="Collapse">◀</button>
              </div>
              <PageList pages={pages} counts={wordCounts} selectedPage={selectedPage} selectedPages={selectedPages} onClick={clickPage} />
            </Panel>
          )}
          {leftOpen && <Separator className="w-px bg-border transition-colors hover:bg-primary/50" />}

          {/* 가운데: 페이지 */}
          <Panel className="min-w-0 overflow-hidden">
           <div ref={scrollRef} className={`relative h-full overflow-auto ${fullscreen ? "bg-black" : "bg-muted/60"}`}>
            {/* 위 가운데 떠 있는 보기 버튼: 전체화면 / 한 화면에 맞춤 / 폭에 맞춤 */}
            <div className="sticky top-2 z-10 flex justify-center">
              <div className="flex overflow-hidden rounded-lg border bg-background/90 text-xs shadow-sm backdrop-blur">
                <button className={`px-2.5 py-1 hover:bg-muted ${fullscreen ? "bg-primary text-primary-foreground" : ""}`} onClick={toggleFullscreen} title="Fullscreen">⛶</button>
                <button className={`border-l px-2.5 py-1 hover:bg-muted ${fit === "page" ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setFit("page")} title="Fit page">↔ fit</button>
                <button className={`border-l px-2.5 py-1 hover:bg-muted ${fit === "width" ? "bg-primary text-primary-foreground" : ""}`} onClick={() => setFit("width")} title="Fit width">↕ fit</button>
                <button className="border-l px-2.5 py-1 hover:bg-muted disabled:opacity-40" disabled={pageIndex <= 0} onClick={() => stepPage(-1)} title="Previous page (←)">‹ prev</button>
                <button className="border-l px-2.5 py-1 hover:bg-muted disabled:opacity-40" disabled={pageIndex < 0 || pageIndex >= pages.length - 1} onClick={() => stepPage(1)} title="Next page (→)">next ›</button>
              </div>
            </div>
            {/* 흰 카드는 그림 크기를 그대로 따라간다 (카드에 높이 제한을 주면 그림만 삐져나옴). 그림 최대 높이 = 화면 - 상단바/하단줄/여백/카드 패딩 */}
            <div className={`flex justify-center px-8 pb-8 pt-4 ${fit === "page" ? "h-[calc(100%-2.25rem)] items-center" : "min-h-full items-start"}`}>
              <div className={`inline-block max-w-full rounded-md p-2 ${fullscreen ? "bg-black" : "bg-background shadow-[0_8px_30px_rgba(0,0,0,0.12)] ring-1 ring-black/5"}`}>
                <canvas
                  ref={canvasRef}
                  className={`block rounded-sm ${
                    fit === "page" ? `h-auto w-auto max-w-full ${fullscreen ? "max-h-[calc(100vh-5.5rem)]" : "max-h-[calc(100vh-10.5rem)]"}` : "h-auto max-w-full"
                  }`}
                />
              </div>
            </div>
           </div>
          </Panel>

          {rightOpen && <Separator className="w-px bg-border transition-colors hover:bg-primary/50" />}
          {/* 오른쪽: 글자 목록 + 설정 */}
          {rightOpen && (
            <Panel defaultSize="20%" minSize="14%" className="flex flex-col border-l bg-background">
              <div className="min-h-0 flex-1 overflow-y-auto">
                <Text contents={contents} selectedArea={selectedArea} onSelect={setSelectedArea} onEdit={editTranslation} onCollapse={() => setRightOpen(false)} />
              </div>
              {/* 오른쪽 아래: 설정 창 여는 버튼 */}
              <div className="shrink-0 border-t bg-muted/40 p-2">
                <Button variant="outline" size="sm" className="w-full justify-start gap-2" onClick={() => setSettingsOpen(true)}>
                  <span>⚙</span>
                  <span>SETTINGS</span>
                </Button>
              </div>
            </Panel>
          )}
        </Group>

        {/* 접힌 TEXT: 얇은 띠 + 펼치기 */}
        {!rightOpen && (
          <button
            className="flex w-7 shrink-0 flex-col items-center gap-2 border-l bg-background pt-2 text-muted-foreground hover:bg-muted"
            onClick={() => setRightOpen(true)}
            title="Expand TEXT"
          >
            <span className="text-[10px]">◀</span>
            <span className="text-[10px] [writing-mode:vertical-rl]">TEXT</span>
          </button>
        )}
      </div>

      <SettingsDialog
        open={settingsOpen}
        settings={settings}
        fluxAvailable={fluxAvailable}
        fonts={fontChoices}
        font={font}
        onFont={set_font}
        onChange={setSettings}
        onClose={() => setSettingsOpen(false)}
      />

      <Toasts items={toasts} onClose={closeToast} />

      {/* 하단 상태 줄 */}
      <footer className="flex h-7 shrink-0 items-center gap-3 border-t bg-background px-3 text-[11px] text-muted-foreground">
        <span>{contents.length} texts</span>
        <span>·</span>
        <span>{viewLabel[shownView]} view</span>
        <span>·</span>
        <span>{settings.source} → {settings.target}</span>
        {/* TRANSLATE 진행 막대: 칸 = API 호출, 응답이 온 칸만 색칠 */}
        {callBar && (
          <div className="ml-auto flex h-1.5 w-40 shrink-0 gap-0.5" title={`${callBar.filter(Boolean).length}/${callBar.length}`}>
            {callBar.map((done, k) => (
              <div key={k} className={`flex-1 rounded-sm ${done ? "bg-primary" : "bg-border"}`} />
            ))}
          </div>
        )}
        {progress && (
          <span className={`${callBar ? "" : "ml-auto "}rounded-full px-2.5 py-0.5 ${isError ? "bg-destructive/10 text-destructive" : "bg-accent text-accent-foreground"}`}>
            {progress}
          </span>
        )}
      </footer>
    </div>
  );
}
