from datetime import date
from app.domain.types import *

AS_OF = date(2026, 9, 30)

def mk(code="T-1", **kw):
    base = dict(project_code=code, project_name="Test", sector="Railways", line_ministry="MoR", state="Uttar Pradesh",
                original_cost_crore=1000.0, revised_cost_crore=1200.0, cumulative_expenditure_crore=600.0,
                start_date=date(2023, 1, 1), original_end_date=date(2026, 1, 1), revised_end_date=date(2027, 1, 1),
                physical_progress_pct=50.0, status=ProjectStatus.UNDER_CONSTRUCTION)
    base.update(kw)
    return Project(**base)

def snaps(vals, start=date(2026, 1, 1)):
    out = []
    y, m = start.year, start.month
    for v in vals:
        out.append(Snapshot(date(y, m, 1), physical_progress_pct=v))
        m += 1
        if m > 12: y, m = y + 1, 1
    return tuple(out)
