from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.api import auth, project, paper, dashboard, llm, eval as eval_api, notes


def create_app() -> FastAPI:
    app = FastAPI(
        title="ResearchPilot API",
        description="学术论文检索与管理平台",
        version="0.1.0",
    )

    # Create any missing tables (idempotent) — alembic versions/ is empty,
    # so model-backed tables are materialized directly at startup.
    from app import models as _models  # noqa: F401 — register all models on Base

    Base.metadata.create_all(bind=engine)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
    app.include_router(project.router, prefix=settings.API_V1_PREFIX)
    app.include_router(paper.router, prefix=settings.API_V1_PREFIX)
    app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
    app.include_router(llm.router, prefix=settings.API_V1_PREFIX)
    app.include_router(eval_api.router, prefix=settings.API_V1_PREFIX)
    app.include_router(notes.router, prefix=settings.API_V1_PREFIX)

    # Preload the cross-encoder reranker in the background so the first chat
    # after startup isn't slowed by model loading. Never blocks startup.
    import threading

    def _preload_reranker():
        try:
            from app.services.hybrid_search import Reranker
            Reranker._get_model()
        except Exception:
            pass

    threading.Thread(target=_preload_reranker, daemon=True).start()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
