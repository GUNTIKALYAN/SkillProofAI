from langgraph.graph import StateGraph, END
from app.agents.graph.graph_state import SkillProofState

from app.agents.nodes.skill_audit_node import skill_audit_node
from app.agents.nodes.gap_analysis_node import gap_analysis_node
from app.agents.nodes.ats_impact_node import ats_impact_node
from app.agents.nodes.action_planner_node import action_planner_node


def build_skillproof_graph():
    graph = StateGraph(SkillProofState)

    graph.add_node("skill_audit", skill_audit_node)
    graph.add_node("gap_analysis", gap_analysis_node)
    graph.add_node("ats_impact", ats_impact_node)
    graph.add_node("action_plan", action_planner_node)

    graph.set_entry_point("skill_audit")

    graph.add_edge("skill_audit", "gap_analysis")
    graph.add_edge("gap_analysis", "ats_impact")
    graph.add_edge("ats_impact", "action_plan")
    graph.add_edge("action_plan", END)

    return graph.compile()
