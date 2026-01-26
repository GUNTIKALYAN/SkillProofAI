from typing import Dict, List

from app.utils.constants import (
    REQUIRED_HEADERS,
    PREFERRED_HEADERS,
    SKILL_VOCABULARY
)
from Backend.app.utils.text_utils import is_header


def analyze_job_description(jd_text: str) -> Dict[str, List[str]]:
    if not jd_text.strip():
        raise ValueError("Empty job description")

    sections = _split_jd_sections(jd_text)

    return {
        "required": sorted(_extract_skills(sections["required_text"])),
        "preferred": sorted(_extract_skills(sections["preferred_text"]))
    }


def _split_jd_sections(jd_text: str) -> Dict[str, List[str]]:
    lines = jd_text.split("\n")

    sections = {
        "required_text": [],
        "preferred_text": []
    }

    current = "required_text"

    for line in lines:
        clean = line.lower().rstrip(":")

        if is_header(clean, REQUIRED_HEADERS):
            current = "required_text"
            continue
        if is_header(clean, PREFERRED_HEADERS):
            current = "preferred_text"
            continue

        if line.strip():
            sections[current].append(line.strip())

    return sections


def _extract_skills(text_lines: List[str]) -> List[str]:
    combined = " ".join(text_lines).lower()
    return [skill for skill in SKILL_VOCABULARY if skill in combined]
