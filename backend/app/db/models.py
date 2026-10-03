from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AiAllowanceRecord(Base):
    __tablename__ = "ai_allowances"
    owner_user_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)


class AiUsageRecord(Base):
    __tablename__ = "ai_usage"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    period: Mapped[str] = mapped_column(String(7))
    operation: Mapped[str] = mapped_column(String(80))
    units: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="reserved")
    job_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class ManualMembershipRecord(Base):
    __tablename__ = "manual_memberships"
    owner_user_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    monthly_limit: Mapped[int] = mapped_column(Integer, default=100)
    note: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class MembershipAuditRecord(Base):
    __tablename__ = "membership_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    actor_user_id: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(20))
    request: Mapped[dict] = mapped_column(JSON)
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class FeedbackRecord(Base):
    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sender_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    contact: Mapped[str] = mapped_column(String(320))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class FeedbackRateRecord(Base):
    __tablename__ = "feedback_rate_limits"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class AppUserRecord(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    clerk_user_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(40), default="user", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BillingCheckoutRecord(Base):
    __tablename__ = "billing_checkouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    checkout_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    plan_key: Mapped[str] = mapped_column(String(80), index=True)
    creem_product_id: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )


class UserSubscriptionRecord(Base):
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    creem_customer_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    creem_subscription_id: Mapped[str | None] = mapped_column(
        String(180), nullable=True, unique=True, index=True
    )
    creem_product_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    plan_key: Mapped[str] = mapped_column(String(80), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )


class BillingEventRecord(Base):
    __tablename__ = "billing_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    creem_object_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())


class VedicSessionRecord(Base):
    __tablename__ = "vedic_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    stage: Mapped[str] = mapped_column(String(60), default="draft", index=True)
    storage_backend: Mapped[str] = mapped_column(String(30), default="local")
    storage_root: Mapped[str] = mapped_column(Text)
    subject_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_count: Mapped[int] = mapped_column(Integer, default=0)
    export_count: Mapped[int] = mapped_column(Integer, default=0)
    has_pdf: Mapped[bool] = mapped_column(Boolean, default=False)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_completed: Mapped[int] = mapped_column(Integer, default=0)
    progress_running: Mapped[int] = mapped_column(Integer, default=0)
    progress_failed: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    active_job_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    active_node: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )


class VedicArtifactRecord(Base):
    __tablename__ = "vedic_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="other")
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    storage_backend: Mapped[str] = mapped_column(String(30), default="local")
    storage_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    producer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    checkpointed: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_sha256: Mapped[str | None] = mapped_column(String(80), nullable=True)
    chart_record_sha256: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("session_id", "path", name="uq_vedic_artifact_session_path"),
    )


class VedicExportRecord(Base):
    __tablename__ = "vedic_exports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    path: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    storage_backend: Mapped[str] = mapped_column(String(30), default="local")
    storage_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    __table_args__ = (UniqueConstraint("session_id", "path", name="uq_vedic_export_session_path"),)


class VedicCoreJobRecord(Base):
    __tablename__ = "vedic_core_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    message: Mapped[str] = mapped_column(Text)
    user_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_completed: Mapped[int] = mapped_column(Integer, default=0)
    progress_running: Mapped[int] = mapped_column(Integer, default=0)
    progress_failed: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )


class VedicCoreJobNodeRecord(Base):
    __tablename__ = "vedic_core_job_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(80), index=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    label: Mapped[str] = mapped_column(Text)
    wave: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    files: Mapped[list] = mapped_column(JSON, default=list)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    __table_args__ = (UniqueConstraint("job_id", "node_id", name="uq_vedic_job_node"),)


class JournalEntryRecord(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (UniqueConstraint("owner_user_id", "day", name="uq_journal_owner_day"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_user_id: Mapped[str] = mapped_column(String(160), index=True)
    day: Mapped[str] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(80))
    mood: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(32))
    calendar: Mapped[dict] = mapped_column(JSON)
    reflections: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )


class UserProfileRecord(Base):
    """The account owner's own birth details, collected once at onboarding."""

    __tablename__ = "user_profiles"
    owner_user_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    birth_date: Mapped[str] = mapped_column(String(10))
    birth_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    birth_place: Mapped[str] = mapped_column(Text)
    place_label: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(80))
    gender: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now()
    )
