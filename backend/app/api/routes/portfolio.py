"""Portfolio-level read endpoints: dashboard, analytics, risk radar, bottlenecks, map, data quality, alerts, actions."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.analytics.portfolio import bottlenecks, dashboard, data_quality, enrich, group_by
from app.api.deps import WRITE_ROLES, CurrentUser, SessionDep, audit, require
from app.domain.types import RiskBand
from app.models import entities as E
from app.services.analysis import recompute_all, risk_config
from app.services.repository import load_orm_projects, load_projects

router = APIRouter(tags=["portfolio"])


def _filters(sector=None, line_ministry=None, implementing_agency=None, state=None, status=None, origin=None):
    return {k: v for k, v in dict(sector=sector, line_ministry=line_ministry, implementing_agency=implementing_agency,
                                  state=state, status=status, origin=origin).items() if v}


@router.get("/dashboard")
async def get_dashboard(db: SessionDep, user: CurrentUser, sector: Optional[str] = None, state: Optional[str] = None):
    ps = await load_projects(db, **_filters(sector=sector, state=state))
    return dashboard(ps, date.today(), risk_config())


@router.get("/analytics")
async def analytics(db: SessionDep, user: CurrentUser, sector: Optional[str] = None, state: Optional[str] = None):
    ps = await load_projects(db, **_filters(sector=sector, state=state))
    today, cfg = date.today(), risk_config()
    rows = [enrich(p, today, cfg) for p in ps]
    active = [r for r in rows if r["status"] not in ("COMPLETED", "CANCELLED")]
    d = dashboard(ps, today, cfg)

    def hist(key, n=10):
        return sorted([{"project_code": r["project_code"], key: r[key]} for r in rows if r[key] is not None], key=lambda x: -x[key])[:n]

    # portfolio risk trend: average of reconstructed history per month
    from app.risk.engine import risk_history
    from collections import defaultdict
    trend = defaultdict(list)
    for p in ps:
        if p.is_terminal:
            continue
        for h in risk_history(p, cfg):
            trend[h["month"]].append(h["score"])
    risk_trend = [{"month": m, "avg_risk": round(sum(v) / len(v), 2), "projects": len(v)} for m, v in sorted(trend.items())]
    return {
        "cost": {"by_sector": d["by_sector"], "distribution": d["cost_overrun_distribution"], "top_overruns": hist("cost_overrun_pct")},
        "schedule": {"distribution": d["schedule_delay_distribution"],
                     "avg_delay_days": (sum(r["schedule_delay_days"] for r in active if r["schedule_delay_days"] is not None) / max(1, sum(1 for r in active if r["schedule_delay_days"] is not None))),
                     "nearing_deadline": [r for r in active if r["days_remaining"] is not None and 0 <= r["days_remaining"] <= 180][:25]},
        "progress": {"distribution": d["progress_distribution"], "by_sector": [{"key": g["key"], "avg_progress": g["avg_progress"]} for g in d["by_sector"]],
                     "stagnant_projects": [r["project_code"] for r in active if r["is_stagnant"]]},
        "risk": {"distribution": d["risk_distribution"], "by_sector": [{"key": g["key"], "avg_risk": g["avg_risk"]} for g in d["by_sector"]],
                 "by_ministry": [{"key": g["key"], "avg_risk": g["avg_risk"]} for g in d["by_ministry"]], "trend": risk_trend},
        "bottlenecks": bottlenecks(ps, today, cfg), "demo_data_present": d["demo_data_present"],
    }


@router.get("/risk")
async def risk_radar(db: SessionDep, user: CurrentUser, band: Optional[RiskBand] = None, sector: Optional[str] = None,
                     line_ministry: Optional[str] = None, implementing_agency: Optional[str] = None, state: Optional[str] = None,
                     min_cost: Optional[float] = Query(None, ge=0), min_delay_days: Optional[int] = Query(None, ge=0),
                     max_progress: Optional[float] = Query(None, ge=0, le=100)):
    ps = await load_projects(db, **_filters(sector=sector, line_ministry=line_ministry, implementing_agency=implementing_agency, state=state))
    rows = [enrich(p, date.today(), risk_config()) for p in ps]
    rows = [r for r in rows if r["status"] not in ("COMPLETED", "CANCELLED")]
    if band:
        rows = [r for r in rows if r["risk_band"] == band.value]
    if min_cost is not None:
        rows = [r for r in rows if (r["revised_cost_crore"] or r["original_cost_crore"] or 0) >= min_cost]
    if min_delay_days is not None:
        rows = [r for r in rows if (r["schedule_delay_days"] or 0) >= min_delay_days]
    if max_progress is not None:
        rows = [r for r in rows if r["physical_progress_pct"] is not None and r["physical_progress_pct"] <= max_progress]
    rows.sort(key=lambda r: -r["risk_score"])
    groups = {b.value: [r for r in rows if r["risk_band"] == b.value] for b in (RiskBand.CRITICAL, RiskBand.WARNING, RiskBand.WATCH, RiskBand.STABLE)}
    return {"counts": {k: len(v) for k, v in groups.items()}, "projects": rows[:500], "truncated": len(rows) > 500}


@router.get("/bottlenecks")
async def get_bottlenecks(db: SessionDep, user: CurrentUser):
    return {"items": bottlenecks(await load_projects(db), date.today(), risk_config())}


@router.get("/map")
async def project_map(db: SessionDep, user: CurrentUser, sector: Optional[str] = None, state: Optional[str] = None,
                      risk_level: Optional[RiskBand] = None, status: Optional[str] = None, min_cost: Optional[float] = None,
                      max_cost: Optional[float] = None, min_progress: Optional[float] = None, max_progress: Optional[float] = None):
    ps = await load_projects(db, **_filters(sector=sector, state=state, status=status))
    feats, missing = [], 0
    for p in ps:
        r = enrich(p, date.today(), risk_config())
        if r["latitude"] is None or r["longitude"] is None:
            missing += 1
            continue
        cost = r["revised_cost_crore"] if r["revised_cost_crore"] is not None else r["original_cost_crore"]
        if risk_level and r["risk_band"] != risk_level.value:
            continue
        if min_cost is not None and (cost is None or cost < min_cost) or max_cost is not None and (cost is None or cost > max_cost):
            continue
        pr = r["physical_progress_pct"]
        if min_progress is not None and (pr is None or pr < min_progress) or max_progress is not None and (pr is None or pr > max_progress):
            continue
        feats.append({"project_code": r["project_code"], "project_name": r["project_name"], "sector": r["sector"], "lat": r["latitude"],
                      "lng": r["longitude"], "progress": pr, "risk_score": r["risk_score"], "risk_band": r["risk_band"], "cost_crore": cost,
                      "status": r["status"], "origin": r["origin"]})
    return {"projects": feats, "excluded_without_coordinates": missing}


@router.get("/data-quality")
async def get_data_quality(db: SessionDep, user: CurrentUser):
    return data_quality(await load_projects(db), date.today())


@router.post("/risk/recompute")
async def recompute(db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    rows = await load_orm_projects(db)
    n = await recompute_all(db, rows)
    await audit(db, user, "RECOMPUTE_RISK", "portfolio", None, {"projects": n})
    await db.commit()
    return {"recomputed": n}


# ---- alerts
@router.get("/alerts")
async def alerts(db: SessionDep, user: CurrentUser, unacknowledged: bool = True, limit: int = Query(100, le=500)):
    q = select(E.Alert, E.Project.project_code).join(E.Project, E.Project.id == E.Alert.project_id)
    if unacknowledged:
        q = q.where(E.Alert.acknowledged.is_(False))
    rows = (await db.execute(q.order_by(E.Alert.created_at.desc()).limit(limit))).all()
    return [{"id": str(a.id), "project_code": c, "kind": a.kind, "severity": a.severity.value, "message": a.message,
             "acknowledged": a.acknowledged, "created_at": a.created_at} for a, c in rows]


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, db: SessionDep, user=Depends(require(*WRITE_ROLES, E.Role.ANALYST, E.Role.REVIEWER))):
    a = (await db.execute(select(E.Alert).where(E.Alert.id == alert_id))).scalars().first()
    if a is None:
        raise HTTPException(404, "Alert not found")
    a.acknowledged = True
    await audit(db, user, "ACK_ALERT", "alert", a.id)
    await db.commit()
    return {"ok": True}


# ---- actions (portfolio view)
class ActionPatch(BaseModel):
    status: Optional[E.ActionStatus] = None
    owner: Optional[str] = None
    priority: Optional[E.Priority] = None


@router.get("/actions")
async def all_actions(db: SessionDep, user: CurrentUser, status: Optional[E.ActionStatus] = None):
    q = select(E.ActionItem, E.Project.project_code).join(E.Project, E.Project.id == E.ActionItem.project_id)
    if status:
        q = q.where(E.ActionItem.status == status)
    rows = (await db.execute(q.order_by(E.ActionItem.due_date.asc().nulls_last()).limit(500))).all()
    return [{"id": str(a.id), "project_code": c, "title": a.title, "owner": a.owner, "priority": a.priority.value,
             "due_date": a.due_date, "status": a.status.value, "source": a.source} for a, c in rows]


@router.patch("/actions/{action_id}")
async def patch_action(action_id: str, body: ActionPatch, db: SessionDep, user=Depends(require(*WRITE_ROLES))):
    a = (await db.execute(select(E.ActionItem).where(E.ActionItem.id == action_id))).scalars().first()
    if a is None:
        raise HTTPException(404, "Action not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    await audit(db, user, "UPDATE_ACTION", "action", a.id, body.model_dump(exclude_unset=True, mode="json"))
    await db.commit()
    return {"ok": True}


@router.get("/milestones")
async def portfolio_milestones(db: SessionDep, user: CurrentUser, scope: str = Query("overdue", pattern="^(overdue|upcoming|delayed|all)$"),
                               upcoming_days: int = Query(90, ge=1, le=730)):
    """Cross-project milestone monitor derived from recorded milestones only."""
    today = date.today()
    out = []
    for p in await load_projects(db):
        if p.is_terminal:
            continue
        for m in p.milestones:
            st, dd = m.status(today), m.delay_days(today)
            if scope == "overdue" and not (st == "DELAYED"):
                continue
            if scope == "delayed" and dd <= 0:
                continue
            if scope == "upcoming" and not (not m.is_complete and m.planned_end and 0 <= (m.planned_end - today).days <= upcoming_days):
                continue
            out.append({"project_code": p.project_code, "project_name": p.project_name, "milestone": m.name, "planned_end": m.planned_end,
                        "actual_end": m.actual_end, "completion_pct": m.completion_pct, "delay_days": dd, "status": st, "depends_on": m.depends_on})
    out.sort(key=lambda r: -r["delay_days"] if scope != "upcoming" else (r["planned_end"] or today))
    return {"items": out[:1000], "count": len(out)}


@router.get("/risk-config")
async def risk_configuration(user: CurrentUser):
    cfg = risk_config()
    return {"version": cfg.version, "weights_pct_normalised": cfg.normalised_weights(), "scales": cfg.scales,
            "bands": {"STABLE": "0-30", "WATCH": "31-60", "WARNING": "61-80", "CRITICAL": "81-100"},
            "disclaimer": "Initial engineering assumptions; configurable; not validated government weights."}
