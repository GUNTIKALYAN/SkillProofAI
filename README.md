# SkillProof AI- Multi-Agent AI System

SkillProof AI helps job applicants **verify their skills before applying**.

Instead of trusting resumes or ATS keyword matching, it validates skills against:
- Resume content  
- Job description requirements  
- Real GitHub project evidence  

The result is a **clear skill audit, identified gaps, and actionable next steps**.

---

## Why SkillProof AI?

Modern hiring systems break because:
- Candidates can list skills without proof  
- ATS systems prioritize keywords over real ability  

This leads to strong candidates being rejected and weak matches passing screening.

SkillProof AI addresses this **from the candidate’s side**, before submission.

---

## What SkillProof AI Takes In

- Resume (PDF or DOCX)  
- Job description  
- GitHub username  

---

## What SkillProof AI Does

1. Reads the resume and job description  
2. Extracts required skills for the role  
3. Analyzes GitHub repositories for real usage  
4. Verifies which skills are actually supported  
5. Uses AI **only** to explain gaps and suggest improvements  

---

## What You Get

- Supported vs unsupported skills  
- Skill gaps for the target role  
- Risk areas (over-claimed skills)  
- Clear, practical next steps  

**No black-box scoring. Every result is explainable.**

---

## Core Principle

> Validate with deterministic logic first.  
> Use AI only for reasoning and recommendations.

---

## Tech Stack & Design Choices

SkillProof AI is built with a **practical, production-oriented stack** focused on clarity, reliability, and explainability.

### Backend
- **Python** – Core language for parsing, validation, and orchestration  
- **FastAPI** – Lightweight API framework with automatic validation and docs  
- **Pydantic** – Strong input/output data contracts  

### AI & Agent Layer
- **LLaMA (via Groq)** – Used only for reasoning and recommendations  
- **LangGraph** – Structured multi-agent workflows:
  - Skill audit agent  
  - Gap analysis agent  
  - Action planning agent  

> AI agents operate only on validated data, not raw inputs.

### Validation & Evidence
- **Rule-based logic** – Deterministic skill matching and evidence checks  
- **GitHub REST API** – Fetches real project evidence (repos, languages, activity)  

### Infrastructure & DevOps
- **Docker** – Containerized setup for consistent environments  
- **GitHub Actions (CI/CD)** – Automated linting, testing, and build checks  

### Frontend
- **HTML / CSS / JavaScript** – Minimal UI focused on clarity and demo readiness  

---

## Project Structure

The project is organized to clearly separate **API handling**, **deterministic validation**, and **AI reasoning**.


```bash
skillproof-ai/
│
├── Backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entry point
│   │   ├── config.py                # Environment & app configuration
│   │   ├── __init__.py
│   │
│   │   ├── api/
│   │   │   ├── routes.py             # API routes (/analyze, health)
│   │   │   └── __init__.py
│   │
│   │   ├── core/                     # Deterministic logic (NO AI)
│   │   │   ├── resume_parse.py        # Resume text extraction
│   │   │   ├── resume_utils.py
│   │   │   ├── jd_analyzer.py         # Job description parsing
│   │   │   ├── jd_utils.py
│   │   │   ├── skill_mapper.py        # Resume ↔ JD mapping
│   │   │   ├── github_fetcher.py      # GitHub REST API integration
│   │   │   ├── evidence_validator.py  # Skill evidence validation
│   │   │   ├── ats_bm25.py            # ATS keyword logic
│   │   │   ├── ats_normalizer.py
│   │   │   ├── ats_scorer.py
│   │   │   └── __init__.py
│   │
│   │   ├── agents/                   # AI reasoning layer
│   │   │   ├── base_agent.py
│   │   │   ├── skill_audit_agent.py
│   │   │   ├── gap_analysis_agent.py
│   │   │   ├── ats_impact_agent.py
│   │   │   ├── quick_insight_agent.py
│   │   │   ├── action_plan_agent.py
│   │   │   ├── action_planner_agent.py
│   │   │   ├── agent_runner.py        # Agent orchestration
│   │   │   └── __init__.py
│   │
│   │   ├── graph/                    # LangGraph workflow
│   │   │   ├── graph_builder.py
│   │   │   ├── graph_state.py
│   │   │   ├── graph_visualize.py
│   │   │   ├── skillproofai_agent_flow.png
│   │   │   └── __init__.py
│   │
│   │   ├── nodes/                    # Individual LangGraph nodes
│   │   │   ├── skill_audit_node.py
│   │   │   ├── gap_analysis_node.py
│   │   │   ├── ats_impact_node.py
│   │   │   ├── action_plan_node.py
│   │   │   ├── action_planner_node.py
│   │   │   └── __init__.py
│   │
│   │   ├── llm/
│   │   │   ├── client.py              # LLaMA / Groq client
│   │   │   └── __init__.py
│   │
│   │   ├── schemas/
│   │   │   ├── input_schema.py        # Request models
│   │   │   ├── output_schema.py       # Response models
│   │   │   └── __init__.py
│   │
│   │   ├── services/
│   │   │   ├── analysis_service.py    # End-to-end pipeline
│   │   │   └── __init__.py
│   │
│   │   ├── utils/
│   │   │   ├── text_utils.py
│   │   │   ├── skill_utils.py
│   │   │   ├── constants.py
│   │   │   └── __init__.py
│   │
│   │   └── tests/
│   │       ├── test_agents.py
│   │       ├── test_health.py
│   │       └── __init__.py
│   │
│   ├── Dockerfile                    # Backend container
│   ├── requirements.txt
│   └── README.md
│
├── Frontend/
│   ├── index.html
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       └── script.js
│   ├── nginx.conf
│   └── Dockerfile                    # Frontend container
│
├── .github/
│   └── workflows/
│       └── ci.yml                    # CI/CD pipeline
│
├── docker-compose.yml                # Full stack orchestration
├── .env.example
├── .dockerignore
├── .gitignore
└── README.md                         # Main project README
```

## How to Run SkillProof AI

Prerequisites
- Python 3.10+
- Docker & Docker Compose
- GitHub Personal Access Token (for higher API limits)
- Groq API key (for LLaMA agents)

1) Clone the Repository
   ```bash
   git clone https://github.com/GUNTIKALYAN/skillproof-ai.git
   cd skillproof-ai
   ```

2) Environment Setup
   Create ```.env``` file in the project root
     
   ```bash
      GROQ_API_KEY=your_groq_api_key
      GITHUB_TOKEN=your_github_token
   ```
3) Run with Docker (Recommended)
   ```bash
   docker-compose up --build
   ```
   Services:
   - Backend (FastAPI): http://localhost:8000
   - Frontend (Nginx): http://localhost:3000

4) Run Backend Locally (Without Docker)
   ```bash
    cd Backend
    python -m venv venv
    source venv/bin/activate   # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload
   ```
Backend will be available at: http://localhost:8000


## Limitations & Assumptions

SkillProof AI is designed to be transparent and practical. The following limitations are intentional and acknowledged:

- Only **public GitHub repositories** are analyzed  
- Skills demonstrated outside GitHub (private repos, internships, work projects) may not be captured  
- Resume and job description parsing relies on **heuristics**, not deep semantic inference  
- ATS scoring is an **approximation**, not a replica of proprietary systems  
- Skill validation focuses on **evidence presence**, not absolute expertise level  

These constraints are deliberate to keep the system **explainable, auditable, and realistic**.

---

## Future Improvements

Potential enhancements that can be added without changing the core design:

- Support for **private repositories** via OAuth  
- LinkedIn and portfolio website integration  
- Deeper project-level code analysis  
- Recruiter-side dashboards for candidate comparison  
- Resume rewriting based on validated skills  
- Role-specific readiness benchmarks  

The current architecture is built to support these extensions cleanly.

---
Happy Learning 🚀


