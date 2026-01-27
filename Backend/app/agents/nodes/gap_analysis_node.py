from app.agents.gap_analysis_agent import GapAnalysisAgent
from app.agents.graph.graph_state import SkillProofState


def gap_analysis_node(state: SkillProofState):
    agent = GapAnalysisAgent()
    result = agent.run_agent(state.missing_skills)
    return {"gap_analysis": result}

