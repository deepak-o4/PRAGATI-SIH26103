"""PRAGATI risk engine (transparent, rule-based, versioned).

Score = sum_i  weight_i * subscore_i   where each subscore is 0..100.

The default weights are *initial engineering assumptions*, not validated government weights.
They are configurable (``RiskConfig`` / env ``RISK_WEIGHTS_JSON``) and every result records the weights
used plus a version tag so a score can be reproduced later.

Components that cannot be assessed because data is missing contribute 0 and are reported as
``available=False``; ``assessed_weight_pct`` tells the reader how much of the weight was assessable.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from typing import Optional

from app.analytics.metrics import (cost_metrics, progress_metrics, required_velocity_pts_per_month,
                                   schedule_metrics)
from app.domain.types import (SEVERITY_WEIGHT, Issue, IssueStatus, Milestone, Project, ProjectStatus,
                              RiskBand, risk_band)

RISK_VERSION = "risk-v1.0"

DEFAULT_WEIGHTS = {
    "schedule": 25.0,
    "cost": 20.0,
    "progress": 25.0,
    "milestone": 15.0,
    "trend": 10.0,
    "data_quality": 5.0,
    "issues": 0.0,  # informational by default; raise via config to let issue severity drive score
}

# Sub-score scaling assumptions (also configurable)
DEFAULT_SCALES = {
    "schedule_pct_for_100": 40.0,     # 40% slip vs planned duration -> subscore 100
    "schedule_days_for_100": 365.0,   # fallback when planned duration unknown
    "cost_overrun_pct_for_100": 25.0,
    "progress_gap_pts_for_100": 40.0,
    "milestone_delay_days_for_full": 90.0,
    "issue_points_for_100": 4.0,      # sum of severity weights that saturates the issue subscore
}

LABELS = {
    "schedule": "Schedule Delay",
    "cost": "Cost Increase",
    "progress": "Progress Slippage",
    "milestone": "Milestone Delay",
    "trend": "Trend",
    "data_quality": "Data Quality",
    "issues": "Open Issues",
}


@dataclass(frozen=True)
class RiskConfig:
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    scales: dict = field(default_factory=lambda: dict(DEFAULT_SCALES))
    version: str = RISK_VERSION

    @staticmethod
    def from_env() -> "RiskConfig":
        raw = os.getenv("RISK_WEIGHTS_JSON")
        if not raw:
            return RiskConfig()
        data = json.loads(raw)
        w = dict(DEFAULT_WEIGHTS)
        for k, v in data.items():
            if k not in w:
                raise ValueError(f"unknown risk component: {k}")
            if v < 0:
                raise ValueError("risk weights must be non-negative")
            w[k] = float(v)
        if sum(w.values()) <= 0:
            raise ValueError("sum of risk weights must be positive")
        return RiskConfig(weights=w)

    def normalised_weights(self) -> dict:
        total = sum(self.weights.values())
        return {k: v / total * 100.0 for k, v in self.weights.items()}


@dataclass
class Contributor:
    key: str
    label: str
    weight_pct: float
    subscore: Optional[float]     # 0..100, None when unavailable
    points: float                 # weight * subscore / 100
    available: bool
    explanation: str


@dataclass
class RiskResult:
    project_code: str
    score: float                  # 0..100, one decimal
    band: RiskBand
    contributors: list
    assessed_weight_pct: float
    version: str
    weights: dict
    computed_at: str
    as_of: date
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_code": self.project_code, "score": self.score, "band": self.band.value,
            "contributors": [c.__dict__ for c in self.contributors],
            "assessed_weight_pct": self.assessed_weight_pct, "version": self.version,
            "weights": self.weights, "computed_at": self.computed_at, "as_of": self.as_of.isoformat(),
            "notes": self.notes,
        }


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ------------------------------------------------------------------ component scorers
def _schedule(p: Project, as_of: date, sc: dict):
    m = schedule_metrics(p, as_of)
    if m.schedule_delay_days is None:
        return None, "schedule dates missing"
    if m.schedule_delay_pct is not None:
        sub = _clip(m.schedule_delay_pct / sc["schedule_pct_for_100"] * 100)
        return sub, (f"{m.schedule_delay_days} d total slippage vs original baseline "
                     f"({m.schedule_delay_pct:.1f}% of planned duration; official revision "
                     f"{m.revised_slip_days} d, overdue {m.overdue_days} d)")
    sub = _clip(m.schedule_delay_days / sc["schedule_days_for_100"] * 100)
    return sub, f"{m.schedule_delay_days} d total slippage (planned duration unknown)"


def _cost(p: Project, as_of: date, sc: dict):
    m = cost_metrics(p)
    if m.cost_overrun_pct is None:
        return None, "; ".join(m.notes) or "cost data missing"
    sub = _clip(max(0.0, m.cost_overrun_pct) / sc["cost_overrun_pct_for_100"] * 100)
    return sub, f"revised cost is {m.cost_overrun_pct:+.1f}% vs original"


def _progress(p: Project, as_of: date, sc: dict):
    m = progress_metrics(p, as_of)
    if m.progress_gap_pts is None:
        return None, "progress or schedule data missing"
    if p.physical_progress_pct is not None and p.physical_progress_pct >= 100:
        return 0.0, "physically complete"
    sub = _clip(max(0.0, m.progress_gap_pts) / sc["progress_gap_pts_for_100"] * 100)
    return sub, (f"physical progress {m.physical_progress_pct:.1f}% vs {m.expected_progress_pct:.1f}% "
                 f"expected by linear plan ({m.progress_gap_pts:+.1f} pts behind)")


def _milestone(p: Project, as_of: date, sc: dict):
    ms = [m for m in p.milestones if m.planned_end is not None]
    if not ms:
        return None, "no milestones with planned dates"
    full = sc["milestone_delay_days_for_full"]
    tot_w = sum(m.weight for m in ms) or 1.0
    late = sum(m.weight * min(1.0, m.delay_days(as_of) / full) for m in ms)
    n_late = sum(1 for m in ms if m.delay_days(as_of) > 0)
    return _clip(late / tot_w * 100), f"{n_late} of {len(ms)} milestones late (weighted by days late, {full:.0f} d = full)"


def _trend(p: Project, as_of: date, sc: dict):
    m = progress_metrics(p, as_of)
    if m.progress_velocity_pts_per_month is None:
        return None, "fewer than two progress snapshots"
    if p.physical_progress_pct is not None and p.physical_progress_pct >= 100:
        return 0.0, "physically complete"
    subs, why = [], []
    if m.is_stagnant:
        s = _clip(60 + 10 * (m.stagnant_snapshots - 2))
        subs.append(s)
        why.append(f"progress flat for {m.stagnant_snapshots} consecutive reports")
    req = required_velocity_pts_per_month(p, as_of)
    if req is not None:
        if req == float("inf"):
            subs.append(100.0)
            why.append("deadline reached with work remaining")
        elif req > 0:
            ratio = m.progress_velocity_pts_per_month / req
            subs.append(_clip((1 - ratio) * 100))
            why.append(f"velocity {m.progress_velocity_pts_per_month:.2f} vs {req:.2f} pts/month required")
    if not subs:
        return 0.0, "velocity on/above requirement"
    return max(subs), "; ".join(why)


def _data_quality(p: Project, as_of: date, sc: dict):
    checks = {
        "original cost": p.original_cost_crore is not None,
        "revised cost": p.revised_cost_crore is not None,
        "expenditure": p.cumulative_expenditure_crore is not None,
        "start date": p.start_date is not None,
        "original end date": p.original_end_date is not None,
        "revised end date": p.revised_end_date is not None,
        "physical progress": p.physical_progress_pct is not None,
        "2+ snapshots": len(p.snapshots) >= 2,
    }
    missing = [k for k, ok in checks.items() if not ok]
    sub = len(missing) / len(checks) * 100
    return sub, ("all key fields present" if not missing else "missing: " + ", ".join(missing))


def _issues(p: Project, as_of: date, sc: dict):
    open_issues = [i for i in p.issues if i.is_open]
    total = sum(SEVERITY_WEIGHT[i.severity] for i in open_issues)
    sub = _clip(total / sc["issue_points_for_100"] * 100)
    return sub, f"{len(open_issues)} open issue(s), severity-weighted {total:.2f}"


_SCORERS = {"schedule": _schedule, "cost": _cost, "progress": _progress, "milestone": _milestone,
            "trend": _trend, "data_quality": _data_quality, "issues": _issues}


def compute_risk(p: Project, as_of: Optional[date] = None, config: Optional[RiskConfig] = None) -> RiskResult:
    as_of = as_of or date.today()
    cfg = config or RiskConfig()
    weights = cfg.normalised_weights()
    now = datetime.now(timezone.utc).isoformat()
    notes: list[str] = []

    if p.status in (ProjectStatus.COMPLETED, ProjectStatus.CANCELLED):
        notes.append(f"project is {p.status.value}; forward-looking risk not applicable")
        contribs = [Contributor(k, LABELS[k], weights[k], None, 0.0, False, "not applicable (terminal status)")
                    for k in weights]
        return RiskResult(p.project_code, 0.0, RiskBand.STABLE, contribs, 0.0, cfg.version, weights, now,
                          as_of, notes)

    contribs: list[Contributor] = []
    raw_total = 0.0
    assessed = 0.0
    for key, w in weights.items():
        sub, why = _SCORERS[key](p, as_of, cfg.scales)
        avail = sub is not None
        pts = (w * sub / 100.0) if avail else 0.0
        if avail:
            assessed += w
        raw_total += pts
        contribs.append(Contributor(key, LABELS[key], round(w, 2), None if sub is None else round(sub, 1),
                                    round(pts, 1), avail, why))
    score = round(min(100.0, raw_total), 1)
    if assessed < 60:
        notes.append("less than 60% of risk weight could be assessed; score is a lower bound")
    return RiskResult(p.project_code, score, risk_band(score), contribs, round(assessed, 1), cfg.version,
                      weights, now, as_of, notes)


# ------------------------------------------------------------------ historical reconstruction
def project_as_of(p: Project, month: date) -> Project:
    """Reconstruct project state at a snapshot month using only information available then."""
    snaps = [s for s in p.sorted_snapshots() if s.snapshot_month <= month]
    if not snaps:
        return p.with_(snapshots=())
    last = snaps[-1]
    cutoff = _month_end(month)

    def ms_asof(m: Milestone) -> Milestone:
        if m.actual_end is not None and m.actual_end > cutoff:
            return replace(m, actual_end=None, completion_pct=min(m.completion_pct, 99.0))
        if m.actual_start is not None and m.actual_start > cutoff:
            return replace(m, actual_start=None, completion_pct=0.0)
        return m

    def issue_asof(i: Issue):
        if i.reported_date is not None and i.reported_date > cutoff:
            return None
        if i.actual_resolution_date is not None and i.actual_resolution_date > cutoff:
            return replace(i, status=IssueStatus.OPEN, actual_resolution_date=None)
        return i

    issues = tuple(x for x in (issue_asof(i) for i in p.issues) if x is not None)
    return p.with_(
        physical_progress_pct=last.physical_progress_pct,
        financial_progress_pct=last.financial_progress_pct,
        cumulative_expenditure_crore=last.cumulative_expenditure_crore
        if last.cumulative_expenditure_crore is not None else p.cumulative_expenditure_crore,
        revised_cost_crore=last.revised_cost_crore if last.revised_cost_crore is not None else p.revised_cost_crore,
        revised_end_date=last.revised_end_date if last.revised_end_date is not None else p.revised_end_date,
        status=last.status or p.status,
        snapshots=tuple(snaps),
        milestones=tuple(ms_asof(m) for m in p.milestones),
        issues=issues,
    )


def _month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def risk_history(p: Project, config: Optional[RiskConfig] = None) -> list:
    """Risk score at each snapshot month (as-of month end). Returns [{month, score, band}]."""
    out = []
    for s in p.sorted_snapshots():
        view = project_as_of(p, s.snapshot_month)
        # Terminal status recorded later must not leak into earlier history
        if view.status in (ProjectStatus.COMPLETED, ProjectStatus.CANCELLED) and (s.physical_progress_pct or 0) < 100:
            view = view.with_(status=ProjectStatus.UNDER_CONSTRUCTION)
        r = compute_risk(view, _month_end(s.snapshot_month), config)
        out.append({"month": s.snapshot_month.isoformat(), "score": r.score, "band": r.band.value})
    return out
