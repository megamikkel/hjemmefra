from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from hjemmefra import __version__
from hjemmefra.api.routers import admin, catalog, feedback, households, pantry, plans
from hjemmefra.config import Settings, settings as default_settings
from hjemmefra.core.errors import ConflictError, Forbidden, HjemmefraError, NotFound
from hjemmefra.core.logging import configure_logging
from hjemmefra.persistence.db import Base, make_engine, make_session_factory


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or default_settings
    configure_logging(cfg.log_level)
    engine = make_engine(cfg.database_url)
    Base.metadata.create_all(engine)  # dev convenience; production uses alembic migrations
    factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if cfg.seed_demo:
            from hjemmefra.demo.seed import seed_demo
            with factory() as s:
                seed_demo(s, api_key=cfg.demo_api_key)
                s.commit()
        yield

    app = FastAPI(title="Hjemmefra API", version=__version__, lifespan=lifespan,
                  description="Deterministic meal-plan and grocery optimization for Danish households. "
                              "All prices and totals are computed by code; no LLM is authoritative for numbers.")
    app.state.session_factory = factory
    app.state.engine = engine
    app.state.admin_api_key = cfg.admin_api_key
    for r in (households.router, catalog.router, pantry.router, plans.router, feedback.router, admin.router):
        app.include_router(r)

    @app.exception_handler(HjemmefraError)
    async def _domain_error(_, exc: HjemmefraError):
        status = {NotFound: 404, Forbidden: 403, ConflictError: 409}.get(type(exc), 400)
        return JSONResponse(status_code=status, content={"code": exc.code, "detail": str(exc)})

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
