from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routes.artifacts import router as artifacts_router
from .routes.chat import router as chat_router
from .routes.projects import router as projects_router
from .routes.sources import router as sources_router
from .routes.state import router as state_router
from .routes.versions import router as versions_router


def create_app() -> FastAPI:
    app = FastAPI(title="Requirement Workbench API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    @app.get("/api/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects_router)
    app.include_router(sources_router)
    app.include_router(state_router)
    app.include_router(chat_router)
    app.include_router(versions_router)
    app.include_router(artifacts_router)

    return app


app = create_app()
