import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GITHUB_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class AnalyzeRequest(BaseModel):
    jd_text: str = Field(..., min_length=10)
    github_username: str = Field(min_length=1, max_length=39)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("github_username", mode="before")
    @classmethod
    def strip_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("github_username")
    @classmethod
    def username_format(cls, value: str) -> str:
        if _GITHUB_USERNAME.fullmatch(value) is None:
            raise ValueError("GitHub username is invalid")
        return value
