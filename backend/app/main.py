import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, data, portfolio, projects
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pragati")

app = FastAPI(title=f"{settings.APP_NAME} API", version="1.0.0",
              description="Project Assessment, Risk & Governance Analytics for Transformation & Infrastructure")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])


def _err(status_code: int, code: str, message: str, request_id: str, details=None):
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "request_id": request_id, "details": details}})


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    start = time.time()
    request.state.request_id = rid
    try:
        response = await call_next(request)
    except Exception:  # never leak a stack trace to clients
        log.exception("unhandled error rid=%s path=%s", rid, request.url.path)
        return _err(500, "internal_error", "An unexpected error occurred.", rid)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    log.info("%s %s -> %s %.0fms rid=%s", request.method, request.url.path, response.status_code, (time.time() - start) * 1000, rid)
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exc(request: Request, exc: StarletteHTTPException):
    return _err(exc.status_code, f"http_{exc.status_code}", str(exc.detail), getattr(request.state, "request_id", "-"))


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return _err(422, "validation_error", "The request contains invalid values.", getattr(request.state, "request_id", "-"), details)


P = settings.API_V1_STR
for r in (auth.router, projects.router, portfolio.router, data.router):
    app.include_router(r, prefix=P)


@app.get(f"{P}/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
