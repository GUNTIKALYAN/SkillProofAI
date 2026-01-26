from typing import Dict, List, Set
from Backend.app.utils.constants import SKILL_IMPLICATIONS,SKILL_VOCABULARY

# Skill Normalization Helpers

def normalize_skill(skill: str) -> str:
    """
    Normalizes a skill string for comparison.
    """
    return skill.lower().strip()


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
            claimed_skills.add(skill)

    #  Implicit matches (libraries → skills)
    for parent_skill, indicators in SKILL_IMPLICATIONS.items():
        for indicator in indicators:
            if indicator in combined_text:
                claimed_skills.add(parent_skill)
                break  # one indicator is enough

    return claimed_skills



def extract_jd_skills(jd_data: Dict) -> Dict[str, Set[str]]:
    """
    Normalizes JD required and preferred skills.
    """

    return {
        "required": set(normalize_skill(s) for s in jd_data.get("required", [])),
        "preferred": set(normalize_skill(s) for s in jd_data.get("preferred", []))
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
