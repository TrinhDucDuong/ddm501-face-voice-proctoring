import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    samples: Mapped[list["BiometricSample"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class BiometricSample(Base):
    __tablename__ = "biometric_samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    person_id: Mapped[str] = mapped_column(ForeignKey("people.id"), index=True)
    modality: Mapped[str] = mapped_column(String(16), index=True)
    embedding: Mapped[list[float]] = mapped_column(JSON)
    quality: Mapped[float] = mapped_column(Float)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    person: Mapped[Person] = relationship(back_populates="samples")


class VerificationEvent(Base):
    __tablename__ = "verification_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    person_id: Mapped[str] = mapped_column(ForeignKey("people.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    face_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    face_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons: Mapped[list[str]] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(100), default="local-default")
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

