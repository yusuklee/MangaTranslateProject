import { useEffect, useRef, useState } from "react";
import { Project, type Content } from "./Project";
import { API } from "./api";

//시작 화면: 위쪽 우주 띠(앱 이름) + 새 프로젝트 카드 / 프로젝트 카드 격자
//프로젝트는 백엔드가 디스크에 저장한다 (%LOCALAPPDATA%\MangaTranslator\projects\<이름>). 앱을 껐다 켜도 목록이 남는다

//백엔드 /projects 응답
type ProjectSummary = { name: string; pages: number; done: number; updated?: number; thumb?: string | null };
export type ProjectDetail = {
  name: string;
  pages: { file: string; name: string; url: string }[];
  contents: Record<string, Content[]>;
  erased: Record<string, string>;
};

//데스크톱 앱(pywebview)이면 window.pywebview.api 가 있다. 폴더 선택창을 앱이 직접 띄운다
declare global {
  interface Window {
    pywebview?: { api: { pick_folder(): Promise<{ path: string } | null>; fullscreen(): Promise<void> } };
  }
}
const isDesktop = () => !!window.pywebview?.api;

const okJson = async (r: Response) => {
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 300)}`);
  return r.json();
};

function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [name, setName] = useState("");
  const [current, setCurrent] = useState<ProjectDetail | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () =>
    fetch(`${API}/projects`).then(okJson).then(setProjects).catch(() => setProjects([]));
  useEffect(() => {
    refresh();
  }, []);

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  //"Choose a folder": 앱이면 윈도우 폴더 창 → 경로를 백엔드에 넘겨 만든다. 브라우저면 숨은 file input
  const chooseFolder = async () => {
    if (!isDesktop()) return fileRef.current?.click();
    const picked = await window.pywebview!.api.pick_folder();
    if (!picked) return;
    setBusy("Creating project...");
    try {
      const d: ProjectDetail = await fetch(`${API}/projects/from_folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), folder: picked.path }),
      }).then(okJson);
      setName("");
      await refresh();
      setCurrent(d);
    } catch (e) {
      fail(e);
    } finally {
      setBusy("");
    }
  };

  const handleFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    const form = new FormData();
    form.append("name", name.trim());
    for (const f of files) form.append("files", f, f.webkitRelativePath || f.name);
    setBusy(`Copying ${files.length} pages...`);
    try {
      const d: ProjectDetail = await fetch(`${API}/projects/upload`, { method: "POST", body: form }).then(okJson);
      setName("");
      await refresh();
      setCurrent(d);
    } catch (err) {
      fail(err);
    } finally {
      setBusy("");
    }
  };

  const open = async (p: ProjectSummary) => {
    try {
      setCurrent(await fetch(`${API}/projects/${encodeURIComponent(p.name)}`).then(okJson));
    } catch (e) {
      fail(e);
    }
  };

  const remove = async (p: ProjectSummary) => {
    if (!window.confirm(`Delete project "${p.name}"? This removes its copied pages and results. This cannot be undone.`)) return;
    try {
      await fetch(`${API}/projects/${encodeURIComponent(p.name)}`, { method: "DELETE" }).then(okJson);
      await refresh();
    } catch (e) {
      fail(e);
    }
  };

  if (current)
    return (
      <Project
        project={current}
        onBack={() => {
          setCurrent(null);
          refresh();
        }}
      />
    );

  return (
    <div className="min-h-screen bg-muted/60">
      {/* 위쪽 띠: 우주 사진(public/space.png) 위에 어두운 그라데이션을 깔아 글자가 읽히게 */}
      <header className="relative overflow-hidden px-8 pb-16 pt-12 text-white">
        <div className="absolute inset-0 bg-[url('/space.png')] bg-cover bg-center" aria-hidden />
        <div className="absolute inset-0 bg-[linear-gradient(to_bottom,rgba(10,16,51,0.35),rgba(10,16,51,0.75))]" aria-hidden />
        <div className="relative mx-auto max-w-5xl">
          <p className="text-[11px] font-semibold tracking-[0.25em] text-white/60">MANGA TRANSLATOR</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-white/70">Pick a folder of manga pages. Detect, translate, erase, render, export.</p>
        </div>
      </header>

      <main className="relative z-10 mx-auto -mt-8 grid max-w-5xl gap-6 px-8 pb-12 md:grid-cols-[18rem_1fr]">
        {/* 새 프로젝트 */}
        <section className="rounded-2xl border bg-background p-5 shadow-[0_8px_30px_rgba(10,16,51,0.10)]">
          <h2 className="text-sm font-semibold">New project</h2>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name (optional)"
            className="mt-3 h-9 w-full rounded-lg border bg-background px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          />
          <button
            type="button"
            disabled={!!busy}
            onClick={chooseFolder}
            className="mt-3 flex w-full flex-col items-center gap-1 rounded-xl border-2 border-dashed border-primary/40 bg-accent/40 px-4 py-6 text-sm transition-colors hover:border-primary hover:bg-accent disabled:opacity-60"
          >
            <span className="text-2xl">📂</span>
            <span className="font-medium text-accent-foreground">{busy || "Choose a folder"}</span>
            <span className="text-[11px] text-muted-foreground">Images inside become pages</span>
          </button>
          <input ref={fileRef} type="file" multiple {...{ webkitdirectory: "" }} className="hidden" onChange={handleFiles} />
          {error && (
            <p className="mt-3 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive" onClick={() => setError("")}>
              {error}
            </p>
          )}
        </section>

        {/* 프로젝트 카드 격자 */}
        <section className="rounded-2xl border bg-background p-5 shadow-[0_8px_30px_rgba(10,16,51,0.10)]">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold">Your projects</h2>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">{projects.length}</span>
          </div>

          {projects.length === 0 ? (
            <div className="flex flex-col items-center gap-1 py-14 text-center">
              <span className="text-3xl">🗂</span>
              <p className="text-sm font-medium text-muted-foreground">No projects yet</p>
              <p className="text-[11px] text-muted-foreground/70">Choose a folder on the left to start</p>
            </div>
          ) : (
            <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {projects.map((p) => (
                <li key={p.name} className="group relative">
                  <button
                    onClick={() => open(p)}
                    className="flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-all hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md"
                  >
                    {p.thumb ? (
                      <img src={`${API}${p.thumb}`} alt="" className="h-12 w-9 shrink-0 rounded object-cover ring-1 ring-black/10" />
                    ) : (
                      <span className="flex h-12 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-lg text-accent-foreground">📁</span>
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{p.name}</span>
                      <span className="block text-[11px] text-muted-foreground">
                        {p.pages} pages{p.done ? ` · ${p.done} erased` : ""}
                      </span>
                    </span>
                  </button>
                  <button
                    onClick={() => remove(p)}
                    title="Delete project"
                    className="absolute right-2 top-2 hidden rounded px-1.5 text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover:block"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
