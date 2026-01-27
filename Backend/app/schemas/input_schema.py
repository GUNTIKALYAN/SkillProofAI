from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class AnalyzeRequest(BaseModel):
    jd_text: str = Field(..., min_length=10)
    github_username: Optional[str] = None
    include_github: bool = True

    model_config = ConfigDict(from_attributes=True)
