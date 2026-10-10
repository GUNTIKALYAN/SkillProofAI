import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GITHUB_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


class AnalyzeRequest(BaseModel):
    jd_text: str = Field(..., min_length=10)
    github_username: str | None = None
    include_github: bool = True

    model_config = ConfigDict(from_attributes=True)

    @field_validator("github_username", mode="before")
    @classmethod
    def blank_username_is_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("github_username")
    @classmethod
    def username_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _GITHUB_USERNAME.fullmatch(value) is None:
            raise ValueError("GitHub username is invalid")
        return value
