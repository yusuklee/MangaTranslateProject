"""프로젝트 디스크 저장 (코하루 방식: 프로젝트 = 폴더 하나, 원본을 복사해 자기 완결).

%LOCALAPPDATA%\\MangaTranslator\\projects\\<이름>\\
    project.json     이름, 만든 날짜, 페이지 목록, 페이지별 글자 상자·번역문
    pages\\0001.webp  원본 복사본 (번호_원래이름)
    erased\\0001.png  인페인팅 결과

저장은 임시 파일에 쓴 뒤 이름을 바꿔서(교체) 쓰다 꺼져도 이전 상태가 남는다. 직전 파일은 project.json.bak 으로 남겨 두고,
project.json 이 깨져 있으면 .bak 을 읽는다.
project.json 을 읽고-고치고-쓰는 구간은 프로젝트별 잠금으로 묶는다. (자동 저장 PUT state 와 인페인팅 결과 PUT erased 가
동시에 들어오면 같은 임시 파일을 둘이 쓰다 섞여서 JSON 이 깨진 적이 있다.)
"""
import json
import os
import re
import shutil
import tempfile
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile   # request.form() 이 주는 파일 객체는 starlette 것 (fastapi.UploadFile 로 isinstance 하면 다 걸러진다)

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".avif")


def projects_root():
    root = os.environ.get("MANGA_PROJECTS_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "MangaTranslator", "projects"
    )
    os.makedirs(root, exist_ok=True)
    return root


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    return name or "untitled"


def project_dir(name, must_exist=True):
    d = os.path.join(projects_root(), safe_name(name))
    if must_exist and not os.path.isfile(os.path.join(d, "project.json")):
        raise HTTPException(404, f"project not found: {name}")
    return d


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


_locks = {}
_locks_guard = threading.Lock()


def project_lock(name):
    """프로젝트 하나의 project.json 읽기-고치기-쓰기를 직렬화하는 잠금"""
    with _locks_guard:
        return _locks.setdefault(safe_name(name), threading.Lock())


def write_json_atomic(path, data):
    fd, tmp = tempfile.mkstemp(prefix=".project-", suffix=".tmp", dir=os.path.dirname(path))   # 고유한 임시 파일명 (동시에 써도 안 섞임)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    if os.path.isfile(path):
        shutil.copyfile(path, path + ".bak")
    os.replace(tmp, path)


def load_meta(d):
    path = os.path.join(d, "project.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        if not os.path.isfile(path + ".bak"):
            raise
        print(f"[projects] {path} is corrupted, using .bak", flush=True)
        with open(path + ".bak", encoding="utf-8") as f:
            return json.load(f)


def save_meta(d, meta):
    meta["updated"] = time.time()
    write_json_atomic(os.path.join(d, "project.json"), meta)


#페이지 파일명: 0001_원래이름.webp 처럼 번호를 붙여 순서를 고정한다
def page_filename(index, original):
    stem, ext = os.path.splitext(os.path.basename(original))
    return f"{index + 1:04d}_{safe_name(stem)}{ext.lower() or '.png'}"


def detail(meta):
    """프런트가 쓰는 형태. 파일 URL 은 /projects/<이름>/file/... 로"""
    name = meta["name"]
    base = f"/projects/{name}"
    return {
        "name": name,
        "created": meta.get("created"),
        "updated": meta.get("updated"),
        "pages": [
            {"file": p["file"], "name": p["name"], "url": f"{base}/file/pages/{p['file']}"} for p in meta["pages"]
        ],
        "contents": meta.get("contents", {}),
        "erased": {f: f"{base}/file/erased/{f}.png" for f in meta.get("erased", [])},
    }


router = APIRouter(prefix="/projects")


@router.get("")
def list_projects():
    out = []
    for d in sorted(os.listdir(projects_root())):
        path = os.path.join(projects_root(), d, "project.json")
        if not os.path.isfile(path):
            continue
        try:
            meta = load_meta(os.path.join(projects_root(), d))
        except Exception:
            continue
        out.append({
            "name": meta["name"],
            "pages": len(meta["pages"]),
            "created": meta.get("created"),
            "updated": meta.get("updated"),
            "done": len(meta.get("erased", [])),
            "thumb": f"/projects/{meta['name']}/file/pages/{meta['pages'][0]['file']}" if meta["pages"] else None,
        })
    return sorted(out, key=lambda p: -(p.get("updated") or 0))


def _create(name, sources):
    """sources: [(원래 파일명, bytes 또는 경로)]"""
    name = safe_name(name)
    d = project_dir(name, must_exist=False)
    if os.path.exists(d):
        raise HTTPException(409, f"project already exists: {name}")
    os.makedirs(os.path.join(d, "pages"))
    os.makedirs(os.path.join(d, "erased"))
    pages = []
    for i, (orig, src) in enumerate(sources):
        fname = page_filename(i, orig)
        dst = os.path.join(d, "pages", fname)
        if isinstance(src, (bytes, bytearray)):
            with open(dst, "wb") as f:
                f.write(src)
        else:
            shutil.copy2(src, dst)
        pages.append({"file": fname, "name": os.path.basename(orig)})
    meta = {"name": name, "created": time.time(), "pages": pages, "contents": {}, "erased": []}
    save_meta(d, meta)
    return detail(meta)


#앱: 폴더 경로로 만들기. body {"name": "...", "folder": "C:\\..."} (이름이 비면 폴더 이름)
@router.post("/from_folder")
def create_from_folder(body: dict):
    folder = os.path.abspath(body["folder"])
    if not os.path.isdir(folder):
        raise HTTPException(400, "folder not found")
    files = sorted((f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXT)), key=natural_key)
    if not files:
        raise HTTPException(400, "no image_samples in folder")
    name = (body.get("name") or "").strip() or os.path.basename(folder)
    return _create(name, [(f, os.path.join(folder, f)) for f in files])


#브라우저: 파일 업로드로 만들기 (multipart: name, files[])
@router.post("/upload")
async def create_from_upload(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    files = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    files = [f for f in files if (f.filename or "").lower().endswith(IMAGE_EXT)]
    if not files:
        raise HTTPException(400, "no image_samples")
    files.sort(key=lambda f: natural_key(f.filename or ""))
    if not name:
        first = files[0].filename or ""
        name = first.split("/")[0] if "/" in first else "untitled"
    sources = [(os.path.basename(f.filename or f"page{i}.png"), await f.read()) for i, f in enumerate(files)]
    return _create(name, sources)


@router.get("/{name}")
def get_project(name: str):
    return detail(load_meta(project_dir(name)))


#작업 결과 저장: body {"contents": {file: [Content...]}}. 페이지별 글자 상자·번역문 전체를 덮어쓴다
@router.put("/{name}/state")
def put_state(name: str, body: dict):
    d = project_dir(name)
    with project_lock(name):
        meta = load_meta(d)
        if "contents" in body:
            meta["contents"] = body["contents"]
        save_meta(d, meta)
    return {"ok": True}


#인페인팅 결과 저장: 본문이 PNG 바이트
@router.put("/{name}/erased/{file}")
async def put_erased(name: str, file: str, request: Request):
    d = project_dir(name)
    data = await request.body()
    if not data.startswith(b"\x89PNG"):
        raise HTTPException(400, "expected PNG")
    with project_lock(name):
        meta = load_meta(d)
        if not any(p["file"] == file for p in meta["pages"]):
            raise HTTPException(404, "page not in project")
        path = os.path.join(d, "erased", file + ".png")
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
        if file not in meta.setdefault("erased", []):
            meta["erased"].append(file)
        save_meta(d, meta)
    return {"url": f"/projects/{meta['name']}/file/erased/{file}.png"}


#인페인팅 결과 삭제 (DETECT 를 다시 하면 이전 결과는 무효)
@router.delete("/{name}/erased/{file}")
def delete_erased(name: str, file: str):
    d = project_dir(name)
    with project_lock(name):
        meta = load_meta(d)
        path = os.path.join(d, "erased", file + ".png")
        if os.path.isfile(path):
            os.remove(path)
        if file in meta.get("erased", []):
            meta["erased"].remove(file)
            save_meta(d, meta)
    return {"ok": True}


@router.get("/{name}/file/{kind}/{file}")
def get_file(name: str, kind: str, file: str):
    if kind not in ("pages", "erased") or "/" in file or "\\" in file or ".." in file:
        raise HTTPException(400, "bad path")
    path = os.path.join(project_dir(name), kind, file)
    if not os.path.isfile(path):
        raise HTTPException(404, "file not found")
    #CORS 헤더를 항상 붙인다. 개발 중(프런트 5173, 서버 8000)엔 <img> 가 먼저 받아 캐시된 응답에 이 헤더가 없어서,
    #같은 파일을 fetch() 로 다시 받는 썸네일이 캐시에서 "Failed to fetch" 로 실패했다 (현재 페이지인 1페이지만 그랬던 이유)
    return FileResponse(path, headers={"Access-Control-Allow-Origin": "*"})


@router.delete("/{name}")
def delete_project(name: str):
    d = project_dir(name)
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}
