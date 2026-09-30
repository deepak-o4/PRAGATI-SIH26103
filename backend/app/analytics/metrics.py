"""Project-level cost, schedule and progress analytics.

Design rules
* Never fabricate: when an input is missing/invalid the metric is ``None`` and a note explains why.
* Distinguish *official revised schedule slip*, *overdue beyond the revised date* and *forecast delay*
  (the latter lives in ``app.forecasting``).
* Expenditure-vs-progress imbalance is an analytical review indicator only. It says nothing about misuse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.domain.types import Project, ProjectStatus

# Engineering assumptions (configurable via app.core.settings at the API layer; defaults here).
IMBALANCE_REVIEW_THRESHOLD_PTS = 25.0
STAGNATION_EPSILON_PTS = 0.25
STAGNATION_MIN_SNAPSHOTS = 2


def _valid_cost(v: Optional[float]) -> Optional[float]:
    return v if v is not None and v >= 0 else None


# ----------------------------------------------------------------------------- cost
@dataclass
class CostMetrics:
    original_cost_crore: Optional[float]
    revised_cost_crore: Optional[float]
    cost_overrun_amount: Optional[float]
    cost_overrun_pct: Optional[float]
    revised_vs_original_ratio: Optional[float]
    expenditure_ratio_pct: Optional[float]      # expenditure / (revised or original cost) * 100
    expenditure_vs_progress_pts: Optional[float]  # expenditure ratio - physical progress
    notes: list = field(default_factory=list)


def cost_metrics(p: Project) -> CostMetrics:
    notes: list[str] = []
    orig = _valid_cost(p.original_cost_crore)
    rev = _valid_cost(p.revised_cost_crore)
    exp = _valid_cost(p.cumulative_expenditure_crore)
    if p.original_cost_crore is not None and orig is None:
        notes.append("original cost is negative/invalid")
    if p.revised_cost_crore is not None and rev is None:
        notes.append("revised cost is negative/invalid")
    if orig is None:
        notes.append("original cost missing")
    elif orig == 0:
        notes.append("original cost is zero; percentage metrics unavailable")
    if rev is None and orig is not None:
        notes.append("revised cost missing; overrun unavailable")

    amount = pct = ratio = None
    if orig is not None and rev is not None:
        amount = rev - orig
        if orig > 0:
            pct = amount / orig * 100.0
            ratio = rev / orig

    basis = rev if rev is not None else orig
    exp_ratio = None
    if exp is not None and basis is not None and basis > 0:
        exp_ratio = exp / basis * 100.0
    elif exp is not None:
        notes.append("no positive cost basis for expenditure ratio")

    exp_vs_prog = None
    if exp_ratio is not None and p.physical_progress_pct is not None:
        exp_vs_prog = exp_ratio - p.physical_progress_pct
    return CostMetrics(orig, rev, amount, pct, ratio, exp_ratio, exp_vs_prog, notes)


# ----------------------------------------------------------------------------- schedule
@dataclass
class ScheduleMetrics:
    planned_duration_days: Optional[int]
    current_duration_days: Optional[int]
    revised_slip_days: Optional[int]        # official: revised_end - original_end (>=0)
    overdue_days: Optional[int]             # historical: as_of - revised_end if still incomplete
    schedule_delay_days: Optional[int]      # revised_slip + overdue (total slippage vs original baseline)
    schedule_delay_pct: Optional[float]     # of planned duration
    days_remaining: Optional[int]           # revised_end - as_of (negative = overdue)
    deadline_proximity: Optional[str]       # OVERDUE / IMMINENT(<=90d) / NEAR(<=180d) / FAR / NA
    expected_progress_pct: Optional[float]  # linear time-based plan vs revised schedule
    notes: list = field(default_factory=list)


def _complete(p: Project) -> bool:
    return p.status == ProjectStatus.COMPLETED or (p.physical_progress_pct or 0) >= 100.0


def schedule_metrics(p: Project, as_of: date) -> ScheduleMetrics:
    notes: list[str] = []
    planned = current = slip = overdue = total = remaining = None
    pct = None
    prox = "NA"
    expected = None

    if p.start_date and p.original_end_date:
        if p.original_end_date < p.start_date:
            notes.append("original end date precedes start date")
        else:
            planned = (p.original_end_date - p.start_date).days
    else:
        notes.append("start/original end date missing; planned duration unavailable")
    if p.start_date:
        current = max(0, (as_of - p.start_date).days)

    eff_end = p.revised_end_date or p.original_end_date
    if p.revised_end_date and p.original_end_date:
        slip = max(0, (p.revised_end_date - p.original_end_date).days)
    elif p.original_end_date:
        slip = 0
        notes.append("revised end date missing; assuming no official revision")
    if eff_end is not None:
        remaining = (eff_end - as_of).days
        if not _complete(p) and p.status != ProjectStatus.CANCELLED:
            overdue = max(0, -remaining)
        else:
            overdue = 0
        if _complete(p):
            prox = "NA"
        elif remaining < 0:
            prox = "OVERDUE"
        elif remaining <= 90:
            prox = "IMMINENT"
        elif remaining <= 180:
            prox = "NEAR"
        else:
            prox = "FAR"
    if slip is not None:
        total = slip + (overdue or 0)
        if planned and planned > 0:
            pct = total / planned * 100.0

    if p.start_date and eff_end and eff_end > p.start_date:
        span = (eff_end - p.start_date).days
        expected = min(100.0, max(0.0, (as_of - p.start_date).days / span * 100.0))
    return ScheduleMetrics(planned, current, slip, overdue, total, pct, remaining, prox, expected, notes)


# ----------------------------------------------------------------------------- progress
@dataclass
class ProgressMetrics:
    physical_progress_pct: Optional[float]
    financial_progress_pct: Optional[float]
    progress_change_pts: Optional[float]        # latest snapshot - previous snapshot
    progress_velocity_pts_per_month: Optional[float]
    stagnant_snapshots: int                     # consecutive most-recent snapshots with ~no change
    is_stagnant: bool
    expected_progress_pct: Optional[float]
    progress_gap_pts: Optional[float]           # expected - physical (positive = behind plan)
    cost_progress_imbalance_pts: Optional[float]
    imbalance_flag: bool                        # analytical review indicator, NOT an accusation
    notes: list = field(default_factory=list)


def _months_between(a: date, b: date) -> float:
    return max((b - a).days, 0) / 30.4375


def progress_metrics(p: Project, as_of: date) -> ProgressMetrics:
    notes: list[str] = []
    snaps = [s for s in p.sorted_snapshots() if s.physical_progress_pct is not None]
    change = velocity = None
    if len(snaps) >= 2:
        a, b = snaps[-2], snaps[-1]
        change = b.physical_progress_pct - a.physical_progress_pct
        m = _months_between(a.snapshot_month, b.snapshot_month)
        velocity = change / m if m > 0 else None
    else:
        notes.append("fewer than two progress snapshots; velocity unavailable")

    stagnant = 0
    for i in range(len(snaps) - 1, 0, -1):
        if abs(snaps[i].physical_progress_pct - snaps[i - 1].physical_progress_pct) < STAGNATION_EPSILON_PTS:
            stagnant += 1
        else:
            break
    is_stagnant = stagnant >= STAGNATION_MIN_SNAPSHOTS and not _complete(p)

    sm = schedule_metrics(p, as_of)
    phys = p.physical_progress_pct
    gap = None
    if sm.expected_progress_pct is not None and phys is not None:
        gap = sm.expected_progress_pct - phys

    fin = p.financial_progress_pct
    if fin is None:
        fin = cost_metrics(p).expenditure_ratio_pct
        if fin is not None:
            notes.append("financial progress derived from expenditure / cost")
    imb = None
    if fin is not None and phys is not None:
        imb = fin - phys
    flag = imb is not None and imb >= IMBALANCE_REVIEW_THRESHOLD_PTS
    return ProgressMetrics(phys, fin, change, velocity, stagnant, is_stagnant,
                           sm.expected_progress_pct, gap, imb, flag, notes)


def required_velocity_pts_per_month(p: Project, as_of: date) -> Optional[float]:
    """Progress velocity needed to finish by the revised end date."""
    end = p.revised_end_date or p.original_end_date
    if end is None or p.physical_progress_pct is None:
        return None
    months = _months_between(as_of, end)
    remaining = max(0.0, 100.0 - p.physical_progress_pct)
    if months <= 0:
        return None if remaining == 0 else float("inf")
    return remaining / months
