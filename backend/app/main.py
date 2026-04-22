from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import AppSettings, DEFAULT_SETTINGS
from .db import init_db
from .routes.artifacts import router as artifacts_router
from .routes.chat import router as chat_router
from .routes.knowledge_base import router as knowledge_base_router
from .routes.messages import router as messages_router
from .routes.projects import router as projects_router
from .routes.readiness import router as readiness_router
from .routes.sources import router as sources_router
from .routes.state import router as state_router
from .routes.versions import router as versions_router
from .services.agent_runtime import ClaudeAgentRuntime
from .services.artifact_generation import ArtifactGenerationService
from .services.chat_service import ChatService
from .services.evidence_runtime import QdrantLlamaIndexEvidenceRuntime
from .services.notebooklm_service import NotebookLMService
from .services.project_catalog import ProjectCatalog
from .services.project_state import ProjectStateService
from .services.runtime_contracts import AgentRuntime, EvidenceRuntime
from .services.seed_projects import ensure_seed_project
from .services.source_ingestion import SourceIngestionService


@dataclass(slots=True)
class ServiceContainer:
    settings: AppSettings
    catalog: ProjectCatalog
    project_state: ProjectStateService
    source_ingestion: SourceIngestionService
    notebooklm: NotebookLMService
    evidence_runtime: EvidenceRuntime
    agent_runtime: AgentRuntime
    artifact_generation: ArtifactGenerationService
    chat_service: ChatService


def build_services(settings: AppSettings) -> ServiceContainer:
    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)
    source_ingestion = SourceIngestionService(settings)
    notebooklm = NotebookLMService(settings)
    evidence_runtime = QdrantLlamaIndexEvidenceRuntime(settings, catalog=catalog)
    agent_runtime = ClaudeAgentRuntime(settings)
    artifact_generation = ArtifactGenerationService(settings)
    chat_service = ChatService(
        catalog=catalog,
        project_state=project_state,
        notebooklm=notebooklm,
        agent_runtime=agent_runtime,
        artifact_generation=artifact_generation,
    )
    return ServiceContainer(
        settings=settings,
        catalog=catalog,
        project_state=project_state,
        source_ingestion=source_ingestion,
        notebooklm=notebooklm,
        evidence_runtime=evidence_runtime,
        agent_runtime=agent_runtime,
        artifact_generation=artifact_generation,
        chat_service=chat_service,
    )


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    settings = app.state.services.settings
    init_db(settings)
    ensure_seed_project(settings)
    yield


def create_app(settings: AppSettings = DEFAULT_SETTINGS) -> FastAPI:
    app = FastAPI(
        title="Requirement Workbench API",
        version="0.2.0",
        lifespan=app_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    services = build_services(settings)
    app.state.services = services

    @app.get("/api/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects_router)
    app.include_router(readiness_router)
    app.include_router(knowledge_base_router)
    app.include_router(sources_router)
    app.include_router(messages_router)
    app.include_router(state_router)
    app.include_router(chat_router)
    app.include_router(versions_router)
    app.include_router(artifacts_router)

    return app


app = create_app()
