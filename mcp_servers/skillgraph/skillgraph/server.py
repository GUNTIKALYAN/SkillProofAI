import logging
import os
import secrets
from pathlib import Path

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from pydantic import AnyHttpUrl, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse

from skillgraph.schemas import (
    AuditResult,
    CanonicalSkill,
    ExplainSkill,
    JdSkill,
    RelatedSkills,
    ScoreMatch,
    WhatIfLearn,
)
from skillgraph.scoring import SkillStore
from skillgraph.scoring import audit_skills as audit_graph
from skillgraph.scoring import canonicalize as canonicalize_graph
from skillgraph.scoring import explain_skill as explain_graph
from skillgraph.scoring import related_skills as related_graph
from skillgraph.scoring import score_match as score_graph
from skillgraph.scoring import what_if_learn as what_if_graph
from skillgraph.seed import seed
from skillgraph.store import Neo4jStore

logger = logging.getLogger(__name__)

_SCOPE = "skillgraph:read"
_ISSUER = AnyHttpUrl("http://skillgraph")


class SkillGraphSettings(BaseSettings):
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    skillgraph_token: str
    skillgraph_public_url: str = "http://skillgraph:8000/mcp"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(extra="ignore")


class StaticTokenVerifier(TokenVerifier):
    def __init__(self, expected: str, resource: str) -> None:
        self._expected = expected
        self._resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        if len(token) != len(self._expected) or not secrets.compare_digest(token, self._expected):
            return None
        return AccessToken(
            token=token,
            client_id="skillproof",
            scopes=[_SCOPE],
            resource=self._resource,
        )


def build_server(store: SkillStore, token: str, public_url: str, host: str, port: int) -> FastMCP:
    if len(token) < 16:
        raise ValueError("SKILLGRAPH_TOKEN must be at least 16 characters")
    mcp = FastMCP(
        "Skill Graph",
        token_verifier=StaticTokenVerifier(token, public_url),
        auth=AuthSettings(
            issuer_url=_ISSUER,
            resource_server_url=AnyHttpUrl(public_url),
            validate_token_resource=True,
            required_scopes=[_SCOPE],
        ),
        host=host,
        port=port,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    _register(mcp, store, token)
    return mcp


def _register(mcp: FastMCP, store: SkillStore, token: str) -> None:
    @mcp.tool()
    def canonicalize_skill(text: str) -> CanonicalSkill:
        """Resolve a skill name to its canonical skill and ancestors."""
        return canonicalize_graph(store, text)

    @mcp.tool()
    def score_match(jd_skills: list[JdSkill], candidate_skills: list[str]) -> ScoreMatch:
        """Score candidate skills against a job description. The result is deterministic."""
        return score_graph(store, _pairs(jd_skills), candidate_skills)

    @mcp.tool()
    def audit_skills(jd_skills: list[JdSkill], candidate_skills: list[str]) -> AuditResult:
        """Classify each job skill as matched, partial or missing, with the reason."""
        return audit_graph(store, _pairs(jd_skills), candidate_skills)

    @mcp.tool()
    def related_skills(skill: str) -> RelatedSkills:
        """List skills directly connected to this skill."""
        return related_graph(store, skill)

    @mcp.tool()
    def explain_skill(skill: str) -> ExplainSkill:
        """Explain one skill: aliases, ancestors and direct relationships."""
        return explain_graph(store, skill)

    @mcp.tool()
    def what_if_learn(
        skill: str,
        candidate_skills: list[str],
        jd_skills: list[JdSkill],
    ) -> WhatIfLearn:
        """Recompute the JD Match Score as if the candidate learned this skill."""
        return what_if_graph(store, skill, candidate_skills, _pairs(jd_skills))

    @mcp.custom_route("/admin/skill", methods=["POST"], include_in_schema=False)
    async def admin_skill(request: Request) -> JSONResponse:
        if not _bearer_ok(request, token):
            return JSONResponse({"detail": "Not allowed"}, status_code=401)
        body = await _json_body(request)
        name = str(body.get("name") or "")
        if not store.add_skill(name):
            return JSONResponse({"detail": "Skill name is empty"}, status_code=400)
        return JSONResponse({"status": "approved"})

    @mcp.custom_route("/admin/alias", methods=["POST"], include_in_schema=False)
    async def admin_alias(request: Request) -> JSONResponse:
        if not _bearer_ok(request, token):
            return JSONResponse({"detail": "Not allowed"}, status_code=401)
        body = await _json_body(request)
        if not store.add_alias(str(body.get("name") or ""), str(body.get("canonical") or "")):
            return JSONResponse({"detail": "That skill is not in the graph"}, status_code=404)
        return JSONResponse({"status": "aliased"})

    @mcp.custom_route("/readyz", methods=["GET"], include_in_schema=False)
    async def readyz(_request: Request) -> JSONResponse:
        try:
            store.ping()
        except Neo4jError as exc:
            logger.error("neo4j check failed error=%s", type(exc).__name__)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})


def _bearer_ok(request: Request, token: str) -> bool:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return False
    return len(value) == len(token) and secrets.compare_digest(value, token)


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        return {}
    if not isinstance(body, dict):
        return {}
    return body


def _pairs(jd_skills: list[JdSkill]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in jd_skills:
        skill = item if isinstance(item, JdSkill) else JdSkill.model_validate(item)
        pairs.append((skill.name, skill.priority))
    return pairs


def load_settings() -> SkillGraphSettings:
    try:
        return SkillGraphSettings()
    except ValidationError as exc:
        names = ", ".join(str(err["loc"][0]).upper() for err in exc.errors() if err["loc"])
        listed = names or "invalid values"
        raise RuntimeError(
            f"Startup failed. Missing or invalid settings: {listed}."
        ) from exc


def _configure_logging(filename: str) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dir = os.environ.get("LOG_DIR", "").strip()
    if log_dir:
        path = Path(log_dir) / filename
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(path, encoding="utf-8"))
        except OSError:
            pass
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers, force=True)


def main() -> None:
    _configure_logging("skillgraph.log")
    settings = load_settings()
    if len(settings.skillgraph_token) < 16:
        raise RuntimeError("Startup failed. SKILLGRAPH_TOKEN must be at least 16 characters.")
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            count = seed(session)
        logger.info("skill graph seeded skills=%s", count)
        server = build_server(
            Neo4jStore(driver),
            settings.skillgraph_token,
            settings.skillgraph_public_url,
            settings.host,
            settings.port,
        )
        server.run(transport="streamable-http")
    except Neo4jError as exc:
        logger.error("neo4j startup failed error=%s", type(exc).__name__)
        raise RuntimeError("Startup failed. Neo4j is not reachable.") from exc
    finally:
        driver.close()


if __name__ == "__main__":
    main()
