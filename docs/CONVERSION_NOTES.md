# Conversion notes (technical foundation reuse)

Reused from the previous codebase (technical infrastructure only): JWT + bcrypt + refresh-cookie pattern
(`core/security.py`), sliding-window rate limiter, async SQLAlchemy session setup, Alembic layout, Celery/Redis
wiring, Docker/nginx layout, Axios refresh-on-401 interceptor and auth context pattern.

Not carried over: every domain model, schema, service, route, analytic, dataset, frontend page/component and
seed file of the previous product; its `.env` (contained live credentials - rotate them), hard-coded compose secrets,
and the WebSocket/real-time layer (no PRAGATI feature currently needs it: NOT IMPLEMENTED).
