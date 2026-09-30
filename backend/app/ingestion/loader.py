"""CSV/XLSX ingestion: parse -> validate -> normalise -> deduplicate.

Column aliases approximate the headings used by MoSPI PAIMANA-style exports. They are a best-effort
mapping and MUST be checked against a real export before relying on them; unknown columns are ignored
and unmapped required columns are reported, never guessed.
Invalid rows are rejected with reasons rather than silently repaired. Missing optional values stay NULL.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional

from app.domain.types import (DataOrigin, Issue, IssueStatus, IssueType, Milestone, Project, ProjectStatus,
                              Severity, Snapshot)

PROJECT_ALIASES = {
    "project_code": ["project_code", "project code", "projectcode", "code", "project id", "id"],
    "project_name": ["project_name", "project name", "name", "projectname", "project"],
    "sector": ["sector"],
    "line_ministry": ["line_ministry", "line ministry", "ministry", "administrative ministry"],
    "department": ["department"],
    "implementing_agency": ["implementing_agency", "implementing agency", "agency", "executing agency"],
    "state": ["state", "state/ut"],
    "district": ["district"],
    "project_type": ["project_type", "project type", "type"],
    "description": ["description"],
    "original_cost_crore": ["original_cost_crore", "original cost", "original cost (rs. crore)",
                            "original cost (₹ crore)", "sanctioned cost", "original_cost"],
    "revised_cost_crore": ["revised_cost_crore", "revised cost", "revised cost (rs. crore)",
                           "anticipated cost", "revised_cost"],
    "cumulative_expenditure_crore": ["cumulative_expenditure_crore", "expenditure", "cumulative expenditure",
                                     "expenditure (rs. crore)", "cumulative_expenditure"],
    "start_date": ["start_date", "start date", "date of commencement", "commencement date"],
    "original_end_date": ["original_end_date", "original end date", "original completion date",
                          "original date of completion"],
    "revised_end_date": ["revised_end_date", "revised end date", "revised completion date",
                         "anticipated completion date", "anticipated date of completion"],
    "physical_progress_pct": ["physical_progress_pct", "physical progress", "physical progress (%)",
                              "physical_progress"],
    "financial_progress_pct": ["financial_progress_pct", "financial progress", "financial progress (%)"],
    "status": ["status", "project status"],
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng", "long"],
    "origin": ["origin", "data_origin"],
}
SNAPSHOT_ALIASES = {
    "project_code": PROJECT_ALIASES["project_code"],
    "snapshot_month": ["snapshot_month", "month", "reporting_month", "reporting month"],
    "physical_progress_pct": PROJECT_ALIASES["physical_progress_pct"],
    "financial_progress_pct": PROJECT_ALIASES["financial_progress_pct"],
    "cumulative_expenditure_crore": PROJECT_ALIASES["cumulative_expenditure_crore"],
    "revised_cost_crore": PROJECT_ALIASES["revised_cost_crore"],
    "revised_end_date": PROJECT_ALIASES["revised_end_date"],
    "status": PROJECT_ALIASES["status"],
    "issues": ["issues", "issues_text", "reasons for delay", "remarks"],
    "source": ["source"], "source_document": ["source_document", "source document"],
    "origin": ["origin", "data_origin"],
}
MILESTONE_ALIASES = {
    "project_code": PROJECT_ALIASES["project_code"],
    "name": ["milestone_name", "milestone", "name"],
    "planned_start": ["planned_start"], "planned_end": ["planned_end"],
    "actual_start": ["actual_start"], "actual_end": ["actual_end"],
    "completion_pct": ["completion_percentage", "completion_pct", "completion"],
    "depends_on": ["dependency", "depends_on"], "weight": ["weight"],
}
ISSUE_ALIASES = {
    "project_code": PROJECT_ALIASES["project_code"],
    "issue_type": ["issue_type", "type", "category"], "description": ["description"],
    "severity": ["severity"], "reported_date": ["reported_date"],
    "expected_resolution_date": ["expected_resolution_date"],
    "actual_resolution_date": ["actual_resolution_date"], "owner": ["owner"],
    "status": ["status"], "impact": ["impact"],
}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%b-%y", "%b-%Y", "%Y-%m", "%m/%Y")
_NULLS = {"", "na", "n/a", "nan", "null", "none", "-", "--"}


class ParseError(ValueError):
    pass


def _clean(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _NULLS else s


def parse_float(v) -> Optional[float]:
    s = _clean(v)
    if s is None:
        return None
    s = re.sub(r"[₹,\s%]|rs\.?|crore|cr\.?", "", s, flags=re.I)
    try:
        f = float(s)
    except ValueError as e:
        raise ParseError(f"not a number: {v!r}") from e
    if f != f or f in (float("inf"), float("-inf")):
        raise ParseError(f"not a finite number: {v!r}")
    return f


def parse_date(v) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _clean(v)
    if s is None:
        return None
    s = s.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2} \d", s) else s
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"unrecognised date: {v!r}")


def _resolve_columns(header: Iterable[str], aliases: dict) -> tuple[dict, list]:
    norm = {re.sub(r"\s+", " ", h.strip().lower()): h for h in header if h}
    mapping = {}
    for canon, alts in aliases.items():
        for a in alts:
            if a.lower() in norm:
                mapping[canon] = norm[a.lower()]
                break
    return mapping, [k for k in aliases if k not in mapping]


def _rows(source) -> tuple[list, list]:
    """Accept a CSV text/path/bytes or a list of dicts. Returns (header, rows)."""
    if isinstance(source, list):
        header = list(source[0].keys()) if source else []
        return header, source
    if isinstance(source, (bytes, bytearray)):
        source = source.decode("utf-8-sig")
    if isinstance(source, str) and ("\n" not in source and "," not in source):
        with open(source, newline="", encoding="utf-8-sig") as fh:
            source = fh.read()
    reader = csv.DictReader(io.StringIO(source))
    return list(reader.fieldnames or []), list(reader)


@dataclass
class IngestionReport:
    kind: str
    total_rows: int = 0
    accepted: int = 0
    rejected: list = field(default_factory=list)   # [{row, project_code, errors}]
    warnings: list = field(default_factory=list)
    unmapped_columns: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _enum(cls, raw, default=None):
    s = _clean(raw)
    if s is None:
        return default
    key = re.sub(r"[\s\-/]+", "_", s.strip().upper())
    try:
        return cls(key)
    except ValueError:
        raise ParseError(f"invalid {cls.__name__}: {raw!r}")


def _validate_project_fields(d: dict) -> list:
    errs = []
    if not d.get("project_code"):
        errs.append("missing project_code")
    if not d.get("project_name"):
        errs.append("missing project_name")
    for k in ("original_cost_crore", "revised_cost_crore", "cumulative_expenditure_crore"):
        v = d.get(k)
        if v is not None and v < 0:
            errs.append(f"{k} is negative")
    for k in ("physical_progress_pct", "financial_progress_pct"):
        v = d.get(k)
        if v is not None and not (0 <= v <= 100):
            errs.append(f"{k} out of range 0-100: {v}")
    sd, oe, re_ = d.get("start_date"), d.get("original_end_date"), d.get("revised_end_date")
    if sd and oe and oe < sd:
        errs.append("original_end_date precedes start_date")
    if sd and re_ and re_ < sd:
        errs.append("revised_end_date precedes start_date")
    lat, lon = d.get("latitude"), d.get("longitude")
    if lat is not None and not (-90 <= lat <= 90):
        errs.append("latitude out of range")
    if lon is not None and not (-180 <= lon <= 180):
        errs.append("longitude out of range")
    return errs


def ingest_projects(source, default_origin: DataOrigin = DataOrigin.IMPORTED,
                    existing_codes: Optional[set] = None) -> tuple[list, IngestionReport]:
    header, rows = _rows(source)
    mapping, missing = _resolve_columns(header, PROJECT_ALIASES)
    rep = IngestionReport("projects", total_rows=len(rows))
    if "project_code" in missing or "project_name" in missing:
        rep.rejected.append({"row": 0, "project_code": None,
                             "errors": [f"required column(s) not found: {[c for c in ('project_code','project_name') if c in missing]}"]})
        return [], rep
    rep.unmapped_columns = [c for c in missing if c not in ("project_code", "project_name")]
    seen = set(existing_codes or ())
    out: list[Project] = []
    for i, raw in enumerate(rows, start=2):  # row 1 = header
        errs: list[str] = []
        d: dict = {}
        for canon, col in mapping.items():
            v = raw.get(col)
            try:
                if canon in ("original_cost_crore", "revised_cost_crore", "cumulative_expenditure_crore",
                             "physical_progress_pct", "financial_progress_pct", "latitude", "longitude"):
                    d[canon] = parse_float(v)
                elif canon in ("start_date", "original_end_date", "revised_end_date"):
                    d[canon] = parse_date(v)
                elif canon == "status":
                    d[canon] = _enum(ProjectStatus, v, ProjectStatus.UNDER_CONSTRUCTION)
                elif canon == "origin":
                    d[canon] = _enum(DataOrigin, v, default_origin)
                else:
                    d[canon] = _clean(v)
            except ParseError as e:
                errs.append(f"{canon}: {e}")
        errs += _validate_project_fields(d)
        code = d.get("project_code")
        if code and code in seen:
            errs.append(f"duplicate project_code {code}")
        if errs:
            rep.rejected.append({"row": i, "project_code": code, "errors": errs})
            continue
        seen.add(code)
        d.setdefault("origin", default_origin)
        out.append(Project(**d))
    rep.accepted = len(out)
    return out, rep


def ingest_snapshots(source, known_codes: set, default_origin: DataOrigin = DataOrigin.IMPORTED):
    """Returns ({project_code: [Snapshot]}, report). Duplicate (code, month) keeps the last row with a warning."""
    header, rows = _rows(source)
    mapping, missing = _resolve_columns(header, SNAPSHOT_ALIASES)
    rep = IngestionReport("snapshots", total_rows=len(rows))
    if "project_code" in missing or "snapshot_month" in missing:
        rep.rejected.append({"row": 0, "project_code": None, "errors": ["project_code/snapshot_month column missing"]})
        return {}, rep
    by: dict = {}
    for i, raw in enumerate(rows, start=2):
        errs = []
        g = lambda k: raw.get(mapping[k]) if k in mapping else None  # noqa: E731
        code = _clean(g("project_code"))
        try:
            month = parse_date(g("snapshot_month"))
            if month is None:
                errs.append("snapshot_month missing")
            else:
                month = month.replace(day=1)
            phys = parse_float(g("physical_progress_pct"))
            fin = parse_float(g("financial_progress_pct"))
            exp = parse_float(g("cumulative_expenditure_crore"))
            rev = parse_float(g("revised_cost_crore"))
            red = parse_date(g("revised_end_date"))
            st = _enum(ProjectStatus, g("status"), None)
            origin = _enum(DataOrigin, g("origin"), default_origin)
        except ParseError as e:
            errs.append(str(e))
            phys = fin = exp = rev = red = st = origin = None
            month = month if "month" in locals() else None
        if code is None:
            errs.append("missing project_code")
        elif code not in known_codes:
            errs.append(f"unknown project_code {code}")
        for name, v in (("physical_progress_pct", phys), ("financial_progress_pct", fin)):
            if v is not None and not (0 <= v <= 100):
                errs.append(f"{name} out of range 0-100: {v}")
        for name, v in (("cumulative_expenditure_crore", exp), ("revised_cost_crore", rev)):
            if v is not None and v < 0:
                errs.append(f"{name} is negative")
        if errs:
            rep.rejected.append({"row": i, "project_code": code, "errors": errs})
            continue
        snap = Snapshot(month, phys, fin, exp, rev, red, st, _clean(g("issues")), _clean(g("source")),
                        _clean(g("source_document")), origin)
        lst = by.setdefault(code, {})
        if month in lst:
            rep.warnings.append(f"row {i}: duplicate snapshot {code} {month:%Y-%m}; later row kept")
        lst[month] = snap
    for code, m in by.items():
        ordered = [m[k] for k in sorted(m)]
        prev = None
        for s in ordered:
            if prev is not None and s.physical_progress_pct is not None and prev.physical_progress_pct is not None \
                    and s.physical_progress_pct + 1e-9 < prev.physical_progress_pct:
                rep.warnings.append(f"{code}: physical progress decreased {prev.snapshot_month:%Y-%m}"
                                    f"->{s.snapshot_month:%Y-%m} (kept; review source)")
            prev = s
        by[code] = ordered
    rep.accepted = sum(len(v) for v in by.values())
    return by, rep


def ingest_milestones(source, known_codes: set):
    header, rows = _rows(source)
    mapping, missing = _resolve_columns(header, MILESTONE_ALIASES)
    rep = IngestionReport("milestones", total_rows=len(rows))
    if "project_code" in missing or "name" in missing:
        rep.rejected.append({"row": 0, "project_code": None, "errors": ["project_code/milestone_name column missing"]})
        return {}, rep
    by: dict = {}
    for i, raw in enumerate(rows, start=2):
        g = lambda k: raw.get(mapping[k]) if k in mapping else None  # noqa: E731
        code, errs = _clean(g("project_code")), []
        try:
            ps, pe, as_, ae = (parse_date(g(k)) for k in ("planned_start", "planned_end", "actual_start", "actual_end"))
            comp = parse_float(g("completion_pct")) or 0.0
            w = parse_float(g("weight"))
        except ParseError as e:
            errs.append(str(e))
            ps = pe = as_ = ae = None
            comp, w = 0.0, None
        if code not in known_codes:
            errs.append(f"unknown project_code {code}")
        if not _clean(g("name")):
            errs.append("missing milestone name")
        if not (0 <= comp <= 100):
            errs.append("completion_pct out of range 0-100")
        if ps and pe and pe < ps:
            errs.append("planned_end precedes planned_start")
        if as_ and ae and ae < as_:
            errs.append("actual_end precedes actual_start")
        if w is not None and w <= 0:
            errs.append("weight must be positive")
        if errs:
            rep.rejected.append({"row": i, "project_code": code, "errors": errs})
            continue
        by.setdefault(code, []).append(Milestone(_clean(g("name")), ps, pe, as_, ae, comp, _clean(g("depends_on")),
                                                 w if w is not None else 1.0))
    rep.accepted = sum(len(v) for v in by.values())
    return by, rep


def ingest_issues(source, known_codes: set):
    header, rows = _rows(source)
    mapping, missing = _resolve_columns(header, ISSUE_ALIASES)
    rep = IngestionReport("issues", total_rows=len(rows))
    if "project_code" in missing or "issue_type" in missing:
        rep.rejected.append({"row": 0, "project_code": None, "errors": ["project_code/issue_type column missing"]})
        return {}, rep
    by: dict = {}
    for i, raw in enumerate(rows, start=2):
        g = lambda k: raw.get(mapping[k]) if k in mapping else None  # noqa: E731
        code, errs = _clean(g("project_code")), []
        try:
            it = _enum(IssueType, g("issue_type"))
            sev = _enum(Severity, g("severity"), Severity.MEDIUM)
            st = _enum(IssueStatus, g("status"), IssueStatus.OPEN)
            rd, ed, ad = (parse_date(g(k)) for k in ("reported_date", "expected_resolution_date",
                                                     "actual_resolution_date"))
        except ParseError as e:
            errs.append(str(e))
            it = sev = st = rd = ed = ad = None
        if code not in known_codes:
            errs.append(f"unknown project_code {code}")
        if it is None and not errs:
            errs.append("missing issue_type")
        if rd and ad and ad < rd:
            errs.append("actual_resolution_date precedes reported_date")
        if errs:
            rep.rejected.append({"row": i, "project_code": code, "errors": errs})
            continue
        by.setdefault(code, []).append(Issue(it, sev, st, _clean(g("description")) or "", rd, ed, ad,
                                             _clean(g("owner")), _clean(g("impact"))))
    rep.accepted = sum(len(v) for v in by.values())
    return by, rep


def assemble(projects, snapshots: dict, milestones: dict, issues: dict) -> list:
    out = []
    for p in projects:
        out.append(p.with_(snapshots=tuple(snapshots.get(p.project_code, ())),
                           milestones=tuple(milestones.get(p.project_code, ())),
                           issues=tuple(issues.get(p.project_code, ()))))
    return out
