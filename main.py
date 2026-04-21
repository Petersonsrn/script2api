"""
Script2API — Turn any Python script into a REST API instantly.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db import init_db, init_pool, close_pool
from app.routers import convert, health
from app.routers import auth


# ------------------------------------------------------------------ #
#  Lifespan (startup / shutdown)                                       #
# ------------------------------------------------------------------ #
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_pool()
    await init_db()
    yield
    # Shutdown
    await close_pool()


# ------------------------------------------------------------------ #
#  Application factory                                                 #
# ------------------------------------------------------------------ #
def create_app() -> FastAPI:
    app = FastAPI(
        title="Script2API",
        description=(
            "Paste or upload any Python script and instantly get a fully "
            "documented REST API — no boilerplate needed."
        ),
        version="1.1.0",
        contact={"name": "Script2API", "url": "https://github.com/your-username/script2api"},
        license_info={"name": "MIT"},
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ---- CORS ---- #
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Routers ---- #
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(convert.router)
    
    from app.routers import billing
    app.include_router(billing.router)

    return app


app = create_app()


# ------------------------------------------------------------------ #
#  Root                                                                #
# ------------------------------------------------------------------ #
@app.get("/", tags=["root"])
async def root():
    return {
        "service": "Script2API",
        "version": "1.1.0",
        "docs": "/docs",
        "status": "online",
    }


# ------------------------------------------------------------------ #
#  Dev entrypoint                                                      #
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )
