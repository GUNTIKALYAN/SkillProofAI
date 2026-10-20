# SkillProofAI

SkillProofAI shows a student or early-career candidate how a resume and a public GitHub profile match one job description. The result is a **JD Match Score**, a skill audit (matched, partial, or missing), and a learning plan. GitHub is a **signal, not proof**. The product never labels a person "fake".

It is not a chat window with a resume pasted in:

- Public GitHub repos are checked against the claims. Private work stays invisible, and a repo may be a copy.
- The score comes from the skill graph, so the same input gives the same number, with a reason per skill.
- Past runs stay in history. One profile can be compared across job descriptions.
- "What if I learn X?" recomputes the score through the graph.

## Architecture

```
Browser (HTML + CSS + JS)
        |
gateway  (FastAPI, the only published port)
  - request id, one JSON log line per request
  - route policy: public / user / admin  (checks the JWT)
  - Redis rate limits, 5 MB body limit
  - serves the HTML/CSS/JS files, proxies /api/* to the backend
        |
backend  (FastAPI, internal only)
  - verifies the JWT again, loads the user from PostgreSQL (blocked? role?)
  - ownership checks, analyses, chat, admin
  - background task -> LangGraph supervisor
        |
  mcp_client.py   (token, allowlist, budget, rate limit, 3 attempts)
        |
mcp  (one MCP server, 9 tools, one bearer token, internal only)
  - skillgraph tools (6)  -> Neo4j
  - list_public_repos     -> GitHub API
  - tavily_search         -> Tavily API
  - check_company         -> Tavily API

PostgreSQL: backend only        Redis: rate limiting only (gateway + mcp_client)
```

Six services: `gateway`, `backend`, `postgres`, `redis`, `neo4j`, `mcp`. Only the gateway publishes a port.

## Run

```bash
cp .env.example .env
```

Fill in `.env`. `GROQ_API_KEY`, `JWT_SECRET` (at least 32 characters), and `MCP_TOKEN` (at least 16 characters) need real values. The placeholders are not enough to boot the app. `COOKIE_SECURE=false` is for local HTTP. Set it to `true` only when the site is served over HTTPS.

```bash
docker compose up --build
```

Open `http://localhost:8000`. The pages and the API share that origin. Postgres, Redis, Neo4j, the MCP server, and the backend are not published.

Sign up in the UI. The first admin is not a public signup. From `Backend/`:

```bash
python create_admin.py
```

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` first.

## Environment

See `.env.example`.

| Variable | Role |
|---|---|
| `GROQ_API_KEY`, `LLAMA_MODEL` | Model used for extraction, explanations, and the plan |
| `DATABASE_URL` | Postgres URL for the backend. Compose overrides the host to `postgres` |
| `JWT_SECRET` | Shared by the gateway and the backend. Signs the 15-minute access token |
| `MCP_URL`, `MCP_TOKEN` | The one MCP server and its bearer token |
| `REDIS_URL` | Rate limits only. Compose points this at `redis` |
| `BACKEND_URL` | Gateway proxy target. Compose sets `http://backend:8000` |
| `GITHUB_TOKEN` | Optional. Raises the public GitHub API quota. Lives in the MCP container |
| `TAVILY_API_KEY` | Learning links and the company-name check. Lives in the MCP container |
| `COOKIE_SECURE` | `true` when the refresh cookie must be HTTPS-only |
| `MCP_PROBE` | `true` checks that `skills.md` tools exist on the MCP server at startup |
| `POSTGRES_*`, `NEO4J_PASSWORD` | Compose database passwords |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Used only by `create_admin.py` |

Do not commit `.env`. CI refuses a tracked `.env`.

## Known limits

- A restart drops a running analysis. The row stays `running`. There is no queue.
- One MCP token unlocks every tool. Per-agent control is the allowlist in `skills.md`.
- GitHub evidence is a signal, not proof. A missing company page does not lower the score and never means "fake".
- Auth limits are per IP. A blocked user's access token still passes the gateway until it expires. The backend rejects it.

## Tests

From `Backend/` and from `gateway/`:

```bash
pytest
ruff check .
```

Those tests use SQLite, a fake LLM, a fake MCP client, and a fake Redis. They do not need API keys.

CI runs those two commands for the backend and the gateway. It does not push images.

## Interview notes

Why the gateway, why one MCP server, why the score is deterministic, what the guard does not stop, and what was left out: [docs/interview-notes.md](docs/interview-notes.md).
