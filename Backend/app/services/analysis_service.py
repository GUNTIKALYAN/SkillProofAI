from app.core.resume_parse import parse_resume
from app.core.jd_analyzer import analyze_job_description
from app.core.skill_mapper import map_skills
from app.core.github_fetcher import fetch_github_evidence
from app.core.evidence_validator import validate_skill_evidence
from app.core.ats_scorer import compute_ats_score
from app.core.jd_utils import extract_jd_skills
from app.core.resume_utils import extract_resume_skills
from app.agents.agent_runner import run_agents


def run_full_analysis(
    resume_path: str,
    jd_text: str,
    github_username: str | None,
    include_github: bool
):
    # -------------------------
    # 1. Parse inputs
    # -------------------------
    resume_data = parse_resume(resume_path)
    jd_data = analyze_job_description(jd_text)

    # ✅ CRITICAL: normalize skills for BM25
    resume_skills = extract_resume_skills(resume_data)
    jd_skills = extract_jd_skills(jd_data)

    # -------------------------
    # 2. Skill mapping (logic layer)
    # -------------------------
    skill_mapping = map_skills(resume_data, jd_data)

    # -------------------------
    # 3. GitHub evidence (optional)
    # -------------------------
    github_evidence = {}
    if include_github and github_username:
        github_evidence = fetch_github_evidence(github_username)

    # -------------------------
    # 4. Evidence validation
    # -------------------------
    validation = validate_skill_evidence(
        jd_data,
        skill_mapping,
        github_evidence
    )

    # -------------------------
    # 5. Prepare agent inputs
    # -------------------------

    # Skill evidence for SkillAuditAgent
    skill_evidence = {
        skill: {"status": data["status"]}
        for skill, data in validation.items()
    }

    # Missing skills (DICT required by agents)
    missing_skills = {
        skill: data["reason"]
        for skill, data in validation.items()
        if data["status"] == "unsupported"
    }


    # -------------------------
    # 6. ATS scoring (BM25 ✅)
    # -------------------------
    ats_data = compute_ats_score(
        jd_skills=jd_skills,
        resume_skills=resume_skills,
        missing_skills=missing_skills
    )

    ai_input = {
        "skill_evidence": skill_evidence,
        "missing_skills": missing_skills,
        "ats_data": ats_data
    }

    # -------------------------
    # 7. Run AI agents
    # -------------------------
    ai_analysis = run_agents(ai_input)

    # -------------------------
    # 8. Final API response
    # -------------------------
    return {
        "skill_mapping": skill_mapping,
        "evidence_validation": validation,
        "ats_data": ats_data,      
        "ai_analysis": ai_analysis
    }
