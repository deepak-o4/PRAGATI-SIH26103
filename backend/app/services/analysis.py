"""Recompute and persist risk; raise alerts on band worsening. Audit-friendly: stores version, weights, factors."""
from __future__ import annotations

from datetime import date

from app.core.config import settings
from app.domain.types import RiskBand, Severity
from app.models import entities as E
from app.risk.engine import RiskConfig, compute_risk
from app.services.repository import to_domain
from app.analytics.metrics import progress_metrics

ORDER = {RiskBand.STABLE: 0, RiskBand.WATCH: 1, RiskBand.WARNING: 2, RiskBand.CRITICAL: 3}


def risk_config() -> RiskConfig:
    import os
    if settings.RISK_WEIGHTS_JSON:
        os.environ["RISK_WEIGHTS_JSON"] = settings.RISK_WEIGHTS_JSON
    return RiskConfig.from_env()


async def recompute_project(db, row: E.Project, as_of: date | None = None, cfg=None) -> dict:
    as_of = as_of or date.today()
    cfg = cfg or risk_config()
    d = to_domain(row)
    r = compute_risk(d, as_of, cfg)
    prev = row.risk_level
    row.risk_score, row.risk_level = r.score, r.band
    db.add(E.RiskSnapshot(project_id=row.id, as_of=as_of, score=r.score, band=r.band, version=r.version,
                          weights=r.weights, factors=[c.__dict__ for c in r.contributors]))
    if prev is not None and ORDER[r.band] > ORDER[prev]:
        db.add(E.Alert(project_id=row.id, kind="RISK_BAND_CHANGE",
                       severity=Severity.CRITICAL if r.band == RiskBand.CRITICAL else Severity.HIGH,
                       message=f"{row.project_code} risk moved {prev.value} -> {r.band.value} (score {r.score})"))
    g = progress_metrics(d, as_of)
    if g.is_stagnant:
        db.add(E.Alert(project_id=row.id, kind="STAGNATION", severity=Severity.MEDIUM,
                       message=f"{row.project_code}: physical progress flat for {g.stagnant_snapshots} consecutive reports"))
    if g.imbalance_flag:
        db.add(E.Alert(project_id=row.id, kind="IMBALANCE", severity=Severity.MEDIUM,
                       message=f"{row.project_code}: expenditure is {g.cost_progress_imbalance_pts:.0f} pts ahead of physical progress (review indicator, not a finding)"))
    return r.to_dict()


async def recompute_all(db, projects_rows, as_of=None) -> int:
    cfg = risk_config()
    for row in projects_rows:
        await recompute_project(db, row, as_of, cfg)
    return len(projects_rows)
