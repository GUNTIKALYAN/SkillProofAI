import os
from typing import Dict, List

import pdfplumber
from docx import Document

from Backend.app.utils.constants import (
    SKILL_HEADERS,
    PROJECT_HEADERS,
    EXPERIENCE_HEADERS
)
from Backend.app.utils.text_utils import is_header, normalize_text


def parse_resume(file_path: str) -> Dict[str, List[str]]:
    if not os.path.exists(file_path):
        raise FileNotFoundError("Resume file not found")

    ext = file_path.lower()

    if ext.endswith(".pdf"):
        raw_text = extract_text_from_pdf(file_path)
    elif ext.endswith(".docx"):
        raw_text = extract_text_from_docx(file_path)
    else:
        raise ValueError("Unsupported file type. Only PDF and DOCX are allowed.")

    return _split_sections(raw_text)


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


def _split_sections(text: str) -> Dict[str, List[str]]:
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
