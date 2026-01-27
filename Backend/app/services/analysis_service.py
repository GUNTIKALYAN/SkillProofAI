from app.core.resume_parse import parse_resume
from app.core.jd_analyzer import analyze_job_description
from app.core.skill_mapper import map_skills
from app.core.github_fetcher import fetch_github_evidence
from app.core.evidence_validator import validate_skill_evidence
from app.agents.agent_runner import run_agents


def clean_ai_output(ai_output: dict) -> dict:
    """
    Removes prompt-leaked keys like 'output_format'.
    """
    if isinstance(ai_output, dict):
        for _, value in ai_output.items():
            if isinstance(value, dict):
                value.pop("output_format", None)
    return ai_output


def run_full_analysis(
    resume_path: str,
    jd_text: str,
    github_username: str | None,
    include_github: bool
):
    # -------------------------
    # Deterministic pipeline
    # -------------------------
    resume_data = parse_resume(resume_path)
    jd_data = analyze_job_description(jd_text)
    skill_mapping = map_skills(resume_data, jd_data)

    github_evidence = {}
    if include_github and github_username:
        github_evidence = fetch_github_evidence(github_username)

    validation = validate_skill_evidence(
        jd_data,
        skill_mapping,
        github_evidence
    )

    # -------------------------
    # Build AI agent inputs (CRITICAL FIX)
    # -------------------------

    # 1. Skill evidence for SkillAuditAgent
    skill_evidence = {
        skill: {"status": data["status"]}
        for skill, data in validation.items()
    }

    # 2. Missing skills for GapAnalysisAgent
    missing_skills = {
        skill: data["reason"]
        for skill, data in validation.items()
        if data["status"] == "unsupported"
    }

    # 3. ATS input
    ats_data = {
        "current_score": 70,  # baseline heuristic
        "missing_keywords": list(missing_skills.keys())
    }

    ai_input = {
        "skill_evidence": skill_evidence,
        "missing_skills": missing_skills,
        "ats_data": ats_data
    }

    # -------------------------
    # Run multi-agent graph
    # -------------------------
    ai_analysis = run_agents(ai_input)
    ai_analysis = clean_ai_output(ai_analysis)

    # -------------------------
    # Final API response
    # -------------------------
    return {
        "skill_mapping": skill_mapping,
        "evidence_validation": validation,
        "ai_analysis": ai_analysis
    }
