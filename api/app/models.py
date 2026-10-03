import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    __tablename__ = "people"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), default="demo", server_default="demo", index=True)
    external_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
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


class EnrollmentInvitation(Base):
    __tablename__ = "enrollment_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("people.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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


class VerificationFeedback(Base):
    """Human-reviewed ground truth, kept separate from immutable inference events."""

    __tablename__ = "verification_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("verification_events.id"), unique=True, index=True)
    is_genuine: Mapped[bool] = mapped_column(Boolean)
    reviewer: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TenantKey(Base):
    __tablename__ = "tenant_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VerifySession(Base):
    __tablename__ = "verify_sessions"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("people.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    exam_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("verification_events.id"), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("verify_sessions.id"), index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrityCheck(Base):
    __tablename__ = "integrity_checks"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("people.id"), index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("verification_events.id"), nullable=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    face_sha256: Mapped[str] = mapped_column(String(64))
    voice_sha256: Mapped[str] = mapped_column(String(64))
    integrity_status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CheckEvidence(Base):
    __tablename__ = "check_evidence"
    __table_args__ = (UniqueConstraint("check_id", "modality"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    check_id: Mapped[str] = mapped_column(ForeignKey("integrity_checks.id"), index=True)
    modality: Mapped[str] = mapped_column(String(16))
    object_key: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)


class CheckReview(Base):
    """A tenant operator's judgement, separate from immutable model output."""
    __tablename__ = "check_reviews"
    check_id: Mapped[str] = mapped_column(ForeignKey("integrity_checks.id"), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    identity_truth: Mapped[str] = mapped_column(String(16))
    cheating_judgement: Mapped[str] = mapped_column(String(16))
    selection_reason: Mapped[str] = mapped_column(String(24))
    reviewer: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModalityObservation(Base):
    __tablename__ = 'modality_observations'
    __table_args__ = (UniqueConstraint('event_id', 'modality'),
                     Index('ix_modality_monitor_window', 'tenant_id', 'modality', 'model_version', 'created_at'),
                     Index('ix_modality_rollout_window', 'deployment_id', 'modality', 'created_at'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey('verification_events.id'), index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id'), index=True)
    modality: Mapped[str] = mapped_column(String(16), index=True)
    model_version: Mapped[str] = mapped_column(String(100), index=True)
    encoder: Mapped[str] = mapped_column(String(100))
    template_version: Mapped[str] = mapped_column(String(100))
    template_age_days: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    quality: Mapped[dict] = mapped_column(JSON)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    media_sha256: Mapped[str] = mapped_column(String(64))
    truth: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    random_audit: Mapped[bool] = mapped_column(Boolean, default=False)
    integrity_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    deployment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(20), default='CHAMPION')
    served_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    challenger_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    challenger_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    challenger_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_latency_ms: Mapped[float] = mapped_column(Float, default=0)
    challenger_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class TemplateVersion(Base):
    __tablename__ = 'template_versions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id'), index=True)
    modality: Mapped[str] = mapped_column(String(16))
    encoder: Mapped[str] = mapped_column(String(100))
    embeddings: Mapped[list] = mapped_column(JSON)
    previous_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    state: Mapped[str] = mapped_column(String(40), default='PENDING_REVIEW')
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActiveTemplate(Base):
    __tablename__ = 'active_templates'
    person_id: Mapped[str] = mapped_column(ForeignKey('people.id'), primary_key=True)
    modality: Mapped[str] = mapped_column(String(16), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('template_versions.id'))


class ModalityDeployment(Base):
    __tablename__ = 'modality_deployments'
    modality: Mapped[str] = mapped_column(String(16), primary_key=True)
    deployment_id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(40), default='CHAMPION')
    registry_name: Mapped[str] = mapped_column(String(120))
    champion_version: Mapped[str] = mapped_column(String(100))
    champion_threshold: Mapped[float] = mapped_column(Float)
    challenger_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    challenger_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    previous_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    stage_index: Mapped[int] = mapped_column(Integer, default=0)
    traffic_percent: Mapped[float] = mapped_column(Float, default=0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    stage_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LifecycleAudit(Base):
    __tablename__ = 'lifecycle_audit'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    modality: Mapped[str] = mapped_column(String(16), index=True)
    deployment_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModalityMonitorState(Base):
    __tablename__ = 'modality_monitor_state'
    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    modality: Mapped[str] = mapped_column(String(16), primary_key=True)
    model_version: Mapped[str] = mapped_column(String(100), primary_key=True)
    reference: Mapped[list] = mapped_column(JSON, default=list)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
