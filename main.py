"""
Script2API — entrypoint da aplicação FastAPI.

Responsabilidades:
  - Criação e configuração do app FastAPI
  - CORS middleware com origens da config
  - Startup/shutdown do pool asyncpg
  - Registro de todos os routers
  - Handler global de erros
  - Endpoints raiz e versão
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.version import __version__
from app.db import init_db, init_pool, close_pool
from app.routers import auth, billing, convert, health

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if not settings.is_production else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("script2api")


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger.info("🚀 Script2API iniciando (env=%s)…", settings.app_env)
    await init_pool()
    await init_db()
    logger.info("✅ Pool conectado e tabelas verificadas.")
    yield
    await close_pool()
    logger.info("🛑 Pool encerrado. Shutdown completo.")


# ── Application factory ────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="Script2API",
        description=(
            "Transforme qualquer script Python em uma API REST documentada — "
            "sem boilerplate, sem configuração."
        ),
        version=__version__,
        contact={"name": "Script2API", "url": "https://github.com/your-username/script2api"},
        license_info={"name": "MIT"},
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Static files (frontend) ─────────────────────────────────────────────
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

    # ── Routers ─────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(convert.router)
    app.include_router(billing.router)

    # ── Exception Handlers ────────────────────────────────────────────────────
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "path": str(request.url.path),
                "status_code": exc.status_code,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Erro não tratado em %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Erro interno do servidor. Tente novamente mais tarde.",
                "path": str(request.url.path),
                "status_code": 500,
            },
        )

    return app


app = create_app()


# ── Root → Landing Page ──────────────────────────────────────────────────────
@app.get("/", tags=["meta"], include_in_schema=False)
async def root():
    """Redireciona para a landing page (SPA)."""
    return RedirectResponse(url="/static/landing.html")


@app.get("/app", tags=["meta"], include_in_schema=False)
async def app_page():
    """Redireciona para o app principal (dashboard)."""
    return RedirectResponse(url="/static/index.html")


@app.get("/api", tags=["meta"], summary="Informações do serviço")
async def api_info():
    """Retorna metadados da API (JSON)."""
    return {
        "service": "Script2API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "status": "online",
        "env": settings.app_env,
    }


@app.get("/version", tags=["meta"], summary="Versão da API")
async def version():
    return {"version": __version__, "env": settings.app_env}


# ── Dev entrypoint ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=not settings.is_production,
        log_level="info",
    )
