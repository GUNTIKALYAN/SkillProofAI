from typing import Dict


def validate_skill_evidence(
    jd_data: Dict,
    skill_mapping: Dict,
    github_evidence: Dict
) -> Dict[str, Dict[str, str]]:
    """
    Intern-friendly skill evidence validation.

    Rules:
    - Resume/project presence is valid evidence for interns
    - GitHub strengthens evidence but is not mandatory
    - Unsupported means truly no signal anywhere
    """

    results = {}

    required = set(jd_data.get("required", []))
    preferred = set(jd_data.get("preferred", []))

    matched = set(skill_mapping.get("matched", []))

    all_skills = required.union(preferred)

    for skill in all_skills:
        gh = github_evidence.get(skill, {})

        repos = gh.get("repos", [])
        recent = gh.get("recent_activity", False)

        in_resume = skill in matched
        has_github_signal = bool(repos or recent)

        # 1️⃣ Fully supported
        if in_resume and has_github_signal:
            results[skill] = {
                "status": "supported",
                "reason": "Skill appears in resume/projects and is reinforced by GitHub activity"
            }

        # 2️⃣ Resume-only OR GitHub-only → partially supported
        elif in_resume or has_github_signal:
            results[skill] = {
                "status": "partially_supported",
                "reason": "Skill is present in resume or has limited supporting evidence"
            }

        # 3️⃣ Truly unsupported
        else:
            results[skill] = {
                "status": "unsupported",
                "reason": (
                    "Required skill with no resume or GitHub evidence"
                    if skill in required
                    else "Preferred skill without supporting evidence"
                )
            }

    return results
