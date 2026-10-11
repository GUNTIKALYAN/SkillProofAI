import uuid
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    def normalized_email(self) -> str:
        return str(self.email).strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)

    def normalized_email(self) -> str:
        return str(self.email).strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class AnalysisPublic(BaseModel):
    id: uuid.UUID
    status: str
    score: float | None
    github_username: str | None
    created_at: datetime
    result: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class JobAccepted(BaseModel):
    job_id: uuid.UUID
    status: str


class AnalysisSummary(BaseModel):
    id: uuid.UUID
    status: str
    score: float | None
    github_username: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyUrlRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=300)

    @field_validator("name", "url")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value is required")
        return cleaned

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Company URL must start with http:// or https://")
        return value
