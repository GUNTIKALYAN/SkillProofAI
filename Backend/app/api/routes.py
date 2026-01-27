from app.core.resume_parse import parse_resume
from app.core.jd_analyzer import analyze_job_description
from app.core.skill_mapper import map_skills
from app.core.github_fetcher import fetch_github_evidence
from app.core.evidence_validator import validate_skill_evidence
from app.schemas.input_schema import AnalyzeRequest
from app.services.analysis_service import run_full_analysis
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
import tempfile
import os

router = APIRouter()


# -------------------------
# Health / Home
# -------------------------
@router.get("/")
def home_page():
    return {"message": "Welcome to home page of SkillProof AI"}


# -------------------------
# Resume Parsing
# -------------------------
@router.post("/parse-resume")
def parse_resume_route(resume: UploadFile = File(...)):
    suffix = os.path.splitext(resume.filename)[1]  # 👈 preserve extension

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(resume.file.read())
            tmp_path = tmp.name

        return parse_resume(tmp_path)

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# -------------------------
# JD Analysis
# -------------------------
@router.post("/analyze-jd")
def analyze_jd_route(jd_text: str = Form(...)):
    return analyze_job_description(jd_text)


# -------------------------
# Skill Mapping
# -------------------------
@router.post("/map-skills")
def map_skills_route(
    resume: UploadFile = File(...),
    jd_text: str = Form(...)
):
    suffix = os.path.splitext(resume.filename)[1]

    if not jd_text.strip():
        raise HTTPException(status_code=400, detail="JD text is required")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(resume.file.read())
            tmp_path = tmp.name

        resume_data = parse_resume(tmp_path)
        jd_data = analyze_job_description(jd_text)

        return map_skills(resume_data, jd_data)

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# -------------------------
# Full Pipeline
# -------------------------
@router.post("/analyze_nollm")
def analyze_full_nollm(jd_text: str = Form(...),github_username: str | None = Form(None),include_github: bool = Form(True),resume: UploadFile = File(...)):
    request = AnalyzeRequest(
        jd_text=jd_text,
        github_username=github_username,
        include_github=include_github
    )

    suffix = os.path.splitext(resume.filename)[1]

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(resume.file.read())
            tmp_path = tmp.name

        resume_data = parse_resume(tmp_path)
        jd_data = analyze_job_description(request.jd_text)
        skill_mapping = map_skills(resume_data, jd_data)

        github_evidence = {}
        if request.include_github and request.github_username:
            github_evidence = fetch_github_evidence(request.github_username)

        validation = validate_skill_evidence(
            jd_data,
            skill_mapping,
            github_evidence
        )

        return {
            "resume": resume_data,
            "job_description": jd_data,
            "skill_mapping": skill_mapping,
            "github_evidence": github_evidence,
            "evidence_validation": validation
        }

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@router.post("/analyze")
def analyze_full_with_ai(
    jd_text: str = Form(...),
    github_username: str | None = Form(None),
    include_github: bool = Form(True),
    resume: UploadFile = File(...)
):
    request = AnalyzeRequest(
        jd_text=jd_text,
        github_username=github_username,
        include_github=include_github
    )

    suffix = os.path.splitext(resume.filename)[1]

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(resume.file.read())
            tmp_path = tmp.name

        return run_full_analysis(
            resume_path=tmp_path,
            jd_text=request.jd_text,
            github_username=request.github_username,
            include_github=request.include_github
        )

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
