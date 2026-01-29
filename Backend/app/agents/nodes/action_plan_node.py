from app.agents.action_plan_agent import ActionPlannerAgent
from app.agents.graph.graph_state import SkillProofState


def action_planner_node(state: SkillProofState):
    agent = ActionPlannerAgent()

    result = agent.run_agent(
        skill_audit=state.skill_audit,
        gap_analysis=state.gap_analysis
    )

    return {"action_plan": result}