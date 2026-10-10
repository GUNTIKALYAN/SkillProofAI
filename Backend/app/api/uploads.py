import io
import logging
import os
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import get_settings

logger = logging.getLogger(__name__)

PDF_SUFFIX = ".pdf"
DOCX_SUFFIX = ".docx"
ALLOWED_SUFFIXES = {PDF_SUFFIX, DOCX_SUFFIX}


def _read_limited(upload: UploadFile, limit: int) -> bytes:
    content = upload.file.read(limit + 1)
    if len(content) > limit:
        megabytes = max(limit // (1024 * 1024), 1)
        raise HTTPException(
            status_code=413,
            detail=f"Resume must be {megabytes} MB or smaller",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Resume file is empty")
    return content


def _suffix(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Resume must be a PDF or DOCX file")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Resume must be a PDF or DOCX file")
    return suffix


def _is_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF")


def _is_docx(content: bytes) -> bool:
    if not content.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _require_type(suffix: str, content: bytes) -> None:
    matches = _is_pdf(content) if suffix == PDF_SUFFIX else _is_docx(content)
    if not matches:
        raise HTTPException(
            status_code=400,
            detail="Resume file content does not match a PDF or DOCX",
        )


@contextmanager
def resume_file(upload: UploadFile) -> Iterator[str]:
    settings = get_settings()
    content = _read_limited(upload, settings.max_upload_bytes)
    suffix = _suffix(upload.filename)
    _require_type(suffix, content)

    descriptor, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            logger.warning("Could not remove temporary resume file")
