import threading
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import select

from app.agents.skills.loader import (
    SkillError,
    allowlist,
    load_skills,
    require_listed_tools,
    skill_hash,
)
from app.db.models import AgentRun, AgentStep, Analysis, User
from app.db.session import session_scope
from app.mcp_client.catalog import KNOWN_TOOLS
from app.mcp_client.client import call_tool, reset_breaker
from app.mcp_client.context import RunContext, reset_run, set_run
from app.mcp_client.errors import McpError, ToolFailure
from app.services.bucket import MemoryBucket
from app.services.cache import MemoryCache


class Scripted:
    def __init__(self, results: list) -> None:
        self._results = list(results)
        self.calls = 0

    def call(self, server: str, tool: str, args: dict) -> dict:
        del server, tool, args
        self.calls += 1
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@contextmanager
def _open_run(transport: Scripted, budget: int = 40):
    with session_scope() as session:
        user = User(email=f"{uuid.uuid4()}@example.com", password_hash="x", role="user", status="active")
        session.add(user)
        session.flush()
        analysis = Analysis(
            user_id=user.id,
            jd_text="job description",
            jd_hash="a" * 64,
            status="queued",
        )
        session.add(analysis)
        session.flush()
        skills = load_skills()
        run = AgentRun(analysis_id=analysis.id, skill_hash=skill_hash(skills), status="running")
        session.add(run)
        session.commit()
        ctx = RunContext(
            run_id=run.id,
            session=session,
            allow=allowlist(skills),
            limits={name: skill.limits["max_tool_calls"] for name, skill in skills.items()},
            budget=budget,
            transport=transport,
            bucket=MemoryBucket(),
            cache=MemoryCache(),
            lock=threading.Lock(),
            node_calls={},
        )
        token = set_run(ctx)
        try:
            yield ctx
        finally:
            reset_run(token)


@pytest.fixture(autouse=True)
def _quiet_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_breaker()
    monkeypatch.setattr("app.mcp_client.client._sleep", lambda _seconds: None)


def test_retries_then_succeeds() -> None:
    transport = Scripted(
        [
            ToolFailure(500, retry=True),
            ToolFailure(429, retry=True, retry_after=0),
            {"ok": True},
        ]
    )
    with _open_run(transport):
        result = call_tool("skillgraph", "score_match", {"jd_skills": []}, "match_score")
    assert result == {"ok": True}
    assert transport.calls == 3
    with session_scope() as check:
        steps = list(check.scalars(select(AgentStep).where(AgentStep.tool == "skillgraph.score_match")))
    assert len(steps) == 3
    assert steps[-1].error is None


def test_malformed_result_is_retried() -> None:
    transport = Scripted([ToolFailure(422, retry=True), {"ok": True}])
    with _open_run(transport):
        result = call_tool("skillgraph", "score_match", {}, "match_score")
    assert result == {"ok": True}
    assert transport.calls == 2


def test_auth_and_bad_request_are_not_retried() -> None:
    for status in (401, 400, 403, 404):
        reset_breaker()
        transport = Scripted([ToolFailure(status, retry=False)])
        with _open_run(transport), pytest.raises(McpError):
            call_tool("skillgraph", "score_match", {}, "match_score")
        assert transport.calls == 1


def test_allowlist_blocks_a_tool_outside_the_skill() -> None:
    transport = Scripted([{"ok": True}])
    with _open_run(transport), pytest.raises(McpError, match="not allowed"):
        call_tool("github", "list_public_repos", {"username": "octocat"}, "match_score")
    assert transport.calls == 0


def test_run_budget_is_enforced() -> None:
    transport = Scripted([{"ok": True}, {"ok": True}])
    with _open_run(transport, budget=1):
        call_tool("skillgraph", "score_match", {}, "match_score")
        with pytest.raises(McpError, match="budget"):
            call_tool("skillgraph", "canonicalize_skill", {"text": "Python"}, "match_score")
    assert transport.calls == 1


def test_circuit_breaker_opens_after_five_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.mcp_client.client.MAX_ATTEMPTS", 1)
    transport = Scripted([ToolFailure(500, retry=True) for _ in range(6)])
    with _open_run(transport):
        for _ in range(5):
            with pytest.raises(McpError):
                call_tool("skillgraph", "score_match", {}, "match_score")
        with pytest.raises(McpError, match="paused"):
            call_tool("skillgraph", "score_match", {}, "match_score")
    assert transport.calls == 5


def test_skill_files_list_real_tools() -> None:
    skills = load_skills()
    assert {
        "supervisor",
        "match_score",
        "skill_audit",
        "experience_check",
        "action_planner",
        "github_fetch",
    } <= set(skills)
    require_listed_tools(skills, KNOWN_TOOLS)
    assert len(skill_hash(skills)) == 64
    with pytest.raises(SkillError):
        require_listed_tools(skills, {"skillgraph": set()})
