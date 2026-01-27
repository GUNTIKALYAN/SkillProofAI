from typing import Dict, List, Set
import re
from app.utils.constants import SKILL_IMPLICATIONS,SKILL_VOCABULARY

SKILL_SYNONYMS = {
    "promptengineering": "prompt engineering",
    "prompt engineer": "prompt engineering",
    "llms": "llm",
    "large language models": "llm",
    "retrieval augmented generation": "rag",
    "vector databases": "vector database",
    "deep learning": "deep learning",
    "ci cd": "ci/cd",
    "restful apis": "rest api",
    "rest api": "rest api",
    "apis": "rest api",

    "scikit learn": "scikit-learn",
    "scikit-learn": "scikit-learn",

    "rag": "rag",
    "retrieval augmented generation": "rag",

    "langchain": "langchain",
    "langgraph": "langgraph",

    "json apis": "rest api"
}


# Skill Normalization Helpers

def normalize_skill(skill: str) -> str:
    """
    Normalizes a skill string for comparison.
    """
    skill = skill.lower()
    skill = skill.replace("&", "and")
    skill = re.sub(r"[^a-z0-9\s]", " ", skill)  # remove punctuation
    skill = re.sub(r"\s+", " ", skill).strip()
    return skill

def canonicalize_skill(skill: str) -> str:
    """
    Maps skill variants to a canonical form.
    """
    skill = normalize_skill(skill)

    # Apply synonym mapping
    if skill in SKILL_SYNONYMS:
        return SKILL_SYNONYMS[skill]

    return skill


def extract_resume_skills(resume_data: Dict) -> Set[str]:
    """
    Extracts claimed skills from resume skills + projects text.
    Includes implicit inference via tools/libraries.
    """

    text_blocks = []
    text_blocks.extend(resume_data.get("skills", []))
    text_blocks.extend(resume_data.get("projects", []))

    combined_text = " ".join(text_blocks).lower()

    claimed_skills = set()


    #  Direct matches (exact skills)
    for skill in SKILL_VOCABULARY:
        if skill in combined_text:
            claimed_skills.add(canonicalize_skill(skill))

    #  Implicit matches (libraries → skills)
    for parent_skill, indicators in SKILL_IMPLICATIONS.items():
        for indicator in indicators:
            if indicator in combined_text:
                claimed_skills.add(canonicalize_skill(parent_skill))
                break  # one indicator is enough

    return claimed_skills



def extract_jd_skills(jd_data: Dict) -> Dict[str, Set[str]]:
    """
    Normalizes JD required and preferred skills.
    """

    return {
        "required": set(canonicalize_skill(s) for s in jd_data.get("required", [])),
        "preferred": set(canonicalize_skill(s) for s in jd_data.get("preferred", []))
    }


# Public API

def map_skills(resume_data: Dict, jd_data: Dict) -> Dict[str, List[str]]:
    """
    Maps resume skills against JD skills.
    Output contract (LOCKED):
    {
        "matched": [],
        "missing": [],
        "overclaimed": []
    }
    """

    resume_skills = extract_resume_skills(resume_data)
    jd_skills = extract_jd_skills(jd_data)

    required = jd_skills["required"]
    preferred = jd_skills["preferred"]

    all_jd_skills = required.union(preferred)

    matched = []
    missing = []
    overclaimed = []

    # Matched skills
    for skill in all_jd_skills:
        if skill in resume_skills:
            matched.append(skill)

    # Missing skills (ONLY required)
    for skill in required:
        if skill not in resume_skills:
            missing.append(skill)

    # Overclaimed skills
    for skill in resume_skills:
        if skill not in all_jd_skills:
            overclaimed.append(skill)

    return {
        "matched": sorted(matched),
        "missing": sorted(missing),
        "overclaimed": sorted(overclaimed)
    }
