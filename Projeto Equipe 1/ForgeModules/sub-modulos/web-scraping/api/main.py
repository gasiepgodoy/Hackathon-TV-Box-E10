"""Aplicação FastAPI principal."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent.chain import AcademicAgent
from api.routes import agent, dados, status
from config.settings import Settings, get_settings
from database.connection import close_db, init_db
from shared.cache import CacheService
from shared.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

    await init_db()

    cache = CacheService(settings)
    await cache.connect()
    app.state.cache = cache
    app.state.agent = AcademicAgent(settings)

    yield

    await cache.close()
    await close_db()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Assistente acadêmico local com coleta, RAG e dashboard.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(status.router)
    app.include_router(dados.router)
    app.include_router(agent.router)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def dashboard() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    return app


app = create_app()
