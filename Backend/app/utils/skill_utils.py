from typing import Set
from Backend.app.utils.constants import SKILL_IMPLICATIONS


def normalize_skill(skill: str) -> str:
    return skill.lower().strip()


def infer_skills_from_text(text: str) -> Set[str]:
    """
    Infers high-level skills from low-level mentions.

    Example:
    "sklearn pandas numpy" → "machine learning", "data science"
    """

    text = text.lower()
    inferred = set()

    for high_level_skill, indicators in SKILL_IMPLICATIONS.items():
        if any(indicator in text for indicator in indicators):
            inferred.add(high_level_skill)

    return inferred
