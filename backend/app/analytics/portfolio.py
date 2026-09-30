"""Portfolio-level aggregation over domain Projects. All numbers derive from supplied data; None-safe."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import mean
from typing import Callable, Iterable, Optional

from app.analytics.metrics import cost_metrics, progress_metrics, schedule_metrics
from app.domain.types import DataOrigin, Project, ProjectStatus, RiskBand
from app.risk.engine import RiskConfig, compute_risk

# Buckets are (label, predicate). First match wins; None -> "Unknown".
DELAY_BUCKETS = [("On schedule", lambda v: v <= 0), ("1-90 d", lambda v: v <= 90),
                 ("91-365 d", lambda v: v <= 365), (">365 d", lambda v: True)]
OVERRUN_BUCKETS = [("<=0%", lambda v: v <= 0), ("0-10%", lambda v: v <= 10),
                   ("10-25%", lambda v: v <= 25), (">25%", lambda v: True)]
PROGRESS_BUCKETS = [("0-25%", lambda v: v < 25), ("25-50%", lambda v: v < 50),
                    ("50-75%", lambda v: v < 75), ("75-100%", lambda v: True)]


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 2) if xs else None


def _sum(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs), 2) if xs else None


def enrich(p: Project, as_of: date, cfg: Optional[RiskConfig] = None) -> dict:
    """One flat row per project with every derived metric; used by dashboard, radar, copilot, reports."""
    c, s, g = cost_metrics(p), schedule_metrics(p, as_of), progress_metrics(p, as_of)
    r = compute_risk(p, as_of, cfg)
    return {
        "project_code": p.project_code, "project_name": p.project_name, "sector": p.sector,
        "line_ministry": p.line_ministry, "implementing_agency": p.implementing_agency, "state": p.state,
        "status": p.status.value, "origin": p.origin.value,
        "original_cost_crore": p.original_cost_crore, "revised_cost_crore": p.revised_cost_crore,
        "cumulative_expenditure_crore": p.cumulative_expenditure_crore,
        "physical_progress_pct": p.physical_progress_pct, "financial_progress_pct": g.financial_progress_pct,
        "cost_overrun_amount": c.cost_overrun_amount, "cost_overrun_pct": c.cost_overrun_pct,
        "expenditure_ratio_pct": c.expenditure_ratio_pct,
        "cost_progress_imbalance_pts": g.cost_progress_imbalance_pts, "imbalance_flag": g.imbalance_flag,
        "schedule_delay_days": s.schedule_delay_days, "revised_slip_days": s.revised_slip_days,
        "overdue_days": s.overdue_days, "days_remaining": s.days_remaining,
        "deadline_proximity": s.deadline_proximity, "progress_velocity": g.progress_velocity_pts_per_month,
        "is_stagnant": g.is_stagnant, "risk_score": r.score, "risk_band": r.band.value,
        "assessed_weight_pct": r.assessed_weight_pct, "latitude": p.latitude, "longitude": p.longitude,
        "open_issues": sum(1 for i in p.issues if i.is_open),
        "critical_issues": sum(1 for i in p.issues if i.is_open and i.severity.value == "CRITICAL"),
        "original_end_date": p.original_end_date.isoformat() if p.original_end_date else None,
        "revised_end_date": p.revised_end_date.isoformat() if p.revised_end_date else None,
        "snapshot_count": len(p.snapshots),
    }


def _bucket(v, buckets):
    if v is None:
        return "Unknown"
    for label, pred in buckets:
        if pred(v):
            return label
    return "Unknown"


def _dist(vals, buckets):
    c = Counter(_bucket(v, buckets) for v in vals)
    labels = [b[0] for b in buckets]
    out = [{"bucket": k, "count": c.get(k, 0)} for k in labels]
    if c.get("Unknown"):
        out.append({"bucket": "Unknown", "count": c["Unknown"]})
    return out


def group_by(rows: list, key: str) -> list:
    g = defaultdict(list)
    for r in rows:
        g[r.get(key) or "Unspecified"].append(r)
    out = []
    for k, rs in g.items():
        out.append({"key": k, "projects": len(rs), "original_cost_crore": _sum(r["original_cost_crore"] for r in rs),
                    "revised_cost_crore": _sum(r["revised_cost_crore"] for r in rs),
                    "expenditure_crore": _sum(r["cumulative_expenditure_crore"] for r in rs),
                    "avg_risk": _avg(r["risk_score"] for r in rs), "avg_progress": _avg(r["physical_progress_pct"] for r in rs),
                    "avg_delay_days": _avg(r["schedule_delay_days"] for r in rs),
                    "avg_cost_overrun_pct": _avg(r["cost_overrun_pct"] for r in rs),
                    "critical": sum(1 for r in rs if r["risk_band"] == "CRITICAL")})
    return sorted(out, key=lambda x: (-x["projects"], x["key"]))


def dashboard(projects: Iterable[Project], as_of: date, cfg: Optional[RiskConfig] = None) -> dict:
    projects = list(projects)
    rows = [enrich(p, as_of, cfg) for p in projects]
    active = [r for r in rows if r["status"] not in ("COMPLETED", "CANCELLED")]
    bands = Counter(r["risk_band"] for r in active)
    origins = Counter(r["origin"] for r in rows)
    return {
        "as_of": as_of.isoformat(),
        "demo_data_present": origins.get("SYNTHETIC_DEMO", 0) > 0,
        "data_origins": dict(origins),
        "kpis": {
            "total_projects": len(rows),
            "projects_at_risk": bands["WARNING"] + bands["CRITICAL"],
            "critical_projects": bands["CRITICAL"],
            "delayed_projects": sum(1 for r in active if (r["schedule_delay_days"] or 0) > 0),
            "projects_near_completion": sum(1 for r in active if (r["physical_progress_pct"] or 0) >= 90),
            "total_original_cost_crore": _sum(r["original_cost_crore"] for r in rows),
            "total_revised_cost_crore": _sum(r["revised_cost_crore"] for r in rows),
            "total_expenditure_crore": _sum(r["cumulative_expenditure_crore"] for r in rows),
            "avg_physical_progress_pct": _avg(r["physical_progress_pct"] for r in rows),
            "avg_risk_score": _avg(r["risk_score"] for r in active),
        },
        "by_sector": group_by(rows, "sector"), "by_ministry": group_by(rows, "line_ministry"),
        "by_state": group_by(rows, "state"),
        "risk_distribution": [{"bucket": b, "count": bands.get(b, 0)} for b in ("STABLE", "WATCH", "WARNING", "CRITICAL")],
        "progress_distribution": _dist([r["physical_progress_pct"] for r in rows], PROGRESS_BUCKETS),
        "cost_overrun_distribution": _dist([r["cost_overrun_pct"] for r in rows], OVERRUN_BUCKETS),
        "schedule_delay_distribution": _dist([r["schedule_delay_days"] for r in rows], DELAY_BUCKETS),
    }


def bottlenecks(projects: Iterable[Project], as_of: date, cfg: Optional[RiskConfig] = None) -> list:
    """Aggregate open issues by category using only issue records that exist in the data."""
    projects = list(projects)
    rows = {p.project_code: enrich(p, as_of, cfg) for p in projects}
    agg = defaultdict(lambda: {"codes": set(), "issues": 0, "critical": 0})
    for p in projects:
        for i in p.issues:
            if not i.is_open:
                continue
            a = agg[i.issue_type.value]
            a["codes"].add(p.project_code); a["issues"] += 1
            a["critical"] += i.severity.value == "CRITICAL"
    out = []
    for k, a in agg.items():
        rs = [rows[c] for c in a["codes"]]
        out.append({"category": k, "projects_affected": len(rs), "open_issues": a["issues"], "critical_issues": a["critical"],
                    "avg_delay_days": _avg(r["schedule_delay_days"] for r in rs), "avg_risk": _avg(r["risk_score"] for r in rs),
                    "affected_project_value_crore": _sum(r["revised_cost_crore"] if r["revised_cost_crore"] is not None
                                                          else r["original_cost_crore"] for r in rs)})
    return sorted(out, key=lambda x: (-x["projects_affected"], x["category"]))


def data_quality(projects: Iterable[Project], as_of: date) -> dict:
    projects = list(projects)
    n = len(projects)
    fields = ["original_cost_crore", "revised_cost_crore", "cumulative_expenditure_crore", "start_date", "original_end_date",
              "revised_end_date", "physical_progress_pct", "sector", "line_ministry", "state"]
    missing = {f: sum(1 for p in projects if getattr(p, f) in (None, "")) for f in fields}
    codes = Counter(p.project_code for p in projects)
    inv_dates = sum(1 for p in projects if p.start_date and p.original_end_date and p.original_end_date < p.start_date)
    inv_costs = sum(1 for p in projects if any((getattr(p, k) is not None and getattr(p, k) < 0) for k in
                    ("original_cost_crore", "revised_cost_crore", "cumulative_expenditure_crore")))
    inv_prog = sum(1 for p in projects if p.physical_progress_pct is not None and not 0 <= p.physical_progress_pct <= 100)
    no_snap = sum(1 for p in projects if len(p.snapshots) < 2)
    cells = n * len(fields)
    filled = cells - sum(missing.values())
    return {"total_records": n, "missing_values_by_field": missing,
            "duplicate_project_codes": sum(1 for c, k in codes.items() if k > 1),
            "invalid_dates": inv_dates, "invalid_costs": inv_costs, "invalid_progress_values": inv_prog,
            "missing_project_codes": sum(1 for p in projects if not p.project_code),
            "projects_with_fewer_than_2_snapshots": no_snap,
            "completeness_score_pct": round(filled / cells * 100, 1) if cells else None,
            "definition": "share of populated cells across the tracked key fields"}
