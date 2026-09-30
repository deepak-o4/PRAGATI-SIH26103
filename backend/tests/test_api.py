"""API integration tests (pytest + pytest-asyncio + httpx). REQUIRES the packages in requirements.txt.
NOTE: these were written but NOT executed in the authoring sandbox (FastAPI/SQLAlchemy were not installable offline)."""
import os

os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("REFRESH_SECRET_KEY", "y" * 40)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import security
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import entities as E


@pytest_asyncio.fixture(autouse=True)
async def db():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        for name, role in (("admin", E.Role.ADMIN), ("viewer", E.Role.VIEWER), ("pm", E.Role.PROJECT_MANAGER)):
            s.add(E.User(name=name, email=f"{name}@example.org", password_hash=security.get_password_hash("correct-horse-1"), role=role))
        await s.commit()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def login(client, who):
    r = await client.post("/api/v1/auth/login", json={"email": f"{who}@example.org", "password": "correct-horse-1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


@pytest.mark.asyncio
async def test_auth_required_and_bad_login(client):
    assert (await client.get("/api/v1/projects")).status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": "admin@example.org", "password": "wrong"})
    assert r.status_code == 401 and "error" in r.json() and "Traceback" not in r.text


@pytest.mark.asyncio
async def test_actions_accepts_string_uuid_subject(client):
    h = await login(client, "admin")
    r = await client.get("/api/v1/actions", headers=h)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_rbac_viewer_cannot_write(client):
    h = await login(client, "viewer")
    r = await client.post("/api/v1/projects", json={"project_code": "P1", "project_name": "x"}, headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_project_crud_validation_and_risk(client):
    h = await login(client, "pm")
    bad = await client.post("/api/v1/projects", json={"project_code": "P1", "project_name": "x", "physical_progress_pct": 120}, headers=h)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"
    ok = await client.post("/api/v1/projects", json={"project_code": "P1", "project_name": "Bridge", "original_cost_crore": 100,
                           "revised_cost_crore": 150, "start_date": "2022-01-01", "original_end_date": "2025-01-01",
                           "physical_progress_pct": 40}, headers=h)
    assert ok.status_code == 201
    dup = await client.post("/api/v1/projects", json={"project_code": "P1", "project_name": "Again"}, headers=h)
    assert dup.status_code == 409
    got = await client.get("/api/v1/projects/P1", headers=h)
    assert got.status_code == 200 and got.json()["cost_overrun_pct"] == 50.0
    risk = await client.get("/api/v1/projects/P1/risk", headers=h)
    assert risk.json()["current"]["contributors"]
    bad_t = await client.patch("/api/v1/projects/P1", json={"status": "PLANNED"}, headers=h)
    assert bad_t.status_code == 409     # UNDER_CONSTRUCTION -> PLANNED not allowed


@pytest.mark.asyncio
async def test_ingestion_rejects_and_labels_origin(client):
    h = await login(client, "admin")
    csv = b"project_code,project_name,original_cost_crore\nA1,ok,100\nA2,neg,-4\n"
    r = await client.post("/api/v1/ingestion/projects", files={"file": ("p.csv", csv, "text/csv")}, data={"origin": "SYNTHETIC_DEMO"}, headers=h)
    assert r.status_code == 200
    rep = r.json()["report"]
    assert rep["accepted"] == 1 and len(rep["rejected"]) == 1
    hh = await login(client, "pm")
    r2 = await client.post("/api/v1/ingestion/projects", files={"file": ("p.csv", csv, "text/csv")}, data={"origin": "OFFICIAL"}, headers=hh)
    assert r2.status_code == 403        # only admins may label OFFICIAL


@pytest.mark.asyncio
async def test_dashboard_and_copilot(client):
    h = await login(client, "admin")
    csv = b"project_code,project_name,sector,original_cost_crore,revised_cost_crore\nA1,ok,Rail,100,130\n"
    await client.post("/api/v1/ingestion/projects", files={"file": ("p.csv", csv, "text/csv")}, data={"origin": "SYNTHETIC_DEMO"}, headers=h)
    d = (await client.get("/api/v1/dashboard", headers=h)).json()
    assert d["kpis"]["total_projects"] == 1 and d["demo_data_present"] is True
    c = await client.post("/api/v1/copilot", json={"question": "Which projects have the highest cost overruns?"}, headers=h)
    assert c.json()["intent"] == "cost_overrun"
