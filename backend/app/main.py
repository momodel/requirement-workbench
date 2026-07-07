from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import AppSettings, DEFAULT_SETTINGS
from .db import init_db
from .routes.artifacts import router as artifacts_router
from .routes.chat import router as chat_router
from .routes.chat_images import router as chat_images_router
from .routes.knowledge_base import router as knowledge_base_router
from .routes.messages import router as messages_router
from .routes.projects import router as projects_router
from .routes.readiness import router as readiness_router
from .routes.settings import router as settings_router
from .routes.sources import router as sources_router
from .routes.state import router as state_router
from .routes.versions import router as versions_router
from .routes.wiki import router as wiki_router
from .services.agent_runtime import ClaudeAgentRuntime
from .services.audio_ingestion_orchestrator import AudioIngestionOrchestrator
from .services.audio_transcription_service import AudioTranscriptionService
from .services.artifact_generation import ArtifactGenerationService
from .services.chat_service import ChatService
from .services.docling_normalizer import DoclingNormalizer
from .services.evidence_runtime import QdrantLlamaIndexEvidenceRuntime
from .services.object_storage_service import ObjectStorageService
from .services.project_catalog import ProjectCatalog
from .services.project_state import ProjectStateService
from .services.runtime_contracts import AgentRuntime, EvidenceRuntime, WikiRuntime
from .services.seed_projects import ensure_seed_project
from .services.source_ingestion import SourceIngestionService
from .services.wiki_maintenance import WikiMaintainer
from .services.wiki_runtime import ClaudeWikiRuntime
from .services.wiki_store import WikiStore


@dataclass(slots=True)
class ServiceContainer:
    settings: AppSettings
    catalog: ProjectCatalog
    project_state: ProjectStateService
    docling_normalizer: DoclingNormalizer
    source_ingestion: SourceIngestionService
    object_storage: ObjectStorageService
    audio_transcription: AudioTranscriptionService
    audio_ingestion: AudioIngestionOrchestrator
    evidence_runtime: EvidenceRuntime
    wiki_runtime: WikiRuntime
    agent_runtime: AgentRuntime
    artifact_generation: ArtifactGenerationService
    chat_service: ChatService


def build_services(settings: AppSettings) -> ServiceContainer:
    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)
    docling_normalizer = DoclingNormalizer()
    source_ingestion = SourceIngestionService(
        settings,
        docling_normalizer=docling_normalizer,
    )
    object_storage = ObjectStorageService(settings)
    audio_transcription = AudioTranscriptionService(settings)
    evidence_runtime = QdrantLlamaIndexEvidenceRuntime(settings, catalog=catalog)
    audio_ingestion = AudioIngestionOrchestrator(
        settings=settings,
        catalog=catalog,
        object_storage=object_storage,
        audio_transcription=audio_transcription,
        evidence_runtime=evidence_runtime,
    )
    agent_runtime = ClaudeAgentRuntime(settings, evidence_runtime=evidence_runtime)
    wiki_store = WikiStore(settings)
    wiki_maintainer = WikiMaintainer(
        settings,
        store=wiki_store,
        catalog=catalog,
        evidence_runtime=evidence_runtime,
    )
    wiki_runtime = ClaudeWikiRuntime(
        settings,
        catalog=catalog,
        store=wiki_store,
        sdk_readiness_probe=agent_runtime.get_readiness,
        maintainer=wiki_maintainer,
    )
    agent_runtime.attach_wiki_runtime(wiki_runtime)
    artifact_generation = ArtifactGenerationService(settings)
    chat_service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=evidence_runtime,
        agent_runtime=agent_runtime,
        artifact_generation=artifact_generation,
        wiki_runtime=wiki_runtime,
    )
    return ServiceContainer(
        settings=settings,
        catalog=catalog,
        project_state=project_state,
        docling_normalizer=docling_normalizer,
        source_ingestion=source_ingestion,
        object_storage=object_storage,
        audio_transcription=audio_transcription,
        audio_ingestion=audio_ingestion,
        evidence_runtime=evidence_runtime,
        wiki_runtime=wiki_runtime,
        agent_runtime=agent_runtime,
        artifact_generation=artifact_generation,
        chat_service=chat_service,
    )


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    import asyncio

    services = app.state.services
    settings = services.settings
    init_db(settings)
    ensure_seed_project(settings)
    services.wiki_runtime.attach_event_loop(asyncio.get_running_loop())
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
    app.include_router(settings_router)
    app.include_router(sources_router)
    app.include_router(knowledge_base_router)
    app.include_router(messages_router)
    app.include_router(state_router)
    app.include_router(chat_router)
    app.include_router(chat_images_router)
    app.include_router(versions_router)
    app.include_router(artifacts_router)
    app.include_router(wiki_router)

    return app


app = create_app()
