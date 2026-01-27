from app.agents.base_agent import BaseAgent

SYSTEM_PROMPT = """
You are a Skill Audit Agent.

You receive structured skill evidence data.
Each skill has a status: supported, partially_supported, or unsupported.

RULES:
- DO NOT introduce new skills, tools, or experience.
- DO NOT change the given status.
- DO NOT assume years of experience.
- ONLY explain why the given status exists.
- Map credibility strictly as:
  supported -> high
  partially_supported -> medium
  unsupported -> low

Return strictly valid JSON.
"""


class SkillAuditAgent(BaseAgent):
    def run_agent(self, skill_evidence: dict) -> dict:
        payload = {}

        for skill, data in skill_evidence.items():
            status = data.get("status")

            if status == "supported":
                payload[skill] = {
                    "credibility": "high",
                    "reason": "Skill is marked as supported based on resume and evidence."
                }
            elif status == "partially_supported":
                payload[skill] = {
                    "credibility": "medium",
                    "reason": "Skill is partially supported based on limited evidence."
                }
            else:
                payload[skill] = {
                    "credibility": "low",
                    "reason": "Skill is unsupported due to lack of evidence."
                }

        return payload
