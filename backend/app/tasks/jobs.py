"""Background jobs. Only jobs with real implementations are registered."""
import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.services.analysis import recompute_all
from app.services.repository import load_orm_projects
from app.tasks.celery_app import celery_app


async def _recompute():
    async with SessionLocal() as db:
        n = await recompute_all(db, await load_orm_projects(db))
        await db.commit()
        return n


@celery_app.task(name="pragati.calculate_project_risk")
def calculate_project_risk() -> int:
    """Recompute risk for every project, persist RiskSnapshots and raise alerts on band worsening."""
    return asyncio.run(_recompute())


@celery_app.task(name="pragati.train_delay_model")
def train_delay_model() -> dict:
    """Train the delay model iff enough real labelled history exists; otherwise report why not."""
    from app.core.config import settings
    from app.ml.delay_model import train
    from app.services.repository import load_projects

    async def _go():
        async with SessionLocal() as db:
            ps = await load_projects(db, origin=None)
            real = [p for p in ps if p.origin.value in ("OFFICIAL", "IMPORTED", "USER_UPLOADED")]
            return train(real, settings.MODEL_PATH).__dict__
    return asyncio.run(_go())
