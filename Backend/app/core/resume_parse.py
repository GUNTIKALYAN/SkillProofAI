import logging
import os
import zipfile

import pdfplumber
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pdfplumber.utils.exceptions import PdfminerException

from app.utils.constants import EXPERIENCE_HEADERS, PROJECT_HEADERS, SKILL_HEADERS
from app.utils.text_utils import is_header, normalize_text

logger = logging.getLogger(__name__)

_UNREADABLE = (PdfminerException, PackageNotFoundError, zipfile.BadZipFile)


def parse_resume(file_path: str) -> dict[str, list[str]]:
    if not os.path.exists(file_path):
        raise FileNotFoundError("Resume file not found")

    ext = file_path.lower()

    try:
        if ext.endswith(".pdf"):
            raw_text = extract_text_from_pdf(file_path)
        elif ext.endswith(".docx"):
            raw_text = extract_text_from_docx(file_path)
        else:
            raise ValueError("Unsupported file type. Only PDF and DOCX are allowed.")
    except ValueError:
        raise
    except _UNREADABLE as exc:
        logger.warning("resume parse failed error=%s", type(exc).__name__)
        raise ValueError("Could not read the resume file") from exc

    sections = _split_sections(raw_text)
    sections["text"] = [raw_text]
    return sections


def extract_text_from_pdf(file_path: str) -> str:
    text_chunks = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text_chunks.append(page.extract_text())

    if not text_chunks:
        raise ValueError("No text extracted from PDF")

    return normalize_text("\n".join(text_chunks))


def extract_text_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    text_chunks = [p.text for p in doc.paragraphs if p.text.strip()]

    if not text_chunks:
        raise ValueError("No text extracted from DOCX")

    return normalize_text("\n".join(text_chunks))


def _split_sections(text: str) -> dict[str, list[str]]:
    lines = text.split("\n")

    sections = {
        "skills": [],
        "projects": [],
        "experience": []
    }

    current_section = None

    for line in lines:
        clean = line.lower().rstrip(":")

        if is_header(clean, SKILL_HEADERS):
            current_section = "skills"
            continue
        if is_header(clean, PROJECT_HEADERS):
            current_section = "projects"
            continue
        if is_header(clean, EXPERIENCE_HEADERS):
            current_section = "experience"
            continue

        if current_section and line.strip():
            sections[current_section].append(line.strip())

    return sections
