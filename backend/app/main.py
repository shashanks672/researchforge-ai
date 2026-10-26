import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.documents import router as documents_router
from app.api.execution import router as execution_router
from app.api.sessions import router as sessions_router
from app.api.system import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import DATABASE_UNAVAILABLE, build_engine
from app.documents.service import Documents
from app.research.supervisor import ResearchSupervisor


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine: AsyncEngine | None = None
        app.state.db_sessions = None
        if config.database_url is not None:
            engine = build_engine(config.database_url.get_secret_value())
            app.state.db_sessions = async_sessionmaker(engine, expire_on_commit=False)
        app.state.research = ResearchSupervisor(app.state.db_sessions, config)
        app.state.settings = config
        await app.state.research.open()
        app.state.documents = Documents(app.state.db_sessions, config)
        app.state.research.documents = app.state.documents
        await app.state.documents.open(app.state.research.lock_connection is not None)
        try:
            yield
        finally:
            await app.state.research.close()
            await app.state.documents.close()
            if engine is not None:
                await engine.dispose()

    application = FastAPI(title="ResearchForge AI", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @application.middleware("http")
    async def request_metadata(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid4())
        started = perf_counter()
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin is not None and origin not in config.cors_origins:
                return JSONResponse(status_code=403, content={"detail": "Untrusted origin"})
            expected = (
                "application/octet-stream"
                if request.url.path == "/api/v1/documents/upload"
                else "application/json"
            )
            if request.headers.get("content-type", "").split(";")[0] != expected:
                return JSONResponse(status_code=415, content={"detail": f"Use {expected}"})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        logging.getLogger("researchforge.http").info(
            "http_request",
            extra={
                "method": request.method,
                "status_code": response.status_code,
                "latency_ms": round((perf_counter() - started) * 1000, 2),
                "request_id": request_id,
            },
        )
        return response

    application.include_router(router)
    application.include_router(sessions_router)
    application.include_router(execution_router)
    application.include_router(documents_router)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logging.getLogger("researchforge.db").warning("database_request_failed")
        return JSONResponse(status_code=503, content={"detail": DATABASE_UNAVAILABLE})

    return application


app = create_app()
