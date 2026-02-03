
def extract_jd_skills(jd_data: dict) -> list[str]:
    """
    Flattens required + preferred JD skills
    """
    return list(set(
        jd_data.get("required", []) +
        jd_data.get("preferred", [])
    ))
