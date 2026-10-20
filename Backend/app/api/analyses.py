import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.uploads import resume_file
from app.core.resume_parse import parse_resume
from app.db import Analysis, User, get_db
from app.schemas.auth import (
    AnalysisPublic,
    AnalysisSummary,
    CompanyUrlRequest,
    JobAccepted,
)
from app.schemas.chat import PlanCheck
from app.schemas.input_schema import AnalyzeRequest
from app.security import get_current_user
from app.services.analysis_access import (
    get_owned_analysis,
    list_owned_analyses,
    save_company_url,
    set_plan_check,
)
from app.services.analysis_service import accept_analysis
from app.services.runner import execute_analysis
from app.services.skill_extract import ExtractionError, extract_skills

router = APIRouter()


@router.get("/")
def home_page() -> dict[str, str]:
    return {"message": "Welcome to home page of SkillProof AI"}


@router.post("/parse-resume")
def parse_resume_route(
    resume: UploadFile = File(...),
    _user: User = Depends(get_current_user),
) -> dict:
    with resume_file(resume) as resume_path:
        return _parse_resume(resume_path)


@router.post("/analyze-jd")
def analyze_jd_route(
    jd_text: str = Form(...),
    _user: User = Depends(get_current_user),
) -> dict:
    if not jd_text.strip():
        raise HTTPException(status_code=400, detail="JD text is required")
    try:
        extraction = extract_skills("", jd_text)
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail="Skill extraction failed") from exc
    return {"jd_skills": [item.model_dump() for item in extraction.jd_skills]}


@router.post("/map-skills", response_model=JobAccepted, status_code=202)
def map_skills_route(
    background: BackgroundTasks,
    resume: UploadFile = File(...),
    jd_text: str = Form(...),
    github_username: str = Form(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobAccepted:
    if not jd_text.strip():
        raise HTTPException(status_code=400, detail="JD text is required")
    request = _analyze_request(jd_text, github_username)
    with resume_file(resume) as resume_path:
        return _enqueue(resume_path, request, user, session, background)


@router.post("/analyses", response_model=JobAccepted, status_code=202)
@router.post("/analyze", response_model=JobAccepted, status_code=202)
def analyze(
    background: BackgroundTasks,
    jd_text: str = Form(...),
    github_username: str = Form(...),
    resume: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobAccepted:
    request = _analyze_request(jd_text, github_username)
    with resume_file(resume) as resume_path:
        return _enqueue(resume_path, request, user, session, background)


@router.get("/analyses", response_model=list[AnalysisSummary])
def list_analyses(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[Analysis]:
    return list_owned_analyses(session, user.id)


@router.patch("/analyses/{analysis_id}/company-url", response_model=AnalysisPublic)
def add_company_url(
    analysis_id: uuid.UUID,
    body: CompanyUrlRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AnalysisPublic:
    row = save_company_url(session, user.id, analysis_id, body.name, body.url)
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _public(row)


@router.patch("/analyses/{analysis_id}/plan", response_model=AnalysisPublic)
def check_plan_item(
    analysis_id: uuid.UUID,
    body: PlanCheck,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AnalysisPublic:
    row = set_plan_check(session, user.id, analysis_id, body.skill, body.step, body.done)
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _public(row)


@router.get("/analyses/{analysis_id}", response_model=AnalysisPublic)
def read_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AnalysisPublic:
    row = get_owned_analysis(session, user.id, analysis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _public(row)


def _public(row: Analysis) -> AnalysisPublic:
    return AnalysisPublic(
        id=row.id,
        status=row.status,
        score=row.score,
        github_username=row.github_username,
        created_at=row.created_at,
        result=row.result_json,
    )


def _parse_resume(resume_path: str) -> dict:
    try:
        return parse_resume(resume_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _enqueue(
    resume_path: str,
    request: AnalyzeRequest,
    user: User,
    session: Session,
    background: BackgroundTasks,
) -> JobAccepted:
    try:
        resume = parse_resume(resume_path)
        job_id = accept_analysis(session, user.id, request, resume)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background.add_task(execute_analysis, str(job_id))
    return JobAccepted(job_id=job_id, status="queued")


def _analyze_request(jd_text: str, github_username: str) -> AnalyzeRequest:
    try:
        return AnalyzeRequest(
            jd_text=jd_text,
            github_username=github_username,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_message(exc)) from exc


def _validation_message(exc: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(item) for item in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    ]
    return "; ".join(parts) or "Invalid analysis request"
