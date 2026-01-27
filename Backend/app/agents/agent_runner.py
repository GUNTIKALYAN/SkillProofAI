from app.agents.graph.graph_builder import build_skillproof_graph


def run_agents(ai_input: dict) -> dict:
    graph = build_skillproof_graph()

    final_state = graph.invoke({
        "skill_evidence": ai_input["skill_evidence"],
        "missing_skills": ai_input["missing_skills"],
        "ats_data": ai_input["ats_data"],

        "skill_audit": {},
        "gap_analysis": {},
        "ats_impact": {},
        "action_plan": {}
    })

    return {
        "skill_audit": final_state["skill_audit"],
        "gap_analysis": final_state["gap_analysis"],
        "ats_impact": final_state["ats_impact"],
        "action_plan": final_state["action_plan"]
    }
