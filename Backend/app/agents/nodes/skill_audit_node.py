from app.agents.skill_audit_agent import SkillAuditAgent
from app.agents.graph.graph_state import SkillProofState


def skill_audit_node(state: SkillProofState):
    agent = SkillAuditAgent()
    result = agent.run_agent(state.skill_evidence)
    return {"skill_audit": result}

