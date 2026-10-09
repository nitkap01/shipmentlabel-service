"""SHIP-8: file manager for everything kept under the storage root (label PDFs in <label_directory>/YYYY/MM/, bulk
uploads), plus the backup panel.

  GET  /api/files?path=           folders + files of one folder (each label PDF linked to its label)
  GET  /api/files/file?path=      download one file
  POST /api/files/zip             {paths:[files or folders]} -> zip
  POST /api/files/delete          {paths:[files], confirm:"DELETE"} -> files removed; label records kept (pdf_deleted_at)
  GET  /api/backup                last backup result (written by the server's backup job) + whether one is queued
  POST /api/backup/run            ask the server's backup job to run now (incremental upload to S3)
  GET  /api/backup/download       zip of all files + the latest database copy

Hidden entries (names starting with '.', e.g. the backup job's `.backup/` folder) are never listed or touched.
The S3 upload itself runs on the server host (deploy/aws/backup.sh): the app has no AWS credentials.
"""

import datetime
import json
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.db import get_db
from app.models import Label
from app.security import require_admin
from app.storage import StorageDirectoryNotFound, StoragePathError, resolve_existing_directory, storage_root

router = APIRouter(dependencies=[Depends(require_admin)])

BACKUP_DIR = ".backup"
DB_DUMP = "db-latest.sql.gz"


class PathsRequest(BaseModel):
    paths: list[str]


class DeleteRequest(BaseModel):
    paths: list[str]
    confirm: str


def _hidden(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def _resolve_entry(raw: str) -> tuple[Path, str]:
    """A file or folder under the storage root (never hidden, never outside). Returns (absolute, relative)."""
    if not raw or "\x00" in raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise HTTPException(status_code=400, detail="Invalid path")
    root = storage_root()
    target = (root / raw.strip("/")).resolve()
    if not target.is_relative_to(root) or target == root:
        raise HTTPException(status_code=400, detail="Invalid path")
    rel = target.relative_to(root)
    if _hidden(rel):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {rel}")
    return target, str(rel)


def _walk_files(target: Path) -> list[Path]:
    root = storage_root()
    if target.is_file():
        return [target]
    out = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if not name.startswith(".") and p.resolve().is_relative_to(root):
                out.append(p)
    return out


def _zip_response(files: list[Path], name: str, extra: list[tuple[Path, str]] = ()) -> FileResponse:
    root = storage_root()
    tmp = tempfile.NamedTemporaryFile(prefix="files-", suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, arcname=str(p.relative_to(root)))
        for p, arcname in extra:
            zf.write(p, arcname=arcname)
    return FileResponse(tmp.name, media_type="application/zip", filename=name,
                        background=BackgroundTask(os.unlink, tmp.name))


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M")


@router.get("/files")
async def list_folder(path: str = Query(""), db: AsyncSession = Depends(get_db)):
    root = storage_root()
    try:
        directory = resolve_existing_directory(path)
    except StorageDirectoryNotFound:
        raise HTTPException(status_code=404, detail="Folder not found")
    except StoragePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    rel_dir = directory.relative_to(root)
    if _hidden(rel_dir):
        raise HTTPException(status_code=400, detail="Invalid path")

    folders, files = [], []
    for entry in sorted(directory.iterdir(), key=lambda e: e.name.lower()):
        if entry.name.startswith(".") or not entry.resolve().is_relative_to(root):
            continue
        rel = str(entry.relative_to(root))
        if entry.is_dir():
            count = sum(1 for _ in _walk_files(entry))
            folders.append({"name": entry.name, "path": rel, "file_count": count})
        elif entry.is_file():
            st = entry.stat()
            files.append({"name": entry.name, "path": rel, "size": st.st_size,
                          "modified": datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).isoformat()})

    if files:
        labels = (await db.execute(select(Label).where(Label.pdf_path.in_([f["path"] for f in files])))).scalars().all()
        by_path = {label.pdf_path: label for label in labels}
        for f in files:
            label = by_path.get(f["path"])
            f["label"] = ({"id": label.id, "status": label.status, "tracking_number": label.tracking_number,
                           "recipient_name": label.recipient_name} if label else None)
    return {"path": "" if str(rel_dir) == "." else str(rel_dir), "folders": folders, "files": files}


@router.get("/files/file")
async def download_one(path: str = Query(...)):
    target, rel = _resolve_entry(path)
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    return FileResponse(target, filename=target.name)


@router.post("/files/zip")
async def download_zip(payload: PathsRequest):
    if not payload.paths:
        raise HTTPException(status_code=400, detail="Nothing selected")
    files: list[Path] = []
    for raw in payload.paths:
        target, _ = _resolve_entry(raw)
        files += _walk_files(target)
    unique = sorted(set(files))
    if not unique:
        raise HTTPException(status_code=400, detail="The selection has no files")
    return _zip_response(unique, f"labels-{_stamp()}.zip")


@router.post("/files/delete")
async def delete_files(payload: DeleteRequest, db: AsyncSession = Depends(get_db)):
    if payload.confirm != "DELETE":
        raise HTTPException(status_code=400, detail='Type DELETE to confirm')
    if not payload.paths:
        raise HTTPException(status_code=400, detail="Nothing selected")
    targets = []
    for raw in payload.paths:
        target, rel = _resolve_entry(raw)
        if not target.is_file():
            raise HTTPException(status_code=400, detail=f"Only files can be deleted, not folders: {rel}")
        targets.append((target, rel))
    now = datetime.datetime.now(datetime.timezone.utc)
    for target, _ in targets:
        target.unlink()
    result = await db.execute(
        update(Label).where(Label.pdf_path.in_([rel for _, rel in targets]))
        .values(pdf_path=None, pdf_size_bytes=None, pdf_deleted_at=now)
    )
    await db.commit()
    return {"deleted": len(targets), "labels_updated": result.rowcount or 0}


# ---- backup panel -----------------------------------------------------------------------------------------------

def _backup_dir() -> Path:
    d = storage_root() / BACKUP_DIR
    d.mkdir(exist_ok=True)
    return d


@router.get("/backup")
async def backup_status():
    d = _backup_dir()
    status = None
    if (d / "status.json").exists():
        try:
            status = json.loads((d / "status.json").read_text())
        except ValueError:
            status = {"ok": False, "error": "status file unreadable"}
    request = (d / "request").exists()
    return {"last": status, "queued": request, "db_copy_available": (d / DB_DUMP).exists()}


@router.post("/backup/run")
async def backup_run():
    d = _backup_dir()
    (d / "request").write_text(json.dumps({"requested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}))
    return {"queued": True}


@router.get("/backup/download")
async def backup_download():
    root = storage_root()
    files = _walk_files(root)
    dump = _backup_dir() / DB_DUMP
    extra = [(dump, f"database/{DB_DUMP}")] if dump.exists() else []
    if not files and not extra:
        raise HTTPException(status_code=404, detail="Nothing to back up yet")
    return _zip_response(files, f"shipmentlabel-backup-{_stamp()}.zip", extra)
