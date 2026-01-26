from typing import Dict


def validate_skill_evidence(jd_data: Dict,skill_mapping: Dict,github_evidence: Dict) -> Dict[str, Dict[str, str]]:
    """
    Validates each JD skill using resume claims + GitHub evidence.

    Output:
    {
      "skill": {
        "status": "supported | partially_supported | unsupported",
        "reason": "explanation"
      }
    }
    """

    results = {}

    required_skills = set(jd_data.get("required", []))
    preferred_skills = set(jd_data.get("preferred", []))

    matched = set(skill_mapping.get("matched", []))
    missing = set(skill_mapping.get("missing", []))

    all_jd_skills = required_skills.union(preferred_skills)

    for skill in all_jd_skills:
        evidence = github_evidence.get(skill, {})

        repos = evidence.get("repos", [])
        recent = evidence.get("recent_activity", False)

        # CASE 1: Fully supported
        if skill in matched and repos and recent:
            results[skill] = {
                "status": "supported",
                "reason": "Claimed in resume and backed by recent GitHub activity"
            }

        # CASE 2: Partially supported
        elif (skill in matched and not repos) or (skill in missing and repos):
            results[skill] = {
                "status": "partially_supported",
                "reason": "Some evidence exists but not strong enough to fully support the claim"
            }

        # CASE 3: Unsupported
        else:
            if skill in required_skills:
                results[skill] = {
                    "status": "unsupported",
                    "reason": "Required skill with no resume or GitHub evidence"
                }
            else:
                results[skill] = {
                    "status": "unsupported",
                    "reason": "Preferred skill without supporting evidence"
                }

    return results
