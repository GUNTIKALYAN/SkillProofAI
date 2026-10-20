import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import redis
from mcp.types import CallToolResult, TextContent
from sqlalchemy import select

from app.agents.skills_loader import (
    SkillError,
    load_skills,
    require_listed_tools,
    skill_hash,
)
from app.db import AgentRun, AgentStep, Analysis, User, session_scope
from app.mcp_client import (
    KNOWN_TOOLS,
    McpError,
    RedisLimiter,
    RunContext,
    ToolFailure,
    _payload,
    call_tool,
    reset_run,
    set_run,
)


class Scripted:
    def __init__(self, results: list) -> None:
        self._results = list(results)
        self.calls = 0

    def call(self, tool: str, args: dict) -> dict:
        del tool, args
        self.calls += 1
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expiry: dict[str, int] = {}
        self._pipe: list[tuple] = []

    def pipeline(self) -> "FakeRedis":
        self._pipe = []
        return self

    def incr(self, key: str) -> "FakeRedis":
        self._pipe.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int, nx: bool = False) -> "FakeRedis":
        self._pipe.append(("expire", key, seconds, nx))
        return self

    def execute(self) -> list[object]:
        count = 0
        for op in self._pipe:
            if op[0] == "incr":
                self.counts[op[1]] = self.counts.get(op[1], 0) + 1
                count = self.counts[op[1]]
            elif op[0] == "expire" and (not op[3] or op[1] not in self.expiry):
                self.expiry[op[1]] = op[2]
        self._pipe = []
        return [count, True]

    def ttl(self, key: str) -> int:
        return self.expiry.get(key, 1)


class DownRedis:
    def pipeline(self) -> "DownRedis":
        raise redis.RedisError("down")


@contextmanager
def _open_run(transport: Scripted, budget: int = 40, limiter: RedisLimiter | None = None):
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
            allow={name: set(skill.tools) for name, skill in skills.items()},
            limits={name: skill.limits["max_tool_calls"] for name, skill in skills.items()},
            budget=budget,
            transport=transport,
            lock=threading.Lock(),
            node_calls={},
            limiter=limiter or RedisLimiter(),
        )
        token = set_run(ctx)
        try:
            yield ctx
        finally:
            reset_run(token)


@pytest.fixture(autouse=True)
def _quiet_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.mcp_client._sleep", lambda _seconds: None)


def test_retries_stop_after_three_attempts() -> None:
    transport = Scripted(
        [
            ToolFailure(500),
            ToolFailure(429, retry_after=0),
            ["not", "json"],
            {"ok": True},
        ]
    )
    with _open_run(transport), pytest.raises(McpError):
        call_tool("score_match", {"jd_skills": []}, "match_score")
    assert transport.calls == 3
    assert transport._results == [{"ok": True}]
    with session_scope() as check:
        steps = list(check.scalars(select(AgentStep).where(AgentStep.tool == "score_match")))
    assert len(steps) == 3
    assert steps[-1].error == "status 422"


def test_retries_then_succeeds() -> None:
    transport = Scripted([ToolFailure(500), ["bad"], {"ok": True}])
    with _open_run(transport):
        result = call_tool("score_match", {}, "match_score")
    assert result == {"ok": True}
    assert transport.calls == 3


def test_auth_and_bad_request_are_not_retried() -> None:
    for status in (401, 400, 403, 404):
        transport = Scripted([ToolFailure(status), {"ok": True}])
        with _open_run(transport), pytest.raises(McpError):
            call_tool("score_match", {}, "match_score")
        assert transport.calls == 1


def test_allowlist_blocks_a_tool_outside_the_skill() -> None:
    transport = Scripted([{"ok": True}])
    with _open_run(transport), pytest.raises(McpError, match="not allowed"):
        call_tool("list_public_repos", {"username": "octocat"}, "match_score")
    assert transport.calls == 0


def test_run_budget_is_enforced() -> None:
    transport = Scripted([{"ok": True}, {"ok": True}])
    with _open_run(transport, budget=1):
        call_tool("score_match", {}, "match_score")
        with pytest.raises(McpError, match="budget"):
            call_tool("canonicalize_skill", {"text": "Python"}, "match_score")
    assert transport.calls == 1


def test_external_tool_rate_limit_is_refused() -> None:
    store = FakeRedis()
    transport = Scripted([{"repositories": []}, {"repositories": []}])
    limiter = RedisLimiter(client=store, limit=1)
    with _open_run(transport, limiter=limiter):
        call_tool("list_public_repos", {"username": "octocat"}, "github_fetch")
        with pytest.raises(McpError, match="rate limit"):
            call_tool("list_public_repos", {"username": "octocat"}, "github_fetch")
    assert transport.calls == 1
    assert store.counts["rl:mcp:list_public_repos"] == 2


def test_redis_down_fails_closed_for_external_tools() -> None:
    transport = Scripted([{"repositories": []}])
    with _open_run(transport, limiter=RedisLimiter(client=DownRedis())), pytest.raises(McpError, match="unavailable"):
        call_tool("list_public_repos", {"username": "octocat"}, "github_fetch")
    assert transport.calls == 0


def test_skill_file_lists_real_tools() -> None:
    skills = load_skills()
    assert {
        "supervisor",
        "match_score",
        "skill_audit",
        "experience_check",
        "action_planner",
        "github_fetch",
        "chatbot",
        "compare",
    } <= set(skills)
    assert "list_public_repos" not in skills["match_score"].tools
    require_listed_tools(skills, set(KNOWN_TOOLS))
    assert len(skill_hash(skills)) == 64
    with pytest.raises(SkillError):
        require_listed_tools(skills, set())


def test_tool_text_json_is_used_when_structured_content_is_missing() -> None:
    result = CallToolResult(
        content=[TextContent(type="text", text='{"repositories": [{"name": "demo"}]}')],
        isError=False,
    )
    assert _payload(result) == {"repositories": [{"name": "demo"}]}


def test_missing_section_or_tool_stops_loading(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("skills live in sections\n", encoding="utf-8")
    with pytest.raises(SkillError, match="No skill sections"):
        load_skills(empty)
    broken = tmp_path / "broken.md"
    broken.write_text(
        "## demo\n"
        "description: a skill\n"
        "tools: not_a_real_tool\n"
        "limits: max_tool_calls=1, timeout_s=1\n"
        "rules:\n"
        "- stay inside the file\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillError, match="unknown tool"):
        require_listed_tools(load_skills(broken), set(KNOWN_TOOLS))
