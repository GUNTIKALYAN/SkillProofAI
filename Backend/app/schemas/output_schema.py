from pydantic import BaseModel
from typing import Dict, Any


class AnalyzeResponse(BaseModel):
    skill_alignment: Dict[str, Any]
    evidence_validation: Dict[str, Any]
    ai_analysis: Dict[str, Any]

