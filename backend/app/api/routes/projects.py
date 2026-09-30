from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from app.analytics.metrics import cost_metrics, progress_metrics, schedule_metrics
from app.analytics.portfolio import enrich
from app.api.deps import ANALYSIS_ROLES, WRITE_ROLES, CurrentUser, SessionDep, audit, require
from app.domain.types import (DataOrigin, IssueStatus, IssueType, ProjectStatus, Severity, can_transition)
from app.forecasting.forecast import forecast_completion
from app.ml.delay_model import load_model, predict
from app.core.config import settings
from app.models import entities as E
from app.risk.engine import risk_history
from app.scenarios.simulate import ScenarioAdjustments, run_scenario
from app.services.analysis import recompute_project, risk_config
from app.services.repository import get_orm_project, to_domain

router = APIRouter(prefix="/projects", tags=["projects"])
Pct = Field(default=None, ge=0, le=100)
Cost = Field(default=None, ge=0)


class ProjectIn(BaseModel):
    project_code: str = Field(min_length=1, max_length=64)
    project_name: str = Field(min_length=1, max_length=400)
    sector: Optional[str] = None
    line_ministry: Optional[str] = None
    department: Optional[str] = None
    implementing_agency: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    project_type: Optional[str] = None
    description: Optional[str] = None
    original_cost_crore: Optional[float] = Cost
    revised_cost_crore: Optional[float] = Cost
    cumulative_expenditure_crore: Optional[float] = Cost
    start_date: Optional[date] = None
    original_end_date: Optional[date] = None
    revised_end_date: Optional[date] = None
    physical_progress_pct: Optional[float] = Pct
    financial_progress_pct: Optional[float] = Pct
    status: ProjectStatus = ProjectStatus.UNDER_CONSTRUCTION
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    origin: DataOrigin = DataOrigin.USER_UPLOADED

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.original_end_date and self.original_end_date < self.start_date:
            raise ValueError("original_end_date precedes start_date")
        if self.start_date and self.revised_end_date and self.revised_end_date < self.start_date:
            raise ValueError("revised_end_date precedes start_date")
        return self


class ProjectPatch(BaseModel):
    project_name: Optional[str] = None
    sector: Optional[str] = None
    line_ministry: Optional[str] = None
    implementing_agency: Optional[str] = None
    state: Optional[str] = None
    original_cost_crore: Optional[float] = Cost
    revised_cost_crore: Optional[float] = Cost
    cumulative_expenditure_crore: Optional[float] = Cost
    revised_end_date: Optional[date] = None
    physical_progress_pct: Optional[float] = Pct
    financial_progress_pct: Optional[float] = Pct
    status: Optional[ProjectStatus] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class SnapshotIn(BaseModel):
    snapshot_month: date
    physical_progress_pct: Optional[float] = Pct
    financial_progress_pct: Optional[float] = Pct
    cumulative_expenditure_crore: Optional[float] = Cost
    revised_cost_crore: Optional[float] = Cost
    revised_end_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
    issues_text: Optional[str] = None
    source: Optional[str] = None
    source_document: Optional[str] = None


class MilestoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    completion_pct: float = Field(default=0, ge=0, le=100)
    depends_on: Optional[str] = None
    weight: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def _o(self):
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end precedes planned_start")
        if self.actual_start and self.actual_end and self.actual_end < self.actual_start:
            raise ValueError("actual_end precedes actual_start")
        return self


class IssueIn(BaseModel):
    issue_type: IssueType
    description: str = ""
    severity: Severity = Severity.MEDIUM
    reported_date: Optional[date] = None
    expected_resolution_date: Optional[date] = None
    actual_resolution_date: Optional[date] = None
    owner: Optional[str] = None
    status: IssueStatus = IssueStatus.OPEN
    impact: Optional[str] = None


class ActionIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    owner: Optional[str] = None
    priority: E.Priority = E.Priority.MEDIUM
    due_date: Optional[date] = None
    source: str = "MANUAL"


class ScenarioIn(BaseModel):
    name: str = "Untitled scenario"
    progress_increase_pts: float = Field(default=0, ge=0, le=100)
    expenditure_increase_pct: float = Field(default=0, ge=0, le=500)
    revised_cost_increase_pct: float = Field(default=0, ge=0, le=500)
    milestone_delay_days: int = Field(default=0, ge=0, le=3650)
    milestone_name: Optional[str] = None
    resolve_issue_ids: list[str] = []
    resolve_all_critical: bool = False
    completion_slip_days: int = Field(default=0, ge=0, le=3650)
    recovery_days_assumed: int = Field(default=0, ge=0, le=3650)
    save: bool = False


async def _proj(db, ident):
    row = await get_orm_project(db, ident)
    if row is None:
        raise HTTPException(404, "Project not found")
    return row


def _out(row: E.Project, as_of: date) -> dict:
    d = enrich(to_domain(row), as_of, risk_config())
    d["id"] = str(row.id)
    return d


@router.get("")
async def list_projects(db: SessionDep, user: CurrentUser, q: Optional[str] = None, sector: Optional[str] = None,
                        line_ministry: Optional[str] = None, state: Optional[str] = None, status: Optional[ProjectStatus] = None,
                        risk_level: Optional[str] = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                        sort: str = Query("risk_score"), order: str = Query("desc", pattern="^(asc|desc)$")):
    stmt = select(E.Project)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(E.Project.project_name).like(like) | func.lower(E.Project.project_code).like(like))
    for col, val in (("sector", sector), ("line_ministry", line_ministry), ("state", state), ("status", status)):
        if val:
            stmt = stmt.where(getattr(E.Project, col) == val)
    if risk_level:
        stmt = stmt.where(E.Project.risk_level == risk_level.upper())
    sortable = {"risk_score", "project_code", "project_name", "physical_progress_pct", "original_cost_crore", "revised_cost_crore", "sector", "state"}
    if sort not in sortable:
        raise HTTPException(422, f"sort must be one of {sorted(sortable)}")
    col = getattr(E.Project, sort)
    stmt = stmt.order_by(col.desc().nulls_last() if order == "desc" else col.asc().nulls_last(), E.Project.project_code)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    items = [{"id": str(r.id), "project_code": r.project_code, "project_name": r.project_name, "sector": r.sector,
              "line_ministry": r.line_ministry, "state": r.state, "status": r.status.value, "origin": r.origin.value,
              "physical_progress_pct": r.physical_progress_pct, "original_cost_crore": r.original_cost_crore,
              "revised_cost_crore": r.revised_cost_crore, "risk_score": r.risk_score,
              "risk_level": r.risk_level.value if r.risk_level else None} for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_project(body: ProjectIn, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    if (await db.execute(select(E.Project.id).where(E.Project.project_code == body.project_code))).first():
        raise HTTPException(409, f"project_code {body.project_code} already exists")
    row = E.Project(**body.model_dump())
    db.add(row)
    await db.flush()
    row = await get_orm_project(db, str(row.id))
    await recompute_project(db, row)
    await audit(db, user, "CREATE", "project", row.id, {"project_code": row.project_code})
    await db.commit()
    return {"id": str(row.id), "project_code": row.project_code}


@router.get("/{ident}")
async def get_project(ident: str, db: SessionDep, user: CurrentUser):
    row = await _proj(db, ident)
    d = to_domain(row)
    today = date.today()
    out = _out(row, today)
    out.update(description=row.description, department=row.department, district=row.district,
               cost=cost_metrics(d).__dict__, schedule=schedule_metrics(d, today).__dict__,
               progress=progress_metrics(d, today).__dict__)
    return out


@router.patch("/{ident}")
async def patch_project(ident: str, body: ProjectPatch, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    row = await _proj(db, ident)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None and not can_transition(row.status, data["status"]):
        raise HTTPException(409, f"status transition {row.status.value} -> {data['status'].value} is not allowed")
    for k, v in data.items():
        setattr(row, k, v)
    await audit(db, user, "UPDATE", "project", row.id, {k: str(v) for k, v in data.items()})
    await db.flush()
    row = await get_orm_project(db, str(row.id))
    await recompute_project(db, row)
    await db.commit()
    return {"ok": True}


@router.delete("/{ident}", status_code=204)
async def delete_project(ident: str, db: SessionDep, user=Depends(require(E.Role.SUPER_ADMIN, E.Role.ADMIN))):
    row = await _proj(db, ident)
    await audit(db, user, "DELETE", "project", row.id, {"project_code": row.project_code})
    await db.delete(row)
    await db.commit()


# ---- snapshots
@router.get("/{ident}/snapshots")
async def snapshots(ident: str, db: SessionDep, user: CurrentUser):
    row = await _proj(db, ident)
    return [{"snapshot_month": s.snapshot_month.isoformat(), "physical_progress_pct": s.physical_progress_pct,
             "financial_progress_pct": s.financial_progress_pct, "cumulative_expenditure_crore": s.cumulative_expenditure_crore,
             "revised_cost_crore": s.revised_cost_crore, "revised_end_date": s.revised_end_date.isoformat() if s.revised_end_date else None,
             "status": s.status.value if s.status else None, "source": s.source, "origin": s.origin.value} for s in row.snapshots]


@router.post("/{ident}/snapshots", status_code=201)
async def add_snapshot(ident: str, body: SnapshotIn, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    row = await _proj(db, ident)
    month = body.snapshot_month.replace(day=1)
    cur = next((s for s in row.snapshots if s.snapshot_month == month), None)
    vals = body.model_dump(exclude={"snapshot_month"})
    if cur is None:
        row.snapshots.append(E.ProjectSnapshot(snapshot_month=month, origin=DataOrigin.USER_UPLOADED, **vals))
    else:
        for k, v in vals.items():
            setattr(cur, k, v)
    # keep latest values on the master row when this is the newest snapshot
    if all(month >= s.snapshot_month for s in row.snapshots):
        for k in ("physical_progress_pct", "financial_progress_pct", "cumulative_expenditure_crore", "revised_cost_crore", "revised_end_date"):
            if vals.get(k) is not None:
                setattr(row, k, vals[k])
    await audit(db, user, "ADD_SNAPSHOT", "project", row.id, {"month": month.isoformat()})
    await db.flush()
    row = await get_orm_project(db, str(row.id))
    r = await recompute_project(db, row)
    await db.commit()
    return {"risk": r["score"], "band": r["band"]}


# ---- milestones
@router.get("/{ident}/milestones")
async def milestones(ident: str, db: SessionDep, user: CurrentUser):
    row = await _proj(db, ident)
    today = date.today()
    out = []
    for m, dm in zip(row.milestones, to_domain(row).milestones):
        out.append({"id": str(m.id), "name": m.name, "planned_start": m.planned_start, "planned_end": m.planned_end,
                    "actual_start": m.actual_start, "actual_end": m.actual_end, "completion_pct": m.completion_pct,
                    "depends_on": m.depends_on, "delay_days": dm.delay_days(today), "status": dm.status(today)})
    return out


@router.post("/{ident}/milestones", status_code=201)
async def add_milestone(ident: str, body: MilestoneIn, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    row = await _proj(db, ident)
    row.milestones.append(E.ProjectMilestone(**body.model_dump()))
    await audit(db, user, "ADD_MILESTONE", "project", row.id, {"name": body.name})
    await db.flush()
    await recompute_project(db, await get_orm_project(db, str(row.id)))
    await db.commit()
    return {"ok": True}


# ---- issues
@router.get("/{ident}/issues")
async def issues(ident: str, db: SessionDep, user: CurrentUser):
    row = await _proj(db, ident)
    return [{"id": str(i.id), "issue_type": i.issue_type.value, "description": i.description, "severity": i.severity.value,
             "status": i.status.value, "reported_date": i.reported_date, "expected_resolution_date": i.expected_resolution_date,
             "actual_resolution_date": i.actual_resolution_date, "owner": i.owner, "impact": i.impact} for i in row.issues]


@router.post("/{ident}/issues", status_code=201)
async def add_issue(ident: str, body: IssueIn, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    row = await _proj(db, ident)
    row.issues.append(E.ProjectIssue(**body.model_dump()))
    await audit(db, user, "ADD_ISSUE", "project", row.id, {"type": body.issue_type.value})
    await db.flush()
    await recompute_project(db, await get_orm_project(db, str(row.id)))
    await db.commit()
    return {"ok": True}


@router.patch("/{ident}/issues/{issue_id}")
async def update_issue(ident: str, issue_id: str, body: IssueIn, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    row = await _proj(db, ident)
    it = next((i for i in row.issues if str(i.id) == issue_id), None)
    if it is None:
        raise HTTPException(404, "Issue not found")
    for k, v in body.model_dump().items():
        setattr(it, k, v)
    await audit(db, user, "UPDATE_ISSUE", "project", row.id, {"issue": issue_id})
    await db.flush()
    await recompute_project(db, await get_orm_project(db, str(row.id)))
    await db.commit()
    return {"ok": True}


# ---- risk / forecast / prediction / scenarios / actions
@router.get("/{ident}/risk")
async def risk(ident: str, db: SessionDep, user: CurrentUser):
    row = await _proj(db, ident)
    from app.risk.engine import compute_risk
    d = to_domain(row)
    cfg = risk_config()
    cur = compute_risk(d, date.today(), cfg).to_dict()
    return {"current": cur, "history": risk_history(d, cfg), "band_definition": "0-30 STABLE, 31-60 WATCH, 61-80 WARNING, 81-100 CRITICAL",
            "disclaimer": "Weights are configurable engineering assumptions, not validated government weights."}


@router.get("/{ident}/forecast")
async def forecast(ident: str, db: SessionDep, user: CurrentUser):
    d = to_domain(await _proj(db, ident))
    model = load_model(settings.MODEL_PATH)
    return {"forecast": forecast_completion(d, date.today()).to_dict(), "delay_prediction": predict(d, date.today(), model),
            "note": "PRAGATI predicted dates are model outputs and are distinct from the official revised completion date."}


@router.post("/{ident}/scenarios")
async def scenario(ident: str, body: ScenarioIn, db: SessionDep, user=Depends(require(*ANALYSIS_ROLES))):
    row = await _proj(db, ident)
    adj = ScenarioAdjustments(**body.model_dump(exclude={"name", "save", "resolve_issue_ids"}), resolve_issue_ids=tuple(body.resolve_issue_ids))
    res = run_scenario(to_domain(row), adj, date.today(), risk_config())
    if body.save:
        db.add(E.Scenario(project_id=row.id, name=body.name, adjustments=body.model_dump(exclude={"save"}), result=res, created_by=user.id))
        await audit(db, user, "SAVE_SCENARIO", "project", row.id, {"name": body.name})
        await db.commit()
    return res


@router.get("/{ident}/scenarios")
async def list_scenarios(ident: str, db: SessionDep, user: CurrentUser):
    row = await _proj(db, ident)
    rs = (await db.execute(select(E.Scenario).where(E.Scenario.project_id == row.id).order_by(E.Scenario.created_at.desc()))).scalars().all()
    return [{"id": str(s.id), "name": s.name, "created_at": s.created_at, "adjustments": s.adjustments, "result": s.result} for s in rs]


@router.get("/{ident}/actions")
async def project_actions(ident: str, db: SessionDep, user: CurrentUser):
    row = await _proj(db, ident)
    rs = (await db.execute(select(E.ActionItem).where(E.ActionItem.project_id == row.id).order_by(E.ActionItem.due_date))).scalars().all()
    return [_action(a, row.project_code) for a in rs]


def _action(a: E.ActionItem, code: str) -> dict:
    return {"id": str(a.id), "project_code": code, "title": a.title, "description": a.description, "owner": a.owner,
            "priority": a.priority.value, "due_date": a.due_date, "status": a.status.value, "source": a.source, "created_at": a.created_at}


@router.post("/{ident}/actions", status_code=201)
async def create_action(ident: str, body: ActionIn, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    row = await _proj(db, ident)
    a = E.ActionItem(project_id=row.id, created_by=user.id, **body.model_dump())
    db.add(a)
    await audit(db, user, "CREATE_ACTION", "project", row.id, {"title": body.title})
    await db.commit()
    return _action(a, row.project_code)
