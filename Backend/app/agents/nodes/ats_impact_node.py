from app.agents.ats_impact_agent import ATSImpactAgent
from app.agents.graph.graph_state import SkillProofState

def ats_impact_node(state: SkillProofState):
    agent = ATSImpactAgent()
    result = agent.run_agent({
        "missing_skills": state.missing_skills,
        "ats_data": state.ats_data
    })
    return {"ats_impact": result}
