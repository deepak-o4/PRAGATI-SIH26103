"""PRAGATI relational model. Money in ₹ crore; dates are calendar dates; snapshots are monthly."""
import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, Uuid, CheckConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, utcnow
from app.domain.types import DataOrigin, IssueStatus, IssueType, ProjectStatus, RiskBand, Severity


class Role(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    PROGRAM_MANAGER = "PROGRAM_MANAGER"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    ANALYST = "ANALYST"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"


class ActionStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


def _e(cls):
    return Enum(cls, native_enum=False, length=32, validate_strings=True)


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(_e(Role), default=Role.VIEWER)
    organisation: Mapped[Optional[str]] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DataSource(Base, IdMixin, TimestampMixin):
    __tablename__ = "data_sources"
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    source_document: Mapped[Optional[str]] = mapped_column(String(300))
    source_date: Mapped[Optional[date]] = mapped_column(Date)
    snapshot_month: Mapped[Optional[date]] = mapped_column(Date)
    origin: Mapped[DataOrigin] = mapped_column(_e(DataOrigin), default=DataOrigin.IMPORTED)
    record_counts: Mapped[Optional[dict]] = mapped_column(JSON)
    report: Mapped[Optional[dict]] = mapped_column(JSON)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Project(Base, IdMixin, TimestampMixin):
    __tablename__ = "projects"
    project_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    project_name: Mapped[str] = mapped_column(String(400))
    sector: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    line_ministry: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    department: Mapped[Optional[str]] = mapped_column(String(200))
    implementing_agency: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    state: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    district: Mapped[Optional[str]] = mapped_column(String(80))
    project_type: Mapped[Optional[str]] = mapped_column(String(80))
    description: Mapped[Optional[str]] = mapped_column(Text)
    original_cost_crore: Mapped[Optional[float]] = mapped_column(Float)
    revised_cost_crore: Mapped[Optional[float]] = mapped_column(Float)
    cumulative_expenditure_crore: Mapped[Optional[float]] = mapped_column(Float)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    original_end_date: Mapped[Optional[date]] = mapped_column(Date)
    revised_end_date: Mapped[Optional[date]] = mapped_column(Date)
    physical_progress_pct: Mapped[Optional[float]] = mapped_column(Float)
    financial_progress_pct: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[ProjectStatus] = mapped_column(_e(ProjectStatus), default=ProjectStatus.UNDER_CONSTRUCTION, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    origin: Mapped[DataOrigin] = mapped_column(_e(DataOrigin), default=DataOrigin.IMPORTED, index=True)
    data_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"))
    # latest computed risk (denormalised for fast filtering); full history in risk_snapshots
    risk_score: Mapped[Optional[float]] = mapped_column(Float, index=True)
    risk_level: Mapped[Optional[RiskBand]] = mapped_column(_e(RiskBand), index=True)

    snapshots = relationship("ProjectSnapshot", back_populates="project", cascade="all, delete-orphan", order_by="ProjectSnapshot.snapshot_month")
    milestones = relationship("ProjectMilestone", back_populates="project", cascade="all, delete-orphan")
    issues = relationship("ProjectIssue", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("physical_progress_pct IS NULL OR (physical_progress_pct >= 0 AND physical_progress_pct <= 100)", name="ck_proj_phys"),
        CheckConstraint("original_cost_crore IS NULL OR original_cost_crore >= 0", name="ck_proj_orig_cost"),
        CheckConstraint("revised_cost_crore IS NULL OR revised_cost_crore >= 0", name="ck_proj_rev_cost"),
        CheckConstraint("cumulative_expenditure_crore IS NULL OR cumulative_expenditure_crore >= 0", name="ck_proj_exp"),
    )


class ProjectSnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_snapshots"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    snapshot_month: Mapped[date] = mapped_column(Date, index=True)
    physical_progress_pct: Mapped[Optional[float]] = mapped_column(Float)
    financial_progress_pct: Mapped[Optional[float]] = mapped_column(Float)
    cumulative_expenditure_crore: Mapped[Optional[float]] = mapped_column(Float)
    revised_cost_crore: Mapped[Optional[float]] = mapped_column(Float)
    revised_end_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[Optional[ProjectStatus]] = mapped_column(_e(ProjectStatus))
    issues_text: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(200))
    source_document: Mapped[Optional[str]] = mapped_column(String(300))
    origin: Mapped[DataOrigin] = mapped_column(_e(DataOrigin), default=DataOrigin.IMPORTED)
    project = relationship("Project", back_populates="snapshots")
    __table_args__ = (UniqueConstraint("project_id", "snapshot_month", name="uq_snapshot_project_month"),
                      CheckConstraint("physical_progress_pct IS NULL OR (physical_progress_pct >= 0 AND physical_progress_pct <= 100)", name="ck_snap_phys"))


class ProjectMilestone(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_milestones"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    planned_start: Mapped[Optional[date]] = mapped_column(Date)
    planned_end: Mapped[Optional[date]] = mapped_column(Date)
    actual_start: Mapped[Optional[date]] = mapped_column(Date)
    actual_end: Mapped[Optional[date]] = mapped_column(Date)
    completion_pct: Mapped[float] = mapped_column(Float, default=0.0)
    depends_on: Mapped[Optional[str]] = mapped_column(String(200))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    project = relationship("Project", back_populates="milestones")


class ProjectIssue(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_issues"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    issue_type: Mapped[IssueType] = mapped_column(_e(IssueType), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[Severity] = mapped_column(_e(Severity), default=Severity.MEDIUM)
    reported_date: Mapped[Optional[date]] = mapped_column(Date)
    expected_resolution_date: Mapped[Optional[date]] = mapped_column(Date)
    actual_resolution_date: Mapped[Optional[date]] = mapped_column(Date)
    owner: Mapped[Optional[str]] = mapped_column(String(160))
    status: Mapped[IssueStatus] = mapped_column(_e(IssueStatus), default=IssueStatus.OPEN, index=True)
    impact: Mapped[Optional[str]] = mapped_column(Text)
    project = relationship("Project", back_populates="issues")


class ProjectDocument(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_documents"
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(80))
    content_type: Mapped[Optional[str]] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[Optional[str]] = mapped_column(Text)
    entities: Mapped[Optional[dict]] = mapped_column(JSON)
    origin: Mapped[DataOrigin] = mapped_column(_e(DataOrigin), default=DataOrigin.USER_UPLOADED)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RiskSnapshot(Base, IdMixin):
    """Auditable record of each risk computation (score, version, weights, factors)."""
    __tablename__ = "risk_snapshots"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    band: Mapped[RiskBand] = mapped_column(_e(RiskBand))
    version: Mapped[str] = mapped_column(String(32))
    weights: Mapped[dict] = mapped_column(JSON)
    factors: Mapped[list] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_risk_proj_asof", "project_id", "as_of"),)


class Forecast(Base, IdMixin):
    __tablename__ = "forecasts"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(48))
    payload: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scenario(Base, IdMixin):
    __tablename__ = "scenarios"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    adjustments: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)   # scenario_result kept inline (1:1)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "action_items"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner: Mapped[Optional[str]] = mapped_column(String(160))
    priority: Mapped[Priority] = mapped_column(_e(Priority), default=Priority.MEDIUM)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[ActionStatus] = mapped_column(_e(ActionStatus), default=ActionStatus.OPEN, index=True)
    source: Mapped[str] = mapped_column(String(48), default="MANUAL")  # MANUAL | RISK_ALERT | SCENARIO
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Alert(Base, IdMixin):
    __tablename__ = "alerts"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(48))   # RISK_BAND_CHANGE | STAGNATION | DEADLINE | IMBALANCE
    severity: Mapped[Severity] = mapped_column(_e(Severity))
    message: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base, IdMixin):
    __tablename__ = "audit_logs"
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    detail: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
