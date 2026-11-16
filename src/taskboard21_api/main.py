"""FastAPI entry point for taskboard21-api."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import __version__
from .logging_config import configure_logging
from .metrics import MetricsMiddleware
from .tasks.router import router as tasks_router
from .tasks.store import StorageUnavailableError, TaskStore, get_task_store
from .tracing import configure_tracing, tracing_enabled

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
if tracing_enabled():
    configure_tracing()

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Apply the task schema at startup; start anyway when the database is down."""
    try:
        get_task_store().ensure_schema()
    except StorageUnavailableError:
        logger.warning("schema_deferred")
    yield


app = FastAPI(title="taskboard21-api", version=__version__, lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
if tracing_enabled():
    FastAPIInstrumentor.instrument_app(app)
app.include_router(tasks_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — returns 200 as long as the process is responding."""
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse)
def ready(store: TaskStore = Depends(get_task_store)) -> HealthResponse | JSONResponse:  # noqa: B008
    """Readiness probe — 200 when the task database answers, else 503."""
    if store.ping():
        return HealthResponse(status="ready")
    return JSONResponse(status_code=503, content={"status": "not ready"})


@app.get("/ping")
def ping() -> dict[str, str]:
    """Simple ping endpoint."""
    return {"pong": "taskboard21-api"}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
