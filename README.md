# SkillProofAI

SkillProofAI compares one resume with a job description and returns a **JD Match Score**, a skill audit (matched, partial, missing), and an action plan. GitHub activity is a **signal**, not proof. The product never labels a person "fake".

A chat window can already critique a resume. This only wins where a chat window cannot:

1. **Cross-checked evidence.** Public GitHub repos (language, description, README text) are compared with resume claims. A repo can be a tutorial, and private work is invisible, so the UI says "supported by public evidence".
2. **The same input gives the same score.** The score comes from the skill graph, with a reason per skill. The model writes explanations and the plan. It does not pick the score.
3. **Progress sticks around.** Past scores, a plan you can tick off, and a re-run that shows the score change.
4. **Several jobs, one profile.** Compare up to 10 job descriptions and see the single skill that unlocks the most of them.
5. **What-if.** "What if I learn X?" recomputes the score from the graph.

## Architecture

```
Browser (HTML, CSS, JS)
        |
   Traefik  — TLS, routing, load balancing, coarse IP limit
        |
   FastAPI (two replicas, no in-memory session state)
     |-- auth, analyses, chat, compare, admin, /metrics
     |-- Postgres  — users, analyses, traces, chat
     |-- Redis     — rate limits, cache, job queue, shared metrics
     |
     +-- worker (ARQ) runs the LangGraph supervisor
           |-- Skill-Graph MCP  -> Neo4j (skill ontology only)
           |-- GitHub MCP       (list_public_repos, username required)
           |-- Tavily MCP       (learning resources)
           |-- Verify MCP       (company name only)
           +-- Groq             (extraction, explanations, plan)
```

Neo4j stores the skill ontology only. Candidate data stays in Postgres. MCP tools are read-only and never see the user's JWT.

The Skill-Graph container has no published port and sits on an internal Docker network. GitHub, Tavily, and Verify also have no published ports. They join that internal network and a second network, because they have to call the public GitHub and Tavily APIs. The worker joins both networks for the same reason: Groq is on the internet.

## Run

```bash
cp .env.example .env
```

Fill in `.env`. At least `GROQ_API_KEY`, `JWT_SECRET`, and the MCP bearer tokens need real values. Placeholders in `.env.example` are not secrets and are not enough to boot the app. `COOKIE_SECURE=false` is for local HTTP. Set it to `true` when the site is served over HTTPS only.

```bash
docker compose up --build
```

Runtime logs are written under `Backend/.logs/` while the app is running: `backend-logs`, `worker-logs`, `mcp-logs`, and `mcp/*.log` for each MCP server. Those files are not committed.

Then open `https://localhost` and accept the local certificate. The API is also on `http://localhost:8000`. A direct frontend port is `http://localhost:3000`.

Sign up in the UI. The first admin is not a public signup. From `Backend/`:

```bash
python create_admin.py
```

`Delete my data` removes the signed-in account, parsed resume text, analyses, chat, and refresh tokens. Resume files are not stored. Only parsed text is saved with the analysis.

`/metrics` is plain Prometheus text: request latency, LLM latency, and the ARQ queue depth. It has no user data.

## Environment

See `.env.example`.

| Variable | Role |
|---|---|
| `GROQ_API_KEY`, `LLAMA_MODEL` | Model used for extraction, explanations, and the plan |
| `DATABASE_URL` | Postgres URL for the API and worker |
| `JWT_SECRET` | Signs the 15-minute access token |
| `REDIS_URL` | Rate limits, cache, queue, metrics |
| `SKILLGRAPH_URL`, `SKILLGRAPH_TOKEN` | Skill-Graph MCP |
| `GITHUB_MCP_URL`, `GITHUB_MCP_TOKEN` | Our GitHub MCP server. Every analysis requires a username |
| `GITHUB_TOKEN` | Optional GitHub API token for a higher public-repo quota |
| `TAVILY_MCP_URL`, `TAVILY_MCP_TOKEN`, `TAVILY_API_KEY` | Learning-resource search |
| `VERIFY_MCP_URL`, `VERIFY_MCP_TOKEN` | Company-name check |
| `COOKIE_SECURE` | `true` in production so the refresh cookie is HTTPS-only |
| `CORS_ORIGINS` | Explicit origins. Cookies need this. No wildcard |
| `POSTGRES_*`, `NEO4J_PASSWORD` | Compose database passwords |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Used by `create_admin.py` |
| `MCP_PROBE` | `true` checks MCP tools at startup |

Do not commit `.env`. Images are built without it. CI refuses a tracked `.env`.

## Tests

From `Backend/`:

```bash
pytest
ruff check .
```

Those tests use SQLite and fake LLM and MCP clients. They do not need API keys.

CI (`.github/workflows/ci.yml`) runs ruff, the test suite, and a live check against Postgres, Redis, and Neo4j service containers. It builds the images, checks they do not run as root, and runs `pip-audit`. Images are pushed only from `main`.

To run the live service check yourself, point the `STACK_*` variables at Postgres, Redis, and Neo4j and set `SKILLPROOF_INTEGRATION=1`. In PowerShell:

```powershell
$env:SKILLPROOF_INTEGRATION = "1"
$env:STACK_DATABASE_URL = "postgresql://skillproof:skillproof@localhost:5432/skillproof"
$env:STACK_REDIS_URL = "redis://localhost:6379/0"
$env:STACK_NEO4J_URI = "bolt://localhost:7687"
$env:STACK_NEO4J_USER = "neo4j"
$env:STACK_NEO4J_PASSWORD = "skillproof-neo4j"
pytest app/tests/test_stack.py
```

## Interview notes

Why Neo4j, why MCP, why a queue, why the refresh cookie, and what was left out: [docs/interview-notes.md](docs/interview-notes.md).
