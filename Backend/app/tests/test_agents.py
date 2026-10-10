from datetime import date

from app.agents.routing import choose_next
from app.schemas.agents import JobEntry
from app.services.experience_checks import check_entries


def _job(company: str, title: str, start: str, end: str | None) -> JobEntry:
    return JobEntry(company=company, title=title, start=start, end=end, bullets=[])


def test_skip_github_and_experience_when_they_are_missing() -> None:
    state = {"step_count": 0, "github_username": None, "has_experience": False, "match": None}
    assert choose_next(state) == ["match_score"]


def test_independent_steps_are_selected_together() -> None:
    state = {"step_count": 0, "github_username": "octocat", "has_experience": True, "match": None}
    assert choose_next(state) == ["github_fetch", "match_score", "experience_check"]


def test_low_confidence_retries_once() -> None:
    state = {
        "step_count": 2,
        "github_username": None,
        "has_experience": False,
        "github_evidence": None,
        "match": {"low_confidence": True},
        "match_retries": 0,
    }
    assert choose_next(state) == ["match_score"]
    state["match_retries"] = 1
    assert choose_next(state) == ["skill_audit"]


def test_planner_runs_only_when_there_is_a_gap() -> None:
    ready = {
        "step_count": 3,
        "github_username": None,
        "has_experience": False,
        "match": {"low_confidence": False},
        "match_retries": 0,
        "audit": {"items": [{"skill": "Python", "status": "matched"}]},
    }
    assert choose_next(ready) == ["finalize"]
    ready["audit"] = {"items": [{"skill": "Docker", "status": "missing"}]}
    assert choose_next(ready) == ["action_planner"]


def test_step_limit_finishes() -> None:
    assert choose_next({"step_count": 8, "match": None}) == ["finalize"]


def test_end_before_start_is_a_date_flag() -> None:
    flags = check_entries([_job("Acme", "Engineer", "2024-05", "2024-01")], today=date(2026, 1, 1))
    assert any("ends before" in flag["detail"] for flag in flags)


def test_overlap_and_gap() -> None:
    entries = [
        _job("Acme", "Engineer", "2020-01", "2021-06"),
        _job("Other", "Engineer", "2021-01", "2021-08"),
        _job("Next", "Engineer", "2023-01", "2023-06"),
    ]
    flags = check_entries(entries, today=date(2026, 1, 1))
    details = " ".join(flag["detail"] for flag in flags)
    assert "overlaps" in details
    assert "gap longer than 6 months" in details


def test_senior_title_with_a_short_span() -> None:
    flags = check_entries(
        [_job("Acme", "Senior Engineer", "2024-01", "2024-06")],
        today=date(2026, 1, 1),
    )
    assert any("senior title" in flag["detail"] for flag in flags)


def test_company_status_is_not_a_date_flag() -> None:
    flags = check_entries([_job("Acme", "Engineer", "2020-01", "2022-01")], today=date(2026, 1, 1))
    assert flags == []
