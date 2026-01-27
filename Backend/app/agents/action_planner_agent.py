from app.agents.base_agent import BaseAgent

SYSTEM_PROMPT = """
You are an Action Planner Agent.

You receive:
- Skill audit results (credibility)
- Critical skill gaps

RULES:
- ONLY create actions for skills with credibility = low
- ONLY use skills explicitly provided
- Maximum 3 actions
- Actions must be realistic for an AI Engineer Intern
- Output strictly valid JSON
"""


class ActionPlannerAgent(BaseAgent):
    def run_agent(self, skill_audit: dict, gap_analysis: dict) -> dict:
        actions = []

        critical_skills = [
            gap["skill"] for gap in gap_analysis.get("critical_gaps", [])
        ]

        for skill in critical_skills:
            audit = skill_audit.get(skill, {})
            if audit.get("credibility") != "low":
                continue

            actions.append({
                "skill": skill,
                "action": f"Build a small focused project demonstrating {skill}",
                "expected_evidence": "GitHub repository with documented implementation"
            })

            if len(actions) == 3:
                break

        return {"actions": actions}
