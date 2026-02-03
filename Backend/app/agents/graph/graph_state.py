from typing import Dict, Any
from pydantic import BaseModel


class SkillProofState(BaseModel):
    skill_evidence: Dict[str, Any]
    missing_skills: Dict[str, str]
    ats_data: Dict[str, Any]

    skill_audit: Dict[str, Any] = {}
    gap_analysis: Dict[str, Any] = {}
    ats_impact: Dict[str, Any] = {}
    action_plan: Dict[str, Any] = {}
