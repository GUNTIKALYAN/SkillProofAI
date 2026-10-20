from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import User, get_db
from app.schemas.chat import CompareRequest, CompareResponse
from app.security import get_current_user
from app.services.analysis_access import NotFound
from app.services.chat import NoAnalysis
from app.services.compare import CompareFailed, compare_jobs

router = APIRouter(prefix="/compare", tags=["compare"])


@router.post("", response_model=CompareResponse)
def compare(
    body: CompareRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> CompareResponse:
    try:
        return compare_jobs(session, user, body.job_descriptions, body.analysis_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="Analysis not found") from exc
    except NoAnalysis as exc:
        raise HTTPException(status_code=400, detail="Run an analysis before comparing jobs") from exc
    except CompareFailed as exc:
        raise HTTPException(status_code=502, detail="Job comparison failed") from exc
