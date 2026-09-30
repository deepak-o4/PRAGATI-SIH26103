"""Completion forecasting from the project's own progress history.

Method: least-squares linear trend over the most recent ``window`` physical-progress snapshots.
Outputs are labelled PREDICTED and are always kept separate from the official revised end date.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from app.domain.types import DataOrigin, Project, ProjectStatus

METHOD = "linear-trend-v1"
HORIZON_DAYS = 3650


@dataclass
class Forecast:
    project_code: str
    method: str
    origin: str = DataOrigin.PREDICTED.value
    official_revised_end_date: Optional[date] = None      # as reported, never overwritten
    predicted_completion_date: Optional[date] = None      # PRAGATI estimate
    estimated_delay_days: Optional[int] = None            # predicted - official revised end
    velocity_pts_per_month: Optional[float] = None
    confidence: Optional[float] = None                    # 0..1
    confidence_label: str = "NONE"
    points_used: int = 0
    status: str = "OK"                                    # OK / COMPLETED / INSUFFICIENT_HISTORY / STALLED / BEYOND_HORIZON
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        for k in ("official_revised_end_date", "predicted_completion_date"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


def _linreg(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    icpt = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (icpt + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 if ss_tot == 0 else max(0.0, 1 - ss_res / ss_tot)
    return slope, icpt, r2


def _label(c: float) -> str:
    return "LOW" if c < 0.4 else "MEDIUM" if c < 0.7 else "HIGH"


def forecast_completion(p: Project, as_of: Optional[date] = None, window: int = 6,
                        recovery_days: int = 0) -> Forecast:
    as_of = as_of or date.today()
    official = p.revised_end_date or p.original_end_date
    f = Forecast(p.project_code, METHOD, official_revised_end_date=official)
    if p.status == ProjectStatus.COMPLETED or (p.physical_progress_pct or 0) >= 100:
        f.status = "COMPLETED"
        f.reasons.append("project is physically complete")
        return f
    pts = [(s.snapshot_month, s.physical_progress_pct) for s in p.sorted_snapshots()
           if s.physical_progress_pct is not None]
    if len(pts) < 2:
        f.status = "INSUFFICIENT_HISTORY"
        f.reasons.append("need at least two progress snapshots to forecast")
        return f
    pts = pts[-window:]
    f.points_used = len(pts)
    x0 = pts[0][0].toordinal()
    xs = [d.toordinal() - x0 for d, _ in pts]
    ys = [v for _, v in pts]
    fit = _linreg(xs, ys)
    if fit is None:
        f.status = "INSUFFICIENT_HISTORY"
        f.reasons.append("snapshots share the same date")
        return f
    slope, _, r2 = fit
    f.velocity_pts_per_month = round(slope * 30.4375, 3)
    span_days = xs[-1] - xs[0]
    conf = r2 * min(1.0, len(pts) / 6.0) * (1.0 if span_days >= 90 else 0.7)
    f.confidence = round(conf, 2)
    f.confidence_label = _label(conf)
    if slope <= 1e-9:
        f.status = "STALLED"
        f.confidence = round(conf, 2)
        f.reasons.append("no positive progress trend; completion cannot be projected")
        return f
    current = ys[-1]
    last_date = pts[-1][0]
    days_needed = (100.0 - current) / slope
    if days_needed > HORIZON_DAYS:
        f.status = "BEYOND_HORIZON"
        f.reasons.append(f"trend implies completion more than {HORIZON_DAYS // 365} years away")
        return f
    est = last_date + timedelta(days=int(round(days_needed)) - recovery_days)
    est = max(est, as_of) if est < as_of and current < 100 else est
    f.predicted_completion_date = est
    if official:
        f.estimated_delay_days = (est - official).days
    f.reasons.append(f"linear trend over {len(pts)} snapshots, R²={r2:.2f}")
    if recovery_days:
        f.reasons.append(f"includes user-assumed recovery of {recovery_days} days (scenario assumption)")
    return f
