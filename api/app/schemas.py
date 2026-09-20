from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=200)


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    external_id: str
    display_name: str
    active: bool
    created_at: datetime
    face_samples: int = 0
    voice_samples: int = 0
    ready: bool = False


class EnrollmentOut(BaseModel):
    person_id: str
    face_added: int
    voice_added: int
    rejected: list[str]
    ready: bool


class VerificationOut(BaseModel):
    event_id: str
    person_id: str
    session_id: str
    accepted: bool
    decision: str
    risk_score: float
    face_score: float | None
    voice_score: float | None
    face_quality: float | None
    voice_quality: float | None
    thresholds: dict[str, float]
    reasons: list[str]
    model_version: str
    latency_ms: int

