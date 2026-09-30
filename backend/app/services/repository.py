"""ORM <-> domain conversion and persistence helpers."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain import types as T
from app.models import entities as E


def snap_to_domain(s: E.ProjectSnapshot) -> T.Snapshot:
    return T.Snapshot(s.snapshot_month, s.physical_progress_pct, s.financial_progress_pct, s.cumulative_expenditure_crore,
                      s.revised_cost_crore, s.revised_end_date, s.status, s.issues_text, s.source, s.source_document, s.origin)


def to_domain(p: E.Project) -> T.Project:
    return T.Project(
        project_code=p.project_code, project_name=p.project_name, sector=p.sector, line_ministry=p.line_ministry,
        department=p.department, implementing_agency=p.implementing_agency, state=p.state, district=p.district,
        project_type=p.project_type, description=p.description, original_cost_crore=p.original_cost_crore,
        revised_cost_crore=p.revised_cost_crore, cumulative_expenditure_crore=p.cumulative_expenditure_crore,
        start_date=p.start_date, original_end_date=p.original_end_date, revised_end_date=p.revised_end_date,
        physical_progress_pct=p.physical_progress_pct, financial_progress_pct=p.financial_progress_pct,
        status=p.status, latitude=p.latitude, longitude=p.longitude, origin=p.origin,
        snapshots=tuple(snap_to_domain(s) for s in p.snapshots),
        milestones=tuple(T.Milestone(m.name, m.planned_start, m.planned_end, m.actual_start, m.actual_end,
                                     m.completion_pct, m.depends_on, m.weight) for m in p.milestones),
        issues=tuple(T.Issue(i.issue_type, i.severity, i.status, i.description or "", i.reported_date,
                             i.expected_resolution_date, i.actual_resolution_date, i.owner, i.impact, str(i.id))
                     for i in p.issues))


_LOAD = (selectinload(E.Project.snapshots), selectinload(E.Project.milestones), selectinload(E.Project.issues))


async def load_projects(db: AsyncSession, **filters) -> list[T.Project]:
    q = select(E.Project).options(*_LOAD)
    for k in ("sector", "line_ministry", "implementing_agency", "state"):
        if filters.get(k):
            q = q.where(getattr(E.Project, k) == filters[k])
    if filters.get("status"):
        q = q.where(E.Project.status == T.ProjectStatus(filters["status"]))
    if filters.get("origin"):
        q = q.where(E.Project.origin == T.DataOrigin(filters["origin"]))
    res = await db.execute(q.order_by(E.Project.project_code))
    return [to_domain(p) for p in res.scalars().unique().all()]


async def get_orm_project(db: AsyncSession, ident: str) -> Optional[E.Project]:
    """Lookup by UUID or project_code."""
    q = select(E.Project).options(*_LOAD)
    try:
        q = q.where(E.Project.id == uuid.UUID(ident))
    except ValueError:
        q = q.where(E.Project.project_code == ident)
    return (await db.execute(q)).scalars().unique().first()


async def upsert_projects(db: AsyncSession, projects: list[T.Project], data_source_id=None) -> tuple[int, int]:
    """Insert new / update existing by project_code. Snapshots upsert by (project, month)."""
    created = updated = 0
    codes = [p.project_code for p in projects]
    existing = {}
    if codes:
        res = await db.execute(select(E.Project).options(selectinload(E.Project.snapshots)).where(E.Project.project_code.in_(codes)))
        existing = {p.project_code: p for p in res.scalars().unique().all()}
    fields = ["project_name", "sector", "line_ministry", "department", "implementing_agency", "state", "district",
              "project_type", "description", "original_cost_crore", "revised_cost_crore", "cumulative_expenditure_crore",
              "start_date", "original_end_date", "revised_end_date", "physical_progress_pct", "financial_progress_pct",
              "status", "latitude", "longitude", "origin"]
    for d in projects:
        row = existing.get(d.project_code)
        if row is None:
            row = E.Project(project_code=d.project_code, data_source_id=data_source_id, **{f: getattr(d, f) for f in fields})
            db.add(row)
            row.snapshots = []
            created += 1
        else:
            for f in fields:
                v = getattr(d, f)
                if v is not None:
                    setattr(row, f, v)
            updated += 1
        by_month = {s.snapshot_month: s for s in row.snapshots}
        for s in d.snapshots:
            cur = by_month.get(s.snapshot_month)
            vals = dict(physical_progress_pct=s.physical_progress_pct, financial_progress_pct=s.financial_progress_pct,
                        cumulative_expenditure_crore=s.cumulative_expenditure_crore, revised_cost_crore=s.revised_cost_crore,
                        revised_end_date=s.revised_end_date, status=s.status, issues_text=s.issues_text,
                        source=s.source, source_document=s.source_document, origin=s.origin)
            if cur is None:
                row.snapshots.append(E.ProjectSnapshot(snapshot_month=s.snapshot_month, **vals))
            else:
                for k, v in vals.items():
                    setattr(cur, k, v)
    await db.flush()
    return created, updated


async def replace_children(db: AsyncSession, project_code: str, milestones=None, issues=None):
    """Replace milestones/issues for a project from an import (imports are authoritative for these lists)."""
    row = await get_orm_project(db, project_code)
    if row is None:
        return
    if milestones is not None:
        row.milestones = [E.ProjectMilestone(name=m.name, planned_start=m.planned_start, planned_end=m.planned_end,
                                             actual_start=m.actual_start, actual_end=m.actual_end,
                                             completion_pct=m.completion_pct, depends_on=m.depends_on, weight=m.weight)
                          for m in milestones]
    if issues is not None:
        row.issues = [E.ProjectIssue(issue_type=i.issue_type, description=i.description, severity=i.severity,
                                     reported_date=i.reported_date, expected_resolution_date=i.expected_resolution_date,
                                     actual_resolution_date=i.actual_resolution_date, owner=i.owner, status=i.status,
                                     impact=i.impact) for i in issues]


async def upsert_snapshots(db: AsyncSession, project_code: str, snaps: list) -> int:
    """Insert/update monthly snapshots; if the newest snapshot is newer than existing ones, refresh the
    master row's latest values (only where the snapshot supplies a value; never overwrites with NULL)."""
    row = await get_orm_project(db, project_code)
    if row is None:
        return 0
    by_month = {s.snapshot_month: s for s in row.snapshots}
    n = 0
    for s in snaps:
        vals = dict(physical_progress_pct=s.physical_progress_pct, financial_progress_pct=s.financial_progress_pct,
                    cumulative_expenditure_crore=s.cumulative_expenditure_crore, revised_cost_crore=s.revised_cost_crore,
                    revised_end_date=s.revised_end_date, status=s.status, issues_text=s.issues_text,
                    source=s.source, source_document=s.source_document, origin=s.origin)
        cur = by_month.get(s.snapshot_month)
        if cur is None:
            new = E.ProjectSnapshot(snapshot_month=s.snapshot_month, **vals)
            row.snapshots.append(new)
            by_month[s.snapshot_month] = new
        else:
            for k, v in vals.items():
                setattr(cur, k, v)
        n += 1
    newest = max(by_month) if by_month else None
    if newest is not None:
        cur = by_month[newest]
        for k in ("physical_progress_pct", "financial_progress_pct", "cumulative_expenditure_crore", "revised_cost_crore", "revised_end_date"):
            v = getattr(cur, k)
            if v is not None:
                setattr(row, k, v)
    return n


async def load_orm_projects(db: AsyncSession) -> list:
    """All projects with children eagerly loaded (async sessions cannot lazy-load)."""
    res = await db.execute(select(E.Project).options(*_LOAD))
    return list(res.scalars().unique().all())
