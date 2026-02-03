from app.utils.constants import SKILL_VOCABULARY

def extract_resume_skills(resume_data: dict) -> list[str]:
    text = " ".join(
        resume_data.get("skills", []) +
        resume_data.get("projects", []) +
        resume_data.get("experience", [])
    ).lower()

    return [skill for skill in SKILL_VOCABULARY if skill in text]
