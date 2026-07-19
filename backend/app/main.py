from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import auth, project, paper


def create_app() -> FastAPI:
    app = FastAPI(
        title="ResearchPilot API",
        description="学术论文检索与管理平台",
        version="0.1.0",
    )

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

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
