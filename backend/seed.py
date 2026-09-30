"""Create the first admin and optionally load a project dataset.

  python seed.py --admin-email you@example.org            # prompts for password (or ADMIN_PASSWORD env)
  python seed.py --demo                                    # load data/sample as SYNTHETIC_DEMO
  python seed.py --paimana /path/to/PRAGATI-PAIMANA-real-world-starter-dataset.csv
"""
import argparse
import asyncio
import getpass
import os
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.core import security
from app.db.session import SessionLocal
from app.domain.types import DataOrigin
from app.ingestion import loader
from app.models import entities as E
from app.services.analysis import recompute_all
from app.services.repository import load_orm_projects, replace_children, upsert_projects, upsert_snapshots

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"


async def main(args):
    async with SessionLocal() as db:
        if args.admin_email:
            pw = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Admin password (min 10 chars): ")
            if len(pw) < 10:
                raise SystemExit("password must be at least 10 characters")
            if not (await db.execute(select(E.User).where(E.User.email == args.admin_email.lower()))).scalars().first():
                db.add(E.User(name="Administrator", email=args.admin_email.lower(), password_hash=security.get_password_hash(pw), role=E.Role.SUPER_ADMIN))
                print("created SUPER_ADMIN", args.admin_email)
        if args.demo:
            rd = lambda n: (SAMPLE / n).read_text(encoding="utf-8")  # noqa: E731
            projects, r1 = loader.ingest_projects(rd("projects.csv"), DataOrigin.SYNTHETIC_DEMO)
            codes = {p.project_code for p in projects}
            sn, r2 = loader.ingest_snapshots(rd("project_snapshots.csv"), codes, DataOrigin.SYNTHETIC_DEMO)
            ms, r3 = loader.ingest_milestones(rd("project_milestones.csv"), codes)
            iss, r4 = loader.ingest_issues(rd("project_issues.csv"), codes)
            for r in (r1, r2, r3, r4):
                if r.rejected:
                    raise SystemExit(f"demo data rejected rows: {r.kind}: {r.rejected[:3]}")
            ds = E.DataSource(source_name="PRAGATI synthetic demo generator", source_document="data/sample/*.csv",
                              source_date=date.today(), origin=DataOrigin.SYNTHETIC_DEMO,
                              record_counts={"projects": len(projects)}, report={"note": "SYNTHETIC_DEMO - not official data"})
            db.add(ds)
            await db.flush()
            await upsert_projects(db, projects, ds.id)
            await db.flush()
            for code, s in sn.items():
                await upsert_snapshots(db, code, s)
            for code in codes:
                await replace_children(db, code, milestones=ms.get(code, []), issues=iss.get(code, []))
            await db.flush()
            n = await recompute_all(db, await load_orm_projects(db))
            print(f"loaded {len(projects)} SYNTHETIC_DEMO projects; risk computed for {n}")
        if args.paimana:
            path = Path(args.paimana).expanduser().resolve()
            if not path.is_file():
                raise SystemExit(f"PAIMANA dataset not found: {path}")
            source = path.read_text(encoding="utf-8-sig")
            projects, r1 = loader.ingest_projects(source, DataOrigin.IMPORTED)
            codes = {p.project_code for p in projects}
            snapshots, r2 = loader.ingest_snapshots(source, codes, DataOrigin.IMPORTED)
            if r1.rejected or r2.rejected:
                raise SystemExit(f"PAIMANA data rejected rows: projects={r1.rejected[:3]}, snapshots={r2.rejected[:3]}")
            ds = E.DataSource(source_name="PRAGATI PAIMANA real-world starter dataset",
                              source_document=path.name, source_date=date.today(), origin=DataOrigin.IMPORTED,
                              record_counts={"projects": len(projects), "snapshots": r2.accepted},
                              report={"note": "Real-world starter dataset; not a complete PAIMANA database"})
            db.add(ds)
            await db.flush()
            await upsert_projects(db, projects, ds.id)
            await db.flush()
            for code, rows in snapshots.items():
                await upsert_snapshots(db, code, rows)
            n = await recompute_all(db, await load_orm_projects(db))
            print(f"loaded {len(projects)} imported PAIMANA starter projects; risk computed for {n}")
        await db.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-email")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--paimana", help="path to the real-world PAIMANA starter CSV")
    asyncio.run(main(ap.parse_args()))
