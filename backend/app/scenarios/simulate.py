"""What-if simulation. Outputs are simulations, NOT official forecasts."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Optional

from app.domain.types import IssueStatus, Project
from app.forecasting.forecast import forecast_completion
from app.risk.engine import RiskConfig, compute_risk

LABEL = "SIMULATION — not an official government forecast"


@dataclass
class ScenarioAdjustments:
    progress_increase_pts: float = 0.0
    expenditure_increase_pct: float = 0.0
    revised_cost_increase_pct: float = 0.0
    milestone_delay_days: int = 0
    milestone_name: Optional[str] = None       # None -> all not-yet-complete milestones
    resolve_issue_ids: tuple = ()              # issue ids (or indexes as str) to mark resolved
    resolve_all_critical: bool = False
    completion_slip_days: int = 0
    recovery_days_assumed: int = 0             # user-supplied assumption: days recovered if issues resolve


def _apply(p: Project, adj: ScenarioAdjustments, as_of: date):
    notes = []
    q = p
    if adj.progress_increase_pts:
        cur = q.physical_progress_pct if q.physical_progress_pct is not None else 0.0
        new = min(100.0, cur + adj.progress_increase_pts)
        # Apply the uplift to the latest reported snapshot (same month) so observed velocity reflects the
        # assumed faster progress; appending a later-dated snapshot would artificially dilute velocity.
        ss = sorted(q.snapshots, key=lambda x: x.snapshot_month)
        if ss and ss[-1].physical_progress_pct is not None:
            ss[-1] = replace(ss[-1], physical_progress_pct=min(100.0, ss[-1].physical_progress_pct + adj.progress_increase_pts))
        q = q.with_(physical_progress_pct=new, snapshots=tuple(ss))
        notes.append(f"physical progress +{adj.progress_increase_pts:g} pts -> {new:.1f}%")
    if adj.expenditure_increase_pct and q.cumulative_expenditure_crore is not None:
        q = q.with_(cumulative_expenditure_crore=q.cumulative_expenditure_crore * (1 + adj.expenditure_increase_pct / 100))
        notes.append(f"expenditure +{adj.expenditure_increase_pct:g}%")
    if adj.revised_cost_increase_pct and q.revised_cost_crore is not None:
        q = q.with_(revised_cost_crore=q.revised_cost_crore * (1 + adj.revised_cost_increase_pct / 100))
        notes.append(f"revised cost +{adj.revised_cost_increase_pct:g}%")
    if adj.milestone_delay_days:
        out = []
        for m in q.milestones:
            hit = (adj.milestone_name is None and not m.is_complete) or (adj.milestone_name == m.name)
            if hit and m.planned_end is not None:
                out.append(replace(m, actual_end=m.planned_end + timedelta(days=adj.milestone_delay_days),
                                   completion_pct=100.0))
            else:
                out.append(m)
        q = q.with_(milestones=tuple(out))
        notes.append(f"milestone(s) projected {adj.milestone_delay_days} d late")
    if adj.resolve_issue_ids or adj.resolve_all_critical:
        ids = {str(i) for i in adj.resolve_issue_ids}
        new_issues = []
        n = 0
        for idx, i in enumerate(q.issues):
            hit = i.is_open and (str(i.id) in ids or str(idx) in ids or
                                 (adj.resolve_all_critical and i.severity.value == "CRITICAL"))
            if hit:
                n += 1
                new_issues.append(replace(i, status=IssueStatus.RESOLVED, actual_resolution_date=as_of))
            else:
                new_issues.append(i)
        q = q.with_(issues=tuple(new_issues))
        notes.append(f"{n} issue(s) resolved")
    if adj.completion_slip_days:
        base = q.revised_end_date or q.original_end_date
        if base is not None:
            q = q.with_(revised_end_date=base + timedelta(days=adj.completion_slip_days))
            notes.append(f"completion slips {adj.completion_slip_days} d")
    return q, notes


def run_scenario(p: Project, adj: ScenarioAdjustments, as_of: Optional[date] = None,
                 config: Optional[RiskConfig] = None) -> dict:
    as_of = as_of or date.today()
    cfg = config or RiskConfig()
    base_r = compute_risk(p, as_of, cfg)
    base_f = forecast_completion(p, as_of)
    q, notes = _apply(p, adj, as_of)
    rec = adj.recovery_days_assumed if (adj.resolve_issue_ids or adj.resolve_all_critical) else 0
    new_r = compute_risk(q, as_of, cfg)
    new_f = forecast_completion(q, as_of, recovery_days=rec)
    warnings = []
    if (adj.resolve_issue_ids or adj.resolve_all_critical) and cfg.weights.get("issues", 0) == 0:
        warnings.append("Issue component has weight 0 in the current risk configuration, so resolving issues does "
                        "not change the risk score. Configure RISK_WEIGHTS_JSON to include issues, or supply "
                        "recovery_days_assumed to model schedule recovery.")
    d_delay = None
    if base_f.estimated_delay_days is not None and new_f.estimated_delay_days is not None:
        d_delay = new_f.estimated_delay_days - base_f.estimated_delay_days
    return {
        "label": LABEL, "origin": "PREDICTED", "as_of": as_of.isoformat(),
        "assumptions": notes, "warnings": warnings,
        "baseline": {"risk_score": base_r.score, "risk_band": base_r.band.value,
                     "forecast": base_f.to_dict()},
        "projected": {"risk_score": new_r.score, "risk_band": new_r.band.value,
                      "forecast": new_f.to_dict(), "contributors": [c.__dict__ for c in new_r.contributors]},
        "delta": {"risk_score": round(new_r.score - base_r.score, 1), "forecast_delay_days": d_delay},
    }
