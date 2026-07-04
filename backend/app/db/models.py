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


class VedicSessionRecord(Base):
    __tablename__ = "vedic_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
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
    path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="other")
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    storage_backend: Mapped[str] = mapped_column(String(30), default="local")
    storage_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    producer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    checkpointed: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_sha256: Mapped[str | None] = mapped_column(String(80), nullable=True)
    structured_data_sha256: Mapped[str | None] = mapped_column(String(80), nullable=True)
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
