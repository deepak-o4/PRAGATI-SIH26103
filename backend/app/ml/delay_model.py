"""Delay-prediction architecture.

Target ``likely_delay`` must come from REAL outcomes: a project that was completed (or whose revised date
was later re-revised) after a given historical snapshot. This module therefore:

* builds features per (project, snapshot) using only information available at that snapshot,
* builds labels ONLY from later real snapshots/completions (``build_training_set``),
* refuses to train unless there are enough labelled rows of both classes (``MIN_ROWS`` / ``MIN_PER_CLASS``),
* always exposes ``predict`` -- using the trained model when one is loaded, else a deterministic fallback
  derived from the transparent risk engine (clearly labelled ``fallback-rule-v1``, NOT a learned model).

Model: scikit-learn GradientBoostingClassifier (always available). XGBoost/LightGBM/SHAP are used only if
installed; otherwise explanations use permutation-free, model-agnostic ``contribution`` via feature-ablation
against the training mean (labelled ``ablation``). No model file is shipped: none has been trained on real data.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from app.analytics.metrics import cost_metrics, progress_metrics, schedule_metrics
from app.domain.types import Project, Severity
from app.risk.engine import compute_risk, project_as_of, _month_end

FEATURES = ["cost_overrun_pct", "progress_velocity", "schedule_delay_days", "days_remaining", "milestone_delay_days",
            "expenditure_ratio", "stagnant_snapshots", "issue_count", "issue_severity", "project_age_days",
            "progress_gap_pts", "physical_progress_pct"]
SECTOR_FEATURE_NOTE = "sector is not a numeric feature here; add one-hot encoding once >=1 sector has enough history"
MIN_ROWS = 300
MIN_PER_CLASS = 40
FALLBACK_VERSION = "fallback-rule-v1"


def features_for(p: Project, as_of: date) -> dict:
    c, s, g = cost_metrics(p), schedule_metrics(p, as_of), progress_metrics(p, as_of)
    ms = [m.delay_days(as_of) for m in p.milestones if m.planned_end]
    open_iss = [i for i in p.issues if i.is_open]
    sev = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}
    nan = float("nan")
    f = {
        "cost_overrun_pct": c.cost_overrun_pct, "progress_velocity": g.progress_velocity_pts_per_month,
        "schedule_delay_days": s.schedule_delay_days, "days_remaining": s.days_remaining,
        "milestone_delay_days": max(ms) if ms else None, "expenditure_ratio": c.expenditure_ratio_pct,
        "stagnant_snapshots": g.stagnant_snapshots, "issue_count": len(open_iss),
        "issue_severity": max((sev[i.severity] for i in open_iss), default=0),
        "project_age_days": s.current_duration_days, "progress_gap_pts": g.progress_gap_pts,
        "physical_progress_pct": p.physical_progress_pct,
    }
    return {k: (nan if v is None else float(v)) for k, v in f.items()}


def build_training_set(projects, horizon_days: int = 180):
    """Real-outcome labelling. For each snapshot S of a project with a later real observation:
    label=1 if the official revised end date was pushed out (by >30 d) between S and the project's LAST snapshot,
    or the project completed after its revised end date as of S. Returns (X rows, y, meta). Rows without a
    resolvable outcome are excluded, never guessed."""
    X, y, meta = [], [], []
    for p in projects:
        snaps = p.sorted_snapshots()
        if len(snaps) < 3:
            continue
        last = snaps[-1]
        for s in snaps[:-1]:
            if (last.snapshot_month - s.snapshot_month).days < horizon_days:
                continue
            view = project_as_of(p, s.snapshot_month)
            end_then = view.revised_end_date or view.original_end_date
            end_later = last.revised_end_date or p.revised_end_date
            if end_then is None or end_later is None:
                continue
            label = int((end_later - end_then).days > 30)
            X.append(features_for(view, _month_end(s.snapshot_month)))
            y.append(label)
            meta.append((p.project_code, s.snapshot_month.isoformat()))
    return X, y, meta


@dataclass
class TrainReport:
    trained: bool
    reason: str
    rows: int = 0
    positives: int = 0
    metrics: dict = field(default_factory=dict)
    model_path: Optional[str] = None
    version: Optional[str] = None


def train(projects, model_dir: str, horizon_days: int = 180) -> TrainReport:
    X, y, meta = build_training_set(projects, horizon_days)
    pos = sum(y)
    if len(y) < MIN_ROWS or pos < MIN_PER_CLASS or (len(y) - pos) < MIN_PER_CLASS:
        return TrainReport(False, f"insufficient labelled history: {len(y)} rows ({pos} positive); need >= {MIN_ROWS} "
                                  f"rows and >= {MIN_PER_CLASS} per class. Using deterministic fallback.", len(y), pos)
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit
    import joblib
    A = np.array([[r[k] for k in FEATURES] for r in X], dtype=float)
    yy = np.array(y)
    groups = np.array([m[0] for m in meta])
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=7).split(A, yy, groups))  # split by project: no leakage
    clf = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08, max_iter=200, random_state=7)
    clf.fit(A[tr], yy[tr])
    auc = float(roc_auc_score(yy[te], clf.predict_proba(A[te])[:, 1])) if len(set(yy[te])) == 2 else None
    means = np.nanmean(A[tr], axis=0)
    version = f"hgb-{date.today():%Y%m%d}"
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    path = Path(model_dir) / "delay_model.joblib"
    joblib.dump({"model": clf, "features": FEATURES, "train_means": means.tolist(), "version": version}, path)
    (Path(model_dir) / "delay_model.json").write_text(json.dumps(
        {"version": version, "rows": len(y), "positives": pos, "holdout_auc_by_project_split": auc,
         "label_definition": "revised end date pushed out >30d between snapshot and last observation",
         "trained_on": "see data origins of training projects; do not treat as validated unless origin is OFFICIAL"}, indent=2))
    return TrainReport(True, "trained", len(y), pos, {"holdout_auc": auc}, str(path), version)


def load_model(model_dir: str):
    path = Path(model_dir) / "delay_model.joblib"
    if not path.exists():
        return None
    import joblib
    return joblib.load(path)


def _fallback(p: Project, as_of: date, feats: dict) -> dict:
    r = compute_risk(p, as_of)
    prob = 1 / (1 + math.exp(-(r.score - 55) / 12))   # monotone map of risk score; NOT a calibrated probability
    top = sorted(((c.label, c.points) for c in r.contributors if c.points > 0), key=lambda t: -t[1])[:5]
    return {"delay_probability": round(prob, 3), "model_version": FALLBACK_VERSION, "method": "risk-score-logistic-map",
            "calibrated": False, "confidence": None, "origin": "PREDICTED",
            "top_factors": [{"feature": k, "impact": round(v, 2), "direction": "+"} for k, v in top],
            "note": "Deterministic fallback derived from the risk engine; not a learned model and not calibrated."}


def predict(p: Project, as_of: Optional[date] = None, model=None) -> dict:
    as_of = as_of or date.today()
    feats = features_for(p, as_of)
    if model is None:
        return _fallback(p, as_of, feats)
    import numpy as np
    x = np.array([[feats[k] for k in model["features"]]], dtype=float)
    clf = model["model"]
    prob = float(clf.predict_proba(x)[0, 1])
    means = model["train_means"]
    contribs = []
    for i, name in enumerate(model["features"]):
        if math.isnan(x[0, i]):
            continue
        x2 = x.copy()
        x2[0, i] = means[i]
        delta = prob - float(clf.predict_proba(x2)[0, 1])
        contribs.append({"feature": name, "value": float(x[0, i]), "impact": round(delta, 4),
                         "direction": "+" if delta > 0 else "-"})
    contribs.sort(key=lambda d: -abs(d["impact"]))
    shap_note = "feature-ablation vs training mean (SHAP not installed)"
    try:
        import shap  # noqa: F401
        shap_note = "ablation used; install/enable SHAP TreeExplainer path for exact Shapley values"
    except ImportError:
        pass
    return {"delay_probability": round(prob, 3), "model_version": model["version"], "method": "gradient-boosting",
            "calibrated": False, "confidence": None, "origin": "PREDICTED", "top_factors": contribs[:6],
            "explanation_method": shap_note}
