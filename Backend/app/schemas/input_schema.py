from pydantic import BaseModel, Field
from typing import Optional


class AnalyzeRequest(BaseModel):
    """
    Input contract for /analyze endpoint.
    """

    jd_text: str = Field(
        ...,
        min_length=10,
        description="Job description text"
    )

    github_username: Optional[str] = Field(
        None,
        description="Public GitHub username for evidence collection"
    )

    include_github: bool = Field(
        default=True,
        description="Whether to fetch GitHub evidence"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "jd_text": "Looking for a Python developer with ML experience",
                "github_username": "GUNTIKALYAN",
                "include_github": True
            }
        }
