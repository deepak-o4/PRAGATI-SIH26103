"""Framework-free domain types for PRAGATI.

Everything in the analytics / risk / forecasting / scenario / copilot layers works
on these plain dataclasses, so it is unit-testable without a database or web stack.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Optional


class ProjectStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    UNDER_PREPARATION = "UNDER_PREPARATION"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    DELAYED = "DELAYED"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


_EXEC = {ProjectStatus.ON_TRACK, ProjectStatus.AT_RISK, ProjectStatus.DELAYED}

# Allowed status transitions. Terminal states (COMPLETED, CANCELLED) have no outgoing edges.
STATUS_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.PLANNED: {ProjectStatus.UNDER_PREPARATION, ProjectStatus.ON_HOLD, ProjectStatus.CANCELLED},
    ProjectStatus.UNDER_PREPARATION: {ProjectStatus.UNDER_CONSTRUCTION, ProjectStatus.ON_HOLD,
                                      ProjectStatus.CANCELLED},
    ProjectStatus.UNDER_CONSTRUCTION: _EXEC | {ProjectStatus.ON_HOLD, ProjectStatus.COMPLETED,
                                               ProjectStatus.CANCELLED},
    ProjectStatus.ON_TRACK: (_EXEC - {ProjectStatus.ON_TRACK}) | {ProjectStatus.ON_HOLD, ProjectStatus.COMPLETED,
                                                                  ProjectStatus.CANCELLED},
    ProjectStatus.AT_RISK: (_EXEC - {ProjectStatus.AT_RISK}) | {ProjectStatus.ON_HOLD, ProjectStatus.COMPLETED,
                                                                ProjectStatus.CANCELLED},
    ProjectStatus.DELAYED: (_EXEC - {ProjectStatus.DELAYED}) | {ProjectStatus.ON_HOLD, ProjectStatus.COMPLETED,
                                                                ProjectStatus.CANCELLED},
    ProjectStatus.ON_HOLD: {ProjectStatus.UNDER_PREPARATION, ProjectStatus.UNDER_CONSTRUCTION,
                            ProjectStatus.CANCELLED},
    ProjectStatus.COMPLETED: set(),
    ProjectStatus.CANCELLED: set(),
}


def can_transition(src: ProjectStatus, dst: ProjectStatus) -> bool:
    return src == dst or dst in STATUS_TRANSITIONS[src]


class IssueType(str, enum.Enum):
    LAND = "LAND"
    ENVIRONMENT_CLEARANCE = "ENVIRONMENT_CLEARANCE"
    FUNDING = "FUNDING"
    CONTRACTOR = "CONTRACTOR"
    PROCUREMENT = "PROCUREMENT"
    UTILITY_SHIFTING = "UTILITY_SHIFTING"
    LEGAL = "LEGAL"
    DESIGN = "DESIGN"
    MATERIAL = "MATERIAL"
    LABOUR = "LABOUR"
    WEATHER = "WEATHER"
    APPROVAL = "APPROVAL"
    TECHNICAL = "TECHNICAL"
    LOGISTICS = "LOGISTICS"
    OTHER = "OTHER"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_WEIGHT = {Severity.LOW: 0.15, Severity.MEDIUM: 0.4, Severity.HIGH: 0.7, Severity.CRITICAL: 1.0}


class IssueStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class RiskBand(str, enum.Enum):
    STABLE = "STABLE"
    WATCH = "WATCH"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DataOrigin(str, enum.Enum):
    OFFICIAL = "OFFICIAL"
    IMPORTED = "IMPORTED"
    USER_UPLOADED = "USER_UPLOADED"
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"
    DERIVED = "DERIVED"
    PREDICTED = "PREDICTED"


@dataclass(frozen=True)
class Snapshot:
    snapshot_month: date  # first day of the reporting month
    physical_progress_pct: Optional[float] = None
    financial_progress_pct: Optional[float] = None
    cumulative_expenditure_crore: Optional[float] = None
    revised_cost_crore: Optional[float] = None
    revised_end_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
    issues_text: Optional[str] = None
    source: Optional[str] = None
    source_document: Optional[str] = None
    origin: DataOrigin = DataOrigin.IMPORTED


@dataclass(frozen=True)
class Milestone:
    name: str
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    completion_pct: float = 0.0
    depends_on: Optional[str] = None
    weight: float = 1.0

    @property
    def is_complete(self) -> bool:
        return self.actual_end is not None or self.completion_pct >= 100.0

    def delay_days(self, as_of: date) -> int:
        """Days late vs plan. Completed: actual_end - planned_end. Open: as_of - planned_end if overdue."""
        if self.planned_end is None:
            return 0
        ref = self.actual_end if self.actual_end is not None else (None if self.is_complete else as_of)
        if ref is None:
            return 0
        return max(0, (ref - self.planned_end).days)

    def status(self, as_of: date) -> str:
        if self.is_complete:
            return "COMPLETED" if self.delay_days(as_of) == 0 else "COMPLETED_LATE"
        if self.delay_days(as_of) > 0:
            return "DELAYED"
        if self.actual_start is not None or self.completion_pct > 0:
            return "IN_PROGRESS"
        return "NOT_STARTED"


@dataclass(frozen=True)
class Issue:
    issue_type: IssueType
    severity: Severity
    status: IssueStatus = IssueStatus.OPEN
    description: str = ""
    reported_date: Optional[date] = None
    expected_resolution_date: Optional[date] = None
    actual_resolution_date: Optional[date] = None
    owner: Optional[str] = None
    impact: Optional[str] = None
    id: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.status in (IssueStatus.OPEN, IssueStatus.IN_PROGRESS)


@dataclass(frozen=True)
class Project:
    project_code: str
    project_name: str
    sector: Optional[str] = None
    line_ministry: Optional[str] = None
    department: Optional[str] = None
    implementing_agency: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    project_type: Optional[str] = None
    description: Optional[str] = None
    original_cost_crore: Optional[float] = None
    revised_cost_crore: Optional[float] = None
    cumulative_expenditure_crore: Optional[float] = None
    start_date: Optional[date] = None
    original_end_date: Optional[date] = None
    revised_end_date: Optional[date] = None
    physical_progress_pct: Optional[float] = None
    financial_progress_pct: Optional[float] = None
    status: ProjectStatus = ProjectStatus.UNDER_CONSTRUCTION
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    origin: DataOrigin = DataOrigin.IMPORTED
    snapshots: tuple = field(default_factory=tuple)
    milestones: tuple = field(default_factory=tuple)
    issues: tuple = field(default_factory=tuple)

    def with_(self, **kw) -> "Project":
        return replace(self, **kw)

    def sorted_snapshots(self) -> list:
        return sorted(self.snapshots, key=lambda s: s.snapshot_month)

    @property
    def is_terminal(self) -> bool:
        return self.status in (ProjectStatus.COMPLETED, ProjectStatus.CANCELLED)


def risk_band(score: float) -> RiskBand:
    """0-30 STABLE, 31-60 WATCH, 61-80 WARNING, 81-100 CRITICAL (score rounded to nearest int)."""
    s = int(round(score))
    if s <= 30:
        return RiskBand.STABLE
    if s <= 60:
        return RiskBand.WATCH
    if s <= 80:
        return RiskBand.WARNING
    return RiskBand.CRITICAL
