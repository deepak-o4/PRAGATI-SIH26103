# PRAGATI

**Project Assessment, Risk & Governance Analytics for Transformation & Infrastructure**

PRAGATI is an infrastructure project monitoring, risk-intelligence and decision-support platform. It ingests
project-level data (modelled on the columns published by MoSPI PAIMANA), keeps a monthly history per project,
and computes cost, schedule and progress analytics, an explainable risk score, completion forecasts, what-if
scenarios, portfolio dashboards, bottleneck analysis, reports and a data-grounded Copilot.

> **Data status.** This repository ships **no official data**. `data/sample/` holds a deterministic
> **SYNTHETIC_DEMO** dataset (`scripts/generate_demo_data.py`). It is labelled in the database (`origin`),
> in the UI (Demo Data banner) and in reports. Real PAIMANA-style exports can be imported from the Data page.
> The ingestion column aliases are a best-effort mapping and must be checked against a real export.

## Architecture

```
CSV/XLSX ─▶ validation ─▶ normalisation ─▶ dedup ─▶ Project + ProjectSnapshot
                                                     │
        feature engineering ◀────────────────────────┤
        risk engine ─▶ RiskSnapshot (audited) ─▶ alerts
        forecasting / scenarios / delay model
                                                     ▼
              REST API (FastAPI)  ─▶  React dashboard, Copilot, reports
```

* `backend/app/domain` – framework-free types, status state machine
* `backend/app/analytics` – cost / schedule / progress metrics, portfolio aggregation, bottlenecks, data quality
* `backend/app/risk` – transparent weighted risk engine with per-factor explanations and historical reconstruction
* `backend/app/forecasting`, `scenarios` – linear-trend completion forecast; what-if simulation
* `backend/app/ml` – delay-prediction pipeline (real-outcome labels only; deterministic fallback)
* `backend/app/copilot` – rule-routed structured analytics + TF-IDF document retrieval (LLM optional, off by default)
* `backend/app/ingestion`, `reports` – importers and PDF/CSV/XLSX generation
* `backend/app/api`, `models`, `services`, `tasks` – FastAPI, SQLAlchemy 2 (async), Celery jobs
* `frontend/` – React 18 + Vite, Recharts, Leaflet

## Risk engine

Score = Σ weightᵢ × subscoreᵢ (0–100). Default weights are **initial engineering assumptions, not validated
government weights**: schedule 25, cost 20, progress 25, milestone 15, trend 10, data quality 5 (issues 0 – informational;
raise via config). Override with `RISK_WEIGHTS_JSON`. Bands: 0–30 STABLE, 31–60 WATCH, 61–80 WARNING, 81–100 CRITICAL.
Components that cannot be assessed (missing data) contribute 0 and are shown as `n/a`; the API reports the assessable
weight share. Each computation is stored in `risk_snapshots` with version, weights and factors.

Schedule delay separates the **official revised slip** (revised − original end date) from **overdue** days beyond the
revised date. The PRAGATI **forecast** is always shown separately from the official revised date.
Expenditure-ahead-of-progress is an analytical review indicator only, never a finding of misuse.

## ML

`app/ml/delay_model.py` builds features per (project, snapshot) from information available at that time and labels from
*later real observations* (official end date pushed out >30 days). It **refuses to train** below 300 labelled rows /
40 per class and otherwise serves a deterministic, uncalibrated fallback derived from the risk score, clearly labelled
`fallback-rule-v1`. No trained model is shipped. Explanations use feature ablation against the training mean
(**SHAP is not implemented**). Synthetic demo data must not be used to claim model performance.

## Copilot

Deterministic intent router over computed analytics (critical projects, overruns, stalled, delays by state, risk
explanation, imbalance, sector risk, deadlines, compare, project summary). Uploaded documents are searched with TF-IDF
when no analytic intent matches. Unsupported questions are declined, not guessed. An LLM narrator hook exists but no
provider is wired in (**LLM integration NOT implemented**).

## Data model

`users`, `projects`, `project_snapshots`, `project_milestones`, `project_issues`, `project_documents`, `risk_snapshots`,
`forecasts`, `scenarios`, `action_items`, `alerts`, `audit_logs`, `data_sources`. Not created (deliberately):
`ProjectDependency` (milestone `depends_on` is a name reference) and `ProjectLocation` (latitude/longitude on `projects`).

## Installation & running locally

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # run twice; set SECRET_KEY and REFRESH_SECRET_KEY

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
ADMIN_PASSWORD='choose-a-long-password' python seed.py --admin-email you@example.org --demo
uvicorn app.main:app --reload            # API on :8000, docs at /docs

cd ../frontend && npm install && npm run dev   # UI on :5173 (proxies /api)
```

Docker: set `SECRET_KEY`, `REFRESH_SECRET_KEY`, `POSTGRES_PASSWORD` in `.env`, then `docker compose up --build`
(UI on :8080). Run `seed.py` inside the backend container to create the admin user.

## Environment variables

See `.env.example`. Secrets have **no defaults**; the app refuses to start with keys shorter than 32 characters.

## Testing

```bash
cd backend
python -m unittest discover -s tests -t .        # domain/analytics/risk/forecast/ingestion/copilot/reports/ML (58 tests)
pytest tests/test_api.py                          # API tests (need requirements.txt installed)
cd ../frontend && npm test && npm run lint && npm run build
```

## Roles

SUPER_ADMIN, ADMIN, PROGRAM_MANAGER, PROJECT_MANAGER (write), ANALYST (scenarios, documents), REVIEWER, VIEWER (read).
Only administrators may label imports `OFFICIAL`.

## Security notes

JWT access tokens (15 min) + HttpOnly refresh cookie, bcrypt hashing, login rate limiting (Redis if configured),
upload size/type limits with server-generated stored file names, no stack traces in responses, security headers,
strict CORS origins. Run behind HTTPS and set `COOKIE_SECURE=true` in production.

## Project structure

See the tree in this repository: `backend/`, `frontend/`, `data/{raw,processed,sample}`, `models/`, `docs/`, `scripts/`, `docker/`.
