from typing import Dict, List
import json

from app.llm.client import LLMClient


class QuickInsightAgent:
    """
    LLM-powered quick resume insight agent.

    Purpose:
    - Explain missing skills
    - Give brief resume insight
    - Generate a 2-day learning plan
    """

    def __init__(self):
        self.llm = LLMClient()

    def build_prompt(
        self,
        *,
        missing_skills: List[str],
        resume_score_current: int,
        resume_score_after: int,
        job_role: str,
        github_considered: bool,
    ) -> str:
        return f"""
You are an AI career assistant helping a candidate applying for the role of {job_role}.

Context:
- Current resume score: {resume_score_current}/100
- Estimated score after improvements: {resume_score_after}/100
- Missing skills: {missing_skills}
- GitHub evidence considered: {github_considered}

Your task:
1. Briefly explain what the resume is missing compared to the job.
2. Explain why each missing skill matters (short, practical).
3. Create a realistic 2-day learning plan to fix the gaps.

Rules:
- Be concise and practical.
- No fluff, no motivation talk.
- Assume candidate is an intern or fresher.
- Output MUST be valid JSON only.
- Do NOT include markdown or extra text.

Output JSON format:
{{
  "insight_summary": "string",
  "missing_skills_explained": [
    {{
      "skill": "string",
      "why_it_matters": "string"
    }}
  ],
  "two_day_learning_plan": [
    {{
      "day": 1,
      "focus": "string",
      "tasks": ["string", "string"]
    }},
    {{
      "day": 2,
      "focus": "string",
      "tasks": ["string", "string"]
    }}
  ]
}}
"""

    def run(
        self,
        *,
        missing_skills: List[str],
        resume_score_current: int,
        resume_score_after: int,
        job_role: str = "AI Engineer Intern",
        github_considered: bool = True,
    ) -> Dict:
        """
        Executes the quick insight agent and returns structured JSON.
        """

        if not missing_skills:
            return {
                "insight_summary": "Your resume already aligns well with the job requirements.",
                "missing_skills_explained": [],
                "two_day_learning_plan": [],
            }

        prompt = self.build_prompt(
            missing_skills=missing_skills,
            resume_score_current=resume_score_current,
            resume_score_after=resume_score_after,
            job_role=job_role,
            github_considered=github_considered,
        )

        raw_output = self.llm.generate(
            system_prompt="You are a precise JSON-only response generator.",
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=700,
        )

        try:
            return json.loads(raw_output)
        except json.JSONDecodeError:
            # Hard fallback to avoid breaking frontend
            return {
                "insight_summary": "Unable to generate detailed insight. Please try again.",
                "missing_skills_explained": [
                    {
                        "skill": s,
                        "why_it_matters": "Important for this role."
                    }
                    for s in missing_skills
                ],
                "two_day_learning_plan": [],
            }
