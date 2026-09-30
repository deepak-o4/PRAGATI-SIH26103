"""PRAGATI Copilot: structured analytics first, retrieval second, LLM optional.

Every number in an answer is computed from application data (``enrich`` rows). The router is deterministic
(rule-based intents). An optional ``narrator`` callable (an LLM adapter) may only *rephrase* the already
computed answer text; it never receives permission to add figures, and is not wired in by default.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional

from app.analytics.portfolio import enrich, group_by

STATES_HINT = None  # states are matched against data, not a hard-coded list


def _fmt_cr(v):
    return "n/a" if v is None else f"₹{v:,.0f} Cr"


def _evidence(r: dict, as_of: date) -> dict:
    return {"project_code": r["project_code"], "snapshot_as_of": as_of.isoformat(), "origin": r["origin"],
            "physical_progress_pct": r["physical_progress_pct"], "original_cost_crore": r["original_cost_crore"],
            "revised_cost_crore": r["revised_cost_crore"], "expenditure_crore": r["cumulative_expenditure_crore"],
            "risk_score": r["risk_score"], "risk_band": r["risk_band"]}


def _table(rows, cols):
    return [{c: r.get(c) for c in cols} for r in rows]


def _find_codes(q: str, rows: list) -> list:
    ql = q.lower()
    found = []
    for r in rows:
        if r["project_code"].lower() in ql and r["project_code"] not in found:
            found.append(r["project_code"])
    return found


def _limit(q: str, default=10) -> int:
    m = re.search(r"\b(?:top|first|best|worst)\s+(\d{1,3})\b", q.lower())
    return int(m.group(1)) if m else default


def answer(question: str, projects, as_of: Optional[date] = None, cfg=None,
           retriever: Optional[Callable] = None, narrator: Optional[Callable] = None) -> dict:
    as_of = as_of or date.today()
    projects = list(projects)
    by_code = {p.project_code: p for p in projects}
    rows = [enrich(p, as_of, cfg) for p in projects]
    rmap = {r["project_code"]: r for r in rows}
    q = question.strip()
    ql = q.lower()
    n = _limit(q)
    demo = any(r["origin"] == "SYNTHETIC_DEMO" for r in rows)
    res = {"question": q, "as_of": as_of.isoformat(), "intent": None, "answer": "", "table": [], "evidence": [],
           "sources": [{"type": "structured_analytics", "detail": "PRAGATI project snapshot data"}],
           "demo_data_notice": "Figures include SYNTHETIC_DEMO data, not official records." if demo else None}
    codes = _find_codes(q, rows)
    active = [r for r in rows if r["status"] not in ("COMPLETED", "CANCELLED")]

    def done(intent, text, table=None, ev=None):
        res.update(intent=intent, answer=text, table=table or [], evidence=ev or [])
        if narrator and text:
            res["narrated"] = narrator(text)
        return res

    if not rows:
        return done("empty", "There are no projects loaded, so no figures can be computed.")

    if ("compare" in ql) and len(codes) >= 2:
        a, b = rmap[codes[0]], rmap[codes[1]]
        cols = ["project_code", "sector", "state", "risk_score", "risk_band", "physical_progress_pct", "cost_overrun_pct",
                "schedule_delay_days", "cumulative_expenditure_crore", "revised_cost_crore"]
        return done("compare", f"{a['project_code']} has risk {a['risk_score']} ({a['risk_band']}); {b['project_code']} has "
                    f"risk {b['risk_score']} ({b['risk_band']}).", _table([a, b], cols), [_evidence(a, as_of), _evidence(b, as_of)])

    if codes and re.search(r"\bwhy\b|risk|explain", ql):
        from app.risk.engine import compute_risk
        code = codes[0]
        r = compute_risk(by_code[code], as_of, cfg)
        top = [c for c in sorted(r.contributors, key=lambda c: -c.points) if c.points > 0][:4]
        lines = "; ".join(f"{c.label} +{c.points} ({c.explanation})" for c in top) or "no contributing factors above zero"
        txt = f"{code} scores {r.score} ({r.band.value}). Main contributors: {lines}."
        if r.notes:
            txt += " Note: " + " ".join(r.notes)
        return done("explain_risk", txt, [{"component": c.label, "points": c.points, "detail": c.explanation}
                                          for c in r.contributors], [_evidence(rmap[code], as_of)])

    if codes and re.search(r"summar|executive|brief|overview|status of", ql):
        r = rmap[codes[0]]
        txt = (f"{r['project_code']} — {r['project_name']} ({r['sector']}, {r['state']}). Status {r['status']}, risk "
               f"{r['risk_score']} ({r['risk_band']}). Physical progress {r['physical_progress_pct']}%; original cost "
               f"{_fmt_cr(r['original_cost_crore'])}, revised {_fmt_cr(r['revised_cost_crore'])}, expenditure "
               f"{_fmt_cr(r['cumulative_expenditure_crore'])}. Total schedule slippage vs original: "
               f"{r['schedule_delay_days']} days; {r['open_issues']} open issue(s), {r['critical_issues']} critical.")
        return done("project_summary", txt, [], [_evidence(r, as_of)])

    if re.search(r"critical", ql) and re.search(r"risk|project", ql) and "issue" not in ql:
        sel = sorted([r for r in active if r["risk_band"] == "CRITICAL"], key=lambda r: -r["risk_score"])
        cols = ["project_code", "project_name", "sector", "state", "risk_score", "physical_progress_pct", "schedule_delay_days"]
        return done("critical_projects", f"{len(sel)} active project(s) are in the CRITICAL risk band"
                    + (f"; showing the top {min(n, len(sel))}." if sel else "."), _table(sel[:n], cols),
                    [_evidence(r, as_of) for r in sel[:n]])

    if re.search(r"cost overrun|overrun", ql):
        sel = sorted([r for r in rows if r["cost_overrun_pct"] is not None], key=lambda r: -r["cost_overrun_pct"])
        cols = ["project_code", "project_name", "sector", "original_cost_crore", "revised_cost_crore", "cost_overrun_pct", "cost_overrun_amount"]
        skipped = len(rows) - len(sel)
        return done("cost_overrun", f"Top {min(n, len(sel))} projects by cost overrun %. {skipped} project(s) excluded for missing cost data.",
                    _table(sel[:n], cols), [_evidence(r, as_of) for r in sel[:n]])

    if re.search(r"stall|stagnant|no progress|stuck", ql):
        sel = [r for r in active if r["is_stagnant"]]
        cols = ["project_code", "project_name", "sector", "physical_progress_pct", "progress_velocity", "risk_score"]
        return done("stalled", f"{len(sel)} active project(s) show stagnant physical progress over consecutive reports.",
                    _table(sorted(sel, key=lambda r: -r["risk_score"])[:n], cols), [_evidence(r, as_of) for r in sel[:n]])

    if re.search(r"expenditure", ql) and re.search(r"low|less|lag|physical", ql):
        sel = sorted([r for r in active if r["imbalance_flag"]], key=lambda r: -(r["cost_progress_imbalance_pts"] or 0))
        cols = ["project_code", "project_name", "expenditure_ratio_pct", "physical_progress_pct", "cost_progress_imbalance_pts"]
        return done("cost_progress_imbalance", f"{len(sel)} project(s) have expenditure well ahead of physical progress. "
                    "This is an analytical indicator that warrants review, not evidence of misuse.", _table(sel[:n], cols),
                    [_evidence(r, as_of) for r in sel[:n]])

    if re.search(r"sector", ql) and re.search(r"risk", ql):
        g = sorted([x for x in group_by(active, "sector") if x["avg_risk"] is not None], key=lambda x: -x["avg_risk"])
        top = g[0] if g else None
        return done("sector_risk", (f"{top['key']} has the highest average risk ({top['avg_risk']}) across {top['projects']} active project(s)." if top else "No sector risk data."),
                    [{k: x[k] for k in ("key", "projects", "avg_risk", "critical")} for x in g])

    if re.search(r"approach|near|upcoming|due|deadline|revised completion", ql):
        sel = sorted([r for r in active if r["days_remaining"] is not None and 0 <= r["days_remaining"] <= 180], key=lambda r: r["days_remaining"])
        cols = ["project_code", "project_name", "revised_end_date", "days_remaining", "physical_progress_pct", "risk_score"]
        return done("approaching_deadline", f"{len(sel)} active project(s) reach their revised completion date within 180 days.",
                    _table(sel[:n], cols), [_evidence(r, as_of) for r in sel[:n]])

    if re.search(r"delay", ql):
        st = next((r["state"] for r in rows if r["state"] and r["state"].lower() in ql), None)
        sel = [r for r in active if (r["schedule_delay_days"] or 0) > 0 and (st is None or r["state"] == st)]
        sel.sort(key=lambda r: -(r["schedule_delay_days"] or 0))
        cols = ["project_code", "project_name", "state", "schedule_delay_days", "revised_slip_days", "overdue_days", "risk_score"]
        return done("delayed", f"{len(sel)} delayed active project(s)" + (f" in {st}" if st else "") + ".",
                    _table(sel[:n], cols), [_evidence(r, as_of) for r in sel[:n]])

    if re.search(r"how many|count|total number", ql):
        return done("count", f"There are {len(rows)} project(s), of which {len(active)} are active.")

    # Fall back to document retrieval (RAG) when available; otherwise say what can be answered.
    if retriever is not None:
        hits = retriever(q)
        if hits:
            res["sources"] += [{"type": "document", "detail": h["source"], "score": h["score"]} for h in hits]
            return done("document_retrieval", "Relevant passages from uploaded documents:\n" + "\n".join(
                f"[{h['source']}] {h['text'][:300]}" for h in hits))
    return done("unsupported", "I could not map that question to a supported analysis. Try asking about critical-risk projects, "
                "cost overruns, stalled progress, delays by state, a project's risk explanation (include its project code), "
                "expenditure vs progress, sector risk, or upcoming deadlines.")
