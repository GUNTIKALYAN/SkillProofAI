from app.agents.agent_runner import run_agents


if __name__ == "__main__":
    dummy_input = {
        "skill_evidence": {
            "python": {"status": "supported"},
            "pytorch": {"status": "unsupported"}
        },
        "missing_skills": {
            "pytorch": "required but no evidence"
        },
        "ats_data": {
            "current_score": 65,
            "missing_keywords": ["pytorch"]
        }
    }

    result = run_agents(dummy_input)
    print("\n===== MULTI-AGENT OUTPUT =====\n")
    print(result)
