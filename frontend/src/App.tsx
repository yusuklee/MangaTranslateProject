import { useState, type FormEvent, useRef, useEffect } from "react";
import { Project } from "./Project";
import { set, get } from "idb-keyval";

function App() {
  const [projects, setProjects] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [current, setCurrent] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);

  const createProject = (event: FormEvent) => {
    event.preventDefault();
    const projectName = name.trim();
    if (!projectName) return;
    setProjects([...projects, projectName]);
    setName("")
  };

  const [pages, setPages] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const selFolder = () => {
    fileRef.current?.click();
  };

  const handleFolder = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files ?? []);
    const projectName = name.trim()
    setFiles(selectedFiles);
    await set(`project-${projectName}`, selectedFiles);
    setProjects((prev) => [...prev, projectName]);
    setName("");
  };

  if (current)
    return (
      <Project
        name={current}
        onBack={() => setCurrent(null)}
        pages={files.map((f) => URL.createObjectURL(f))}
      />
    );

  return (
    <div className="mx-auto flex max-w-240 gap-6 p-10 border-1 rounded-xl border-black">
      <aside className="w-70 shrink-0 ">
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <p className="mt-1 text-sm text-gray-500">
          Open a workspace or start a new translation
        </p>

        <form onSubmit={createProject} className="mt-6 grid gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my new project"
            className="h-9 rounded-md border border-gray-300 px-3 text-sm outline-none focus:border-gray-900"
          />
          <button
            type="button"
            disabled={!name.trim()}
            className="h-9 rounded-md bg-pink-700 text-sm font-medium text-white disabled:opacity-40"
            onClick={selFolder}
          >
            + Create
          </button>

          <input
            ref={fileRef}
            type="file"
            multiple
            {...{ webkitdirectory: "" }}
            className="hidden"
            onChange={handleFolder}
          />
        </form>
      </aside>

      <section className="min-w-0 flex-1 rounded-xl border border-gray-200">
        <header className="flex h-14 items-center border-b border-gray-200 px-5">
          <h2 className="text-sm font-semibold">Your projects</h2>
          <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
            {projects.length}
          </span>
        </header>

        {projects.length === 0 ? (
          <p className="p-10 text-center text-sm text-gray-400">
            No projects available
          </p>
        ) : (
          <ul className="p-2">
            {projects.map((p) => (
              <li key={p}>
                <button
                  onClick={async () => {
                    setFiles((await get(`project-${p}`)) ?? []);
                    setCurrent(p);
                    
                  }}
                  className="w-full rounded-lg px-3 py-2.5 text-left text-sm hover:bg-gray-100"
                >
                  📁 {p}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default App;
