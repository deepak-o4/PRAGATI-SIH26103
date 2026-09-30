import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings

logger = logging.getLogger("pragati.db")
_sqlite = settings.DATABASE_URL.startswith("sqlite")
if _sqlite:
    kw = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in settings.DATABASE_URL:
        kw["poolclass"] = StaticPool
    engine = create_async_engine(settings.DATABASE_URL, **kw)
else:
    engine = create_async_engine(settings.DATABASE_URL, pool_size=10, max_overflow=10, pool_recycle=1800, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db():
    async with SessionLocal() as session:
        yield session
