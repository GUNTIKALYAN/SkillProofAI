import asyncio
import logging
import secrets

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from pydantic import AliasChoices, AnyHttpUrl, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from company import check_company as lookup_company
from github import list_public_repos as fetch_repos
from search import tavily_search as search_web
from seed_data import seed
from skillgraph import (
    AuditResult,
    CanonicalSkill,
    ExplainSkill,
    JdSkill,
    Neo4jStore,
    RelatedSkills,
    ScoreMatch,
    SkillStore,
    WhatIfLearn,
)
from skillgraph import audit_skills as audit_graph
from skillgraph import canonicalize as canonicalize_graph
from skillgraph import explain_skill as explain_graph
from skillgraph import related_skills as related_graph
from skillgraph import score_match as score_graph
from skillgraph import what_if_learn as what_if_graph

logger = logging.getLogger(__name__)

_SCOPE = "mcp:read"
_ISSUER = AnyHttpUrl("http://mcp")
GRAPH_TIMEOUT = 10.0
GITHUB_TIMEOUT = 20.0
SEARCH_TIMEOUT = 15.0
COMPANY_TIMEOUT = 15.0


class McpSettings(BaseSettings):
    neo4j_uri: str
    neo4j_user: str = Field(validation_alias=AliasChoices("NEO4J_USERNAME", "NEO4J_USER"))
    neo4j_password: str
    neo4j_database: str = ""
    mcp_token: str
    mcp_public_url: str = "http://mcp:8000/mcp"
    github_token: str = ""
    tavily_api_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class StaticTokenVerifier(TokenVerifier):
    def __init__(self, expected: str, resource: str) -> None:
        self._expected = expected
        self._resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        if len(token) != len(self._expected) or not secrets.compare_digest(token, self._expected):
            return None
        return AccessToken(token=token, client_id="skillproof", scopes=[_SCOPE], resource=self._resource)


def build_server(store: SkillStore, settings: McpSettings) -> FastMCP:
    if len(settings.mcp_token) < 16:
        raise ValueError("MCP_TOKEN must be at least 16 characters")
    mcp = FastMCP(
        "SkillProof",
        token_verifier=StaticTokenVerifier(settings.mcp_token, settings.mcp_public_url),
        auth=AuthSettings(
            issuer_url=_ISSUER,
            resource_server_url=AnyHttpUrl(settings.mcp_public_url),
            validate_token_resource=True,
            required_scopes=[_SCOPE],
        ),
        host=settings.host,
        port=settings.port,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    _register(mcp, store, settings)
    return mcp


def _register(mcp: FastMCP, store: SkillStore, settings: McpSettings) -> None:
    @mcp.tool()
    async def canonicalize_skill(text: str) -> CanonicalSkill:
        """Resolve a skill name to its canonical skill and ancestors."""
        return await _limit(canonicalize_graph, GRAPH_TIMEOUT, store, text)

    @mcp.tool()
    async def score_match(jd_skills: list[JdSkill], candidate_skills: list[str]) -> ScoreMatch:
        """Score candidate skills against a job description. The result is deterministic."""
        pairs = _pairs(jd_skills)
        return await _limit(score_graph, GRAPH_TIMEOUT, store, pairs, candidate_skills)

    @mcp.tool()
    async def audit_skills(jd_skills: list[JdSkill], candidate_skills: list[str]) -> AuditResult:
        """Classify each job skill as matched, partial or missing, with the reason."""
        pairs = _pairs(jd_skills)
        return await _limit(audit_graph, GRAPH_TIMEOUT, store, pairs, candidate_skills)

    @mcp.tool()
    async def related_skills(skill: str) -> RelatedSkills:
        """List skills directly connected to this skill."""
        return await _limit(related_graph, GRAPH_TIMEOUT, store, skill)

    @mcp.tool()
    async def explain_skill(skill: str) -> ExplainSkill:
        """Explain one skill: aliases, ancestors and direct relationships."""
        return await _limit(explain_graph, GRAPH_TIMEOUT, store, skill)

    @mcp.tool()
    async def what_if_learn(skill: str, candidate_skills: list[str], jd_skills: list[JdSkill]) -> WhatIfLearn:
        """Recompute the JD Match Score as if the candidate learned this skill."""
        pairs = _pairs(jd_skills)
        return await _limit(what_if_graph, GRAPH_TIMEOUT, store, skill, candidate_skills, pairs)

    @mcp.tool()
    async def list_public_repos(username: str) -> dict:
        """List public repositories for one GitHub username. Read only."""
        return await _limit(fetch_repos, GITHUB_TIMEOUT, username, settings.github_token)

    @mcp.tool()
    async def tavily_search(query: str) -> dict:
        """Search for learning resources. The query is a skill name, not a resume."""
        return await _limit(search_web, SEARCH_TIMEOUT, query, settings.tavily_api_key)

    @mcp.tool()
    async def check_company(name: str) -> dict:
        """Look up a company name. Returns found, not_found, ambiguous, or skipped."""
        return await _limit(lookup_company, COMPANY_TIMEOUT, name, settings.tavily_api_key)


async def _limit(fn, timeout: float, *args):
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout)
    except TimeoutError as exc:
        logger.error("tool timed out")
        raise RuntimeError("tool timed out") from exc


def _pairs(jd_skills: list[JdSkill]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in jd_skills:
        skill = item if isinstance(item, JdSkill) else JdSkill.model_validate(item)
        pairs.append((skill.name, skill.priority))
    return pairs


def load_settings() -> McpSettings:
    try:
        return McpSettings()
    except ValidationError as exc:
        names = ", ".join(str(err["loc"][0]).upper() for err in exc.errors() if err["loc"])
        listed = names or "invalid values"
        raise RuntimeError(f"Startup failed. Missing or invalid settings: {listed}.") from exc


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = load_settings()
    if len(settings.mcp_token) < 16:
        raise RuntimeError("Startup failed. MCP_TOKEN must be at least 16 characters.")
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        driver.verify_connectivity()
        database = settings.neo4j_database or None
        with driver.session(database=database) as session:
            count = seed(session)
        logger.info("skill graph seeded skills=%s", count)
        build_server(Neo4jStore(driver, settings.neo4j_database), settings).run(transport="streamable-http")
    except Neo4jError as exc:
        logger.error("neo4j startup failed error=%s", type(exc).__name__)
        raise RuntimeError("Startup failed. Neo4j is not reachable.") from exc
    finally:
        driver.close()


if __name__ == "__main__":
    main()
