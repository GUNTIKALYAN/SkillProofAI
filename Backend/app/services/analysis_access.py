import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Analysis


def get_owned_analysis(
    session: Session,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID,
) -> Analysis | None:
    return session.scalar(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == user_id,
        )
    )


def completed_analysis(
    session: Session,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID | None,
) -> Analysis | None:
    if analysis_id is not None:
        row = get_owned_analysis(session, user_id, analysis_id)
        if row is None or row.status != "completed":
            return None
        return row
    return session.scalar(
        select(Analysis)
        .where(Analysis.user_id == user_id, Analysis.status == "completed")
        .order_by(Analysis.created_at.desc())
    )


def set_plan_check(
    session: Session,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID,
    skill: str,
    step: str,
    done: bool,
) -> Analysis | None:
    row = get_owned_analysis(session, user_id, analysis_id)
    if row is None:
        return None
    result = dict(row.result_json or {})
    checks = [
        item
        for item in result.get("checked_steps") or []
        if not isinstance(item, dict) or item.get("skill") != skill or item.get("step") != step
    ]
    if done:
        checks.append({"skill": skill, "step": step})
    result["checked_steps"] = checks
    row.result_json = result
    session.commit()
    return row


def list_owned_analyses(session: Session, user_id: uuid.UUID) -> list[Analysis]:
    rows = session.scalars(
        select(Analysis).where(Analysis.user_id == user_id).order_by(Analysis.created_at.desc())
    )
    return list(rows)


def save_company_url(
    session: Session,
    user_id: uuid.UUID,
    analysis_id: uuid.UUID,
    name: str,
    url: str,
) -> Analysis | None:
    row = get_owned_analysis(session, user_id, analysis_id)
    if row is None:
        return None
    result = dict(row.result_json or {})
    key = name.strip().lower()
    urls = [
        item
        for item in result.get("company_urls") or []
        if str(item.get("name") or "").strip().lower() != key
    ]
    urls.append({"name": name.strip(), "url": url})
    result["company_urls"] = urls
    row.result_json = result
    session.commit()
    return row
