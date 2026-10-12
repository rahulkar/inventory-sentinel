"""Helpers shared by routers."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from app import config
from app.services import storage

ZIP_MAGIC = b"PK\x03\x04"


async def stream_upload(file: UploadFile, dest: Path) -> tuple[int, bool]:
    """Stream an upload to `dest` in 1 MB chunks. Returns (bytes written, is_zip)."""
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    is_zip = False
    first = True
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as out:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            if first:
                is_zip = chunk[:4] == ZIP_MAGIC
                first = False
            written += len(chunk)
            if written > limit:
                out.close()
                storage.safe_unlink(tmp)
                raise HTTPException(400, f"File exceeds the {config.MAX_UPLOAD_MB} MB upload limit.")
            out.write(chunk)
    if written == 0:
        storage.safe_unlink(tmp)
        raise HTTPException(400, "The uploaded file is empty.")
    tmp.replace(dest)
    return written, is_zip
