import json

import pytest

from app.llm.complete import LlmError, LlmStatus, complete_json
from app.mcp_client.context import reset_llm, set_llm
from app.schemas.agents import ActionPlan
from app.services.skill_extract import SkillExtraction


def test_invalid_json_is_retried(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.complete._sleep", lambda _seconds: None)
    calls = {"n": 0}

    def caller(system: str, user: str) -> tuple[dict, int]:
        del system, user
        calls["n"] += 1
        if calls["n"] == 1:
            raise json.JSONDecodeError("bad", "", 0)
        return {"resume_skills": ["Python"], "jd_skills": [{"name": "Python", "priority": "required"}]}, 3

    token = set_llm(caller)
    try:
        model, tokens = complete_json("match_score", {"resume": "Python"}, SkillExtraction)
    finally:
        reset_llm(token)
    assert calls["n"] == 2
    assert tokens == 3
    assert isinstance(model, SkillExtraction)


def test_rejected_request_is_not_retried(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.complete._sleep", lambda _seconds: None)
    calls = {"n": 0}

    def caller(system: str, user: str) -> tuple[dict, int]:
        del system, user
        calls["n"] += 1
        raise LlmStatus(401)

    token = set_llm(caller)
    try:
        with pytest.raises(LlmError):
            complete_json("match_score", {"resume": "Python"}, SkillExtraction)
    finally:
        reset_llm(token)
    assert calls["n"] == 1


def test_plan_gap_error_is_sent_back(monkeypatch) -> None:
    monkeypatch.setattr("app.llm.complete._sleep", lambda _seconds: None)
    seen: list[str] = []

    def caller(system: str, user: str) -> tuple[dict, int]:
        del system
        seen.append(user)
        if len(seen) == 1:
            return {"items": [{"skill": "Nope", "steps": ["Try it"], "resources": []}]}, 1
        return {"items": [{"skill": "Docker", "steps": ["Try it"], "resources": []}]}, 2

    def check(plan) -> None:
        for item in ActionPlan.model_validate(plan.model_dump()).items:
            if item.skill != "Docker":
                raise ValueError(f"{item.skill} is not a gap")

    token = set_llm(caller)
    try:
        model, _tokens = complete_json("action_planner", {"gaps": ["Docker"]}, ActionPlan, check=check)
    finally:
        reset_llm(token)
    assert "Validation error" in seen[1]
    assert isinstance(model, ActionPlan)
