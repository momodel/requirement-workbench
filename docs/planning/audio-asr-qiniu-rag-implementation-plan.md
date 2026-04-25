# Audio ASR + Qiniu RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the missing audio normalization mainline so uploaded audio files move from project-local storage to Qiniu, then through Aliyun ASR, then into `normalized.md`, and finally into the existing `EvidenceRuntime` indexing/query flow with honest readiness and failure states.

**Architecture:** Keep the current `text-first RAG` design intact. Replace the current accidental “audio goes through synchronous Docling normalization” behavior with a thin async backend pipeline: `ObjectStorageService` uploads the local audio file to Qiniu, `AudioTranscriptionService` submits and polls Aliyun filetrans, and `AudioIngestionOrchestrator` writes `normalized.md`, updates source state, and triggers the existing evidence index path. Frontend changes stay source-centric: audio keeps an audio badge, but status, preview, and retrieval all remain text-based.

**Tech Stack:** FastAPI, SQLite, Pydantic, Qiniu Python SDK, Aliyun Python SDK Core, pytest, React, Vite, TypeScript, Vitest, Testing Library

---

## File Map

### Backend files

- Modify: `backend/requirements.txt`
  - Add Qiniu and Aliyun SDK dependencies.
- Modify: `backend/app/config.py`
  - Add project-local Qiniu and Aliyun settings.
- Modify: `backend/app/models.py`
  - Add `SourceProcessingJobRecord` plus new readiness fields.
- Modify: `backend/app/schema.sql`
  - Create `source_processing_jobs`.
- Modify: `backend/app/services/project_catalog.py`
  - Add job persistence and `update_source_normalization()`.
- Create: `backend/app/services/object_storage_service.py`
  - Encapsulate Qiniu upload and readiness.
- Create: `backend/app/services/audio_transcription_service.py`
  - Encapsulate Aliyun filetrans submission, polling, and markdown formatting.
- Create: `backend/app/services/audio_ingestion_orchestrator.py`
  - Coordinate upload, transcription, normalized text write, and indexing.
- Modify: `backend/app/services/source_ingestion.py`
  - Return `processing` for audio instead of trying Docling normalization.
- Modify: `backend/app/services/docling_normalizer.py`
  - Stop treating audio as a Docling-supported normalization target.
- Modify: `backend/app/routes/sources.py`
  - Schedule async audio processing and add audio-aware reindex behavior.
- Modify: `backend/app/routes/readiness.py`
  - Expose `object_storage` and `audio_transcription` readiness.
- Modify: `backend/app/main.py`
  - Wire the new backend services into the service container.

### Backend tests

- Create: `backend/tests/test_audio_pipeline_config.py`
  - Verify config parsing for Qiniu/Aliyun settings.
- Create: `backend/tests/test_audio_pipeline_schema.py`
  - Verify `source_processing_jobs` schema and catalog helpers.
- Create: `backend/tests/test_object_storage_service.py`
  - Verify Qiniu readiness and upload behavior.
- Create: `backend/tests/test_audio_transcription_service.py`
  - Verify Aliyun readiness, orchestration entrypoint, and markdown formatting.
- Create: `backend/tests/test_audio_ingestion_orchestrator.py`
  - Verify success, failure, and post-transcription indexing behavior.
- Create: `backend/tests/test_source_ingestion_audio.py`
  - Verify audio upload returns `processing` and bypasses Docling normalization.
- Modify: `backend/tests/test_api_flow.py`
  - Verify upload, readiness, reindex, and content preview semantics for audio.

### Frontend files

- Modify: `frontend/src/lib/types.ts`
  - Add `object_storage` and `audio_transcription` readiness fields.
- Modify: `frontend/src/lib/api.ts`
  - Normalize optional readiness fields to `null`.
- Modify: `frontend/src/App.tsx`
  - Poll the workbench while audio normalization/indexing is still active.
- Modify: `frontend/src/features/workbench/WorkbenchPage.tsx`
  - Rename source status labels around “标准化 / 入库”, render audio processing states, and show new provider cards.
- Modify: `frontend/src/App.test.tsx`
  - Add audio lifecycle and runtime dialog tests.

### Docs

- Modify: `docs/planning/fullstack-phase1-todo.md`
  - Mark the audio mainline complete after verification passes.

## Task 1: Add Config, Readiness Model, and Job Persistence Groundwork

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/schema.sql`
- Modify: `backend/app/services/project_catalog.py`
- Test: `backend/tests/test_audio_pipeline_config.py`
- Test: `backend/tests/test_audio_pipeline_schema.py`

- [ ] **Step 1: Write the failing config and schema tests**

```python
# backend/tests/test_audio_pipeline_config.py
from pathlib import Path

from app.config import AppSettings


def test_from_env_reads_qiniu_and_aliyun_audio_settings(monkeypatch, tmp_path: Path) -> None:
    root_dir = tmp_path / "repo"
    backend_dir = root_dir / "backend"
    backend_dir.mkdir(parents=True)
    (backend_dir / ".env.local").write_text(
        "\n".join(
            [
                "REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY=qiniu-ak",
                "REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY=qiniu-sk",
                "REQUIREMENT_WORKBENCH_QINIU_BUCKET=audio-bucket",
                "REQUIREMENT_WORKBENCH_QINIU_DOMAIN=https://audio.example.com/",
                "REQUIREMENT_WORKBENCH_ALIYUN_AK_ID=aliyun-ak",
                "REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET=aliyun-sk",
                "REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY=aliyun-app-key",
                "REQUIREMENT_WORKBENCH_ALIYUN_FILETRANS_REGION=cn-shanghai",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(root_dir / "backend")

    settings = AppSettings.from_env()

    assert settings.qiniu_access_key == "qiniu-ak"
    assert settings.qiniu_secret_key == "qiniu-sk"
    assert settings.qiniu_bucket == "audio-bucket"
    assert settings.qiniu_domain == "https://audio.example.com/"
    assert settings.aliyun_ak_id == "aliyun-ak"
    assert settings.aliyun_ak_secret == "aliyun-sk"
    assert settings.aliyun_app_key == "aliyun-app-key"
    assert settings.aliyun_filetrans_region == "cn-shanghai"
```

```python
# backend/tests/test_audio_pipeline_schema.py
import sqlite3
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.services.project_catalog import ProjectCatalog


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
    )


def test_init_db_creates_source_processing_jobs_table(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(source_processing_jobs)").fetchall()
        }
    finally:
        connection.close()

    assert {
        "id",
        "project_id",
        "source_id",
        "job_type",
        "status",
        "provider",
        "provider_job_id",
        "attempt_count",
        "last_error",
        "created_at",
        "updated_at",
    }.issubset(columns)


def test_project_catalog_can_create_and_update_source_processing_job(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    job = catalog.create_source_processing_job(
        project_id="project-1",
        source_id="source-1",
        job_type="audio_transcription",
        provider="ALIYUN_FILETRANS",
        status="processing",
        provider_job_id=None,
        attempt_count=1,
        last_error=None,
    )
    updated = catalog.update_source_processing_job(
        job_id=job.id,
        status="failed",
        provider_job_id="task-123",
        attempt_count=2,
        last_error="Aliyun timeout",
    )

    assert job.status == "processing"
    assert updated.status == "failed"
    assert updated.provider_job_id == "task-123"
    assert updated.attempt_count == 2
    assert updated.last_error == "Aliyun timeout"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_audio_pipeline_config.py backend/tests/test_audio_pipeline_schema.py -v
```

Expected:

- `AttributeError` because `AppSettings` has no audio provider fields
- `sqlite3.OperationalError` because `source_processing_jobs` does not exist
- `AttributeError` because `ProjectCatalog` has no job helper methods

- [ ] **Step 3: Add the config fields, readiness models, schema, and catalog helpers**

```python
# backend/app/config.py
@dataclass(slots=True)
class AppSettings:
    root_dir: Path
    data_dir: Path
    sqlite_dir: Path
    sqlite_path: Path
    projects_dir: Path
    qdrant_path: Path | None = None
    qdrant_url: str | None = None
    qdrant_collection_prefix: str = "project"
    evidence_backend: str = "qdrant_llamaindex"
    embedder_backend: str = "fastembed"
    evidence_query_timeout_seconds: float = 15.0
    evidence_top_k: int = 6
    claude_cli_path: str | None = None
    claude_model: str | None = None
    claude_max_turns: int = 6
    claude_stream_timeout_seconds: float = 90.0
    claude_structured_timeout_seconds: float = 45.0
    claude_artifact_timeout_seconds: float = 180.0
    default_timezone: str = "Asia/Shanghai"
    apimart_api_key: str | None = None
    apimart_base_url: str | None = None
    apimart_image_model: str | None = None
    public_api_base_url: str = "http://127.0.0.1:8001"
    image_generation_timeout_seconds: float = 240.0
    image_generation_request_timeout_seconds: float = 60.0
    image_generation_poll_interval_seconds: float = 2.0
    qiniu_access_key: str | None = None
    qiniu_secret_key: str | None = None
    qiniu_bucket: str | None = None
    qiniu_domain: str | None = None
    qiniu_key_prefix: str = "audio"
    audio_transcription_backend: str = "aliyun_filetrans"
    audio_transcription_timeout_seconds: float = 300.0
    audio_transcription_poll_interval_seconds: float = 2.0
    aliyun_ak_id: str | None = None
    aliyun_ak_secret: str | None = None
    aliyun_app_key: str | None = None
    aliyun_filetrans_region: str = "cn-shanghai"
```

```python
# backend/app/config.py
        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            sqlite_dir=sqlite_dir,
            sqlite_path=sqlite_path,
            projects_dir=projects_dir,
            qdrant_path=qdrant_path,
            qdrant_url=os.getenv("REQUIREMENT_WORKBENCH_QDRANT_URL"),
            qdrant_collection_prefix=os.getenv("REQUIREMENT_WORKBENCH_QDRANT_COLLECTION_PREFIX", "project"),
            evidence_backend=os.getenv("REQUIREMENT_WORKBENCH_EVIDENCE_BACKEND", "qdrant_llamaindex"),
            embedder_backend=os.getenv("REQUIREMENT_WORKBENCH_EMBEDDER_BACKEND", "fastembed"),
            evidence_query_timeout_seconds=float(
                os.getenv(
                    "REQUIREMENT_WORKBENCH_EVIDENCE_QUERY_TIMEOUT_SECONDS",
                    os.getenv("EVIDENCE_QUERY_TIMEOUT_SECONDS", "15"),
                )
            ),
            evidence_top_k=int(
                os.getenv(
                    "REQUIREMENT_WORKBENCH_EVIDENCE_TOP_K",
                    os.getenv("EVIDENCE_TOP_K", "6"),
                )
            ),
            claude_cli_path=os.getenv("CLAUDE_CODE_CLI_PATH"),
            claude_model=os.getenv("CLAUDE_MODEL"),
            claude_max_turns=int(os.getenv("CLAUDE_MAX_TURNS", "6")),
            claude_stream_timeout_seconds=float(os.getenv("CLAUDE_STREAM_TIMEOUT_SECONDS", "90")),
            claude_structured_timeout_seconds=float(os.getenv("CLAUDE_STRUCTURED_TIMEOUT_SECONDS", "45")),
            claude_artifact_timeout_seconds=float(os.getenv("CLAUDE_ARTIFACT_TIMEOUT_SECONDS", "180")),
            default_timezone=os.getenv("REQUIREMENT_WORKBENCH_TIMEZONE", "Asia/Shanghai"),
            apimart_api_key=os.getenv("APIMART_API_KEY"),
            apimart_base_url=os.getenv("APIMART_BASE_URL"),
            apimart_image_model=os.getenv("APIMART_IMAGE_MODEL"),
            public_api_base_url=os.getenv("PUBLIC_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/"),
            image_generation_timeout_seconds=float(os.getenv("IMAGE_GENERATION_TIMEOUT_SECONDS", "240")),
            image_generation_request_timeout_seconds=float(os.getenv("IMAGE_GENERATION_REQUEST_TIMEOUT_SECONDS", "60")),
            image_generation_poll_interval_seconds=float(os.getenv("IMAGE_GENERATION_POLL_INTERVAL_SECONDS", "2")),
            qiniu_access_key=os.getenv("REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY"),
            qiniu_secret_key=os.getenv("REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY"),
            qiniu_bucket=os.getenv("REQUIREMENT_WORKBENCH_QINIU_BUCKET"),
            qiniu_domain=os.getenv("REQUIREMENT_WORKBENCH_QINIU_DOMAIN"),
            qiniu_key_prefix=os.getenv("REQUIREMENT_WORKBENCH_QINIU_KEY_PREFIX", "audio"),
            audio_transcription_backend=os.getenv("REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_BACKEND", "aliyun_filetrans"),
            audio_transcription_timeout_seconds=float(
                os.getenv("REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS", "300")
            ),
            audio_transcription_poll_interval_seconds=float(
                os.getenv("REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_POLL_INTERVAL_SECONDS", "2")
            ),
            aliyun_ak_id=os.getenv("REQUIREMENT_WORKBENCH_ALIYUN_AK_ID"),
            aliyun_ak_secret=os.getenv("REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET"),
            aliyun_app_key=os.getenv("REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY"),
            aliyun_filetrans_region=os.getenv("REQUIREMENT_WORKBENCH_ALIYUN_FILETRANS_REGION", "cn-shanghai"),
        )
```

```python
# backend/app/models.py
class SourceProcessingJobRecord(BaseModel):
    id: str
    project_id: str
    source_id: str
    job_type: str
    status: str
    provider: str
    provider_job_id: str | None = None
    attempt_count: int
    last_error: str | None = None
    created_at: str
    updated_at: str


class ProjectReadiness(BaseModel):
    project_id: str
    claude: ProviderReadiness
    evidence: ProviderReadiness
    knowledge_base: KnowledgeBaseRecord | None = None
    object_storage: ProviderReadiness | None = None
    audio_transcription: ProviderReadiness | None = None


class GlobalReadiness(BaseModel):
    claude: ProviderReadiness
    evidence: ProviderReadiness
    object_storage: ProviderReadiness | None = None
    audio_transcription: ProviderReadiness | None = None
```

```sql
-- backend/app/schema.sql
CREATE TABLE IF NOT EXISTS source_processing_jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_job_id TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_processing_jobs_project_id ON source_processing_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_source_processing_jobs_source_id ON source_processing_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_source_processing_jobs_status ON source_processing_jobs(status);
```

```python
# backend/app/services/project_catalog.py
    def create_source_processing_job(
        self,
        *,
        project_id: str,
        source_id: str,
        job_type: str,
        provider: str,
        status: str,
        provider_job_id: str | None,
        attempt_count: int,
        last_error: str | None,
    ) -> SourceProcessingJobRecord:
        record = SourceProcessingJobRecord(
            id=f"job-{uuid.uuid4().hex[:10]}",
            project_id=project_id,
            source_id=source_id,
            job_type=job_type,
            status=status,
            provider=provider,
            provider_job_id=provider_job_id,
            attempt_count=attempt_count,
            last_error=last_error,
            created_at=now_iso(self.settings),
            updated_at=now_iso(self.settings),
        )
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO source_processing_jobs (
                  id, project_id, source_id, job_type, status, provider,
                  provider_job_id, attempt_count, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.project_id,
                    record.source_id,
                    record.job_type,
                    record.status,
                    record.provider,
                    record.provider_job_id,
                    record.attempt_count,
                    record.last_error,
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def get_source_processing_job(self, job_id: str) -> SourceProcessingJobRecord | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, source_id, job_type, status, provider,
                       provider_job_id, attempt_count, last_error, created_at, updated_at
                FROM source_processing_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return SourceProcessingJobRecord.model_validate(dict(row)) if row else None

    def list_source_processing_jobs(self, *, source_id: str) -> list[SourceProcessingJobRecord]:
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, source_id, job_type, status, provider,
                       provider_job_id, attempt_count, last_error, created_at, updated_at
                FROM source_processing_jobs
                WHERE source_id = ?
                ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC
                """,
                (source_id,),
            ).fetchall()
        return [SourceProcessingJobRecord.model_validate(dict(row)) for row in rows]

    def update_source_processing_job(
        self,
        *,
        job_id: str,
        status: str,
        provider_job_id: str | None,
        attempt_count: int,
        last_error: str | None,
    ) -> SourceProcessingJobRecord:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                UPDATE source_processing_jobs
                SET status = ?, provider_job_id = ?, attempt_count = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, provider_job_id, attempt_count, last_error, timestamp, job_id),
            )
        updated = self.get_source_processing_job(job_id)
        if updated is None:
            raise LookupError("Source processing job not found")
        return updated
```

```text
# backend/requirements.txt
qiniu==7.13.0
aliyun-python-sdk-core==2.16.0
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_audio_pipeline_config.py backend/tests/test_audio_pipeline_schema.py -v
```

Expected:

- PASS `test_from_env_reads_qiniu_and_aliyun_audio_settings`
- PASS `test_init_db_creates_source_processing_jobs_table`
- PASS `test_project_catalog_can_create_and_update_source_processing_job`

- [ ] **Step 5: Commit the groundwork**

```powershell
git add backend/requirements.txt backend/app/config.py backend/app/models.py backend/app/schema.sql backend/app/services/project_catalog.py backend/tests/test_audio_pipeline_config.py backend/tests/test_audio_pipeline_schema.py
git commit -m "feat: add audio provider config and job persistence"
```

## Task 2: Implement the Qiniu Object Storage Adapter

**Files:**
- Create: `backend/app/services/object_storage_service.py`
- Test: `backend/tests/test_object_storage_service.py`

- [ ] **Step 1: Write the failing Qiniu adapter tests**

```python
# backend/tests/test_object_storage_service.py
from pathlib import Path

from app.config import AppSettings
from app.models import ProviderIssue
from app.services.object_storage_service import ObjectStorageService


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
        qiniu_access_key="ak",
        qiniu_secret_key="sk",
        qiniu_bucket="audio-bucket",
        qiniu_domain="https://audio.example.com/",
    )


def test_get_readiness_reports_missing_qiniu_configuration(tmp_path: Path) -> None:
    service = ObjectStorageService(make_settings(tmp_path))
    service.settings.qiniu_access_key = None

    readiness = service.get_readiness()

    assert readiness.provider == "QINIU_OSS"
    assert readiness.status == "not_configured"
    assert "七牛" in (readiness.detail or "")


def test_upload_audio_source_returns_stable_object_metadata(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    source_path = settings.projects_dir / "project-1" / "sources" / "call.mp3"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"ID3")

    captured: dict[str, object] = {}

    def fake_put_file_v2(token: str, key: str, file_path: str, version: str = "v2"):
        captured["token"] = token
        captured["key"] = key
        captured["file_path"] = file_path
        captured["version"] = version
        return {"key": key}, type("Info", (), {"status_code": 200})()

    monkeypatch.setattr("app.services.object_storage_service.put_file_v2", fake_put_file_v2)

    service = ObjectStorageService(settings)
    result = service.upload_audio_source(
        project_id="project-1",
        source_id="src-1",
        local_path=source_path,
    )

    assert captured["file_path"] == str(source_path)
    assert captured["version"] == "v2"
    assert result.object_key == "audio/project-1/src-1/call.mp3"
    assert result.url == "https://audio.example.com/audio/project-1/src-1/call.mp3"


def test_upload_audio_source_raises_when_qiniu_is_not_ready(tmp_path: Path) -> None:
    service = ObjectStorageService(make_settings(tmp_path))
    service.settings.qiniu_bucket = None

    source_path = service.settings.projects_dir / "project-1" / "sources" / "call.mp3"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"ID3")

    try:
        service.upload_audio_source(project_id="project-1", source_id="src-1", local_path=source_path)
    except ProviderIssue as exc:
        assert exc.provider == "QINIU_OSS"
        assert "七牛" in exc.message
    else:
        raise AssertionError("Expected ProviderIssue when Qiniu is not configured")
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_object_storage_service.py -v
```

Expected:

- `ModuleNotFoundError` because `object_storage_service.py` does not exist yet

- [ ] **Step 3: Implement the Qiniu adapter**

```python
# backend/app/services/object_storage_service.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qiniu import Auth, put_file_v2

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue, ProviderReadiness


QINIU_PROVIDER = "QINIU_OSS"


@dataclass(frozen=True, slots=True)
class UploadedObject:
    object_key: str
    url: str


class ObjectStorageService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def get_readiness(self) -> ProviderReadiness:
        required = [
            self.settings.qiniu_access_key,
            self.settings.qiniu_secret_key,
            self.settings.qiniu_bucket,
            self.settings.qiniu_domain,
        ]
        if any(value in {None, ""} for value in required):
            return ProviderReadiness(
                provider=QINIU_PROVIDER,
                status="not_configured",
                summary="七牛对象存储未就绪。",
                detail="缺少七牛 AccessKey、SecretKey、Bucket 或 Domain 配置。",
                action_label="配置七牛对象存储",
            )
        return ProviderReadiness(
            provider=QINIU_PROVIDER,
            status="ready",
            summary="七牛对象存储已就绪。",
            detail=f"bucket={self.settings.qiniu_bucket}",
            action_label=None,
        )

    def build_object_key(self, *, project_id: str, source_id: str, local_path: Path) -> str:
        return f"{self.settings.qiniu_key_prefix}/{project_id}/{source_id}/{local_path.name}"

    def upload_audio_source(self, *, project_id: str, source_id: str, local_path: Path) -> UploadedObject:
        readiness = self.get_readiness()
        if readiness.status != "ready":
            raise ProviderIssue(provider=QINIU_PROVIDER, message=readiness.detail or readiness.summary)
        if not local_path.exists():
            raise FileNotFoundError(str(local_path))

        object_key = self.build_object_key(project_id=project_id, source_id=source_id, local_path=local_path)
        token = Auth(
            self.settings.qiniu_access_key,
            self.settings.qiniu_secret_key,
        ).upload_token(self.settings.qiniu_bucket, object_key, 3600)
        ret, info = put_file_v2(token, object_key, str(local_path), version="v2")
        if info.status_code != 200 or not ret or ret.get("key") != object_key:
            raise ProviderIssue(provider=QINIU_PROVIDER, message="七牛上传失败。")

        domain = self.settings.qiniu_domain.rstrip("/")
        return UploadedObject(
            object_key=object_key,
            url=f"{domain}/{object_key}",
        )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_object_storage_service.py -v
```

Expected:

- PASS `test_get_readiness_reports_missing_qiniu_configuration`
- PASS `test_upload_audio_source_returns_stable_object_metadata`
- PASS `test_upload_audio_source_raises_when_qiniu_is_not_ready`

- [ ] **Step 5: Commit the Qiniu adapter**

```powershell
git add backend/app/services/object_storage_service.py backend/tests/test_object_storage_service.py
git commit -m "feat: add qiniu object storage adapter"
```

## Task 3: Implement the Aliyun Audio Transcription Adapter

**Files:**
- Create: `backend/app/services/audio_transcription_service.py`
- Test: `backend/tests/test_audio_transcription_service.py`

- [ ] **Step 1: Write the failing Aliyun transcription tests**

```python
# backend/tests/test_audio_transcription_service.py
from pathlib import Path

from app.config import AppSettings
from app.models import ProviderIssue
from app.services.audio_transcription_service import AudioTranscriptionService


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
        aliyun_ak_id="aliyun-ak",
        aliyun_ak_secret="aliyun-sk",
        aliyun_app_key="aliyun-app-key",
        aliyun_filetrans_region="cn-shanghai",
        audio_transcription_timeout_seconds=30,
        audio_transcription_poll_interval_seconds=0.01,
    )


def test_get_readiness_reports_missing_aliyun_configuration(tmp_path: Path) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    service.settings.aliyun_app_key = None

    readiness = service.get_readiness()

    assert readiness.provider == "ALIYUN_FILETRANS"
    assert readiness.status == "not_configured"
    assert "阿里云" in (readiness.detail or "")


def test_format_markdown_preserves_time_ranges() -> None:
    markdown = AudioTranscriptionService.format_markdown(
        [
            {"BeginTime": 0, "EndTime": 5000, "Text": "逐笔对账需要人工确认"},
            {"BeginTime": 5000, "EndTime": 12000, "Text": "退款口径需要独立确认"},
        ]
    )

    assert markdown.startswith("# 音频转写")
    assert "00:00-00:05 逐笔对账需要人工确认" in markdown
    assert "00:05-00:12 退款口径需要独立确认" in markdown


def test_transcribe_from_url_returns_provider_job_id_and_markdown(tmp_path: Path, monkeypatch) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(service, "_submit_task", lambda file_url, source_name: "task-1")
    monkeypatch.setattr(
        service,
        "_wait_for_result",
        lambda task_id: [{"BeginTime": 0, "EndTime": 5000, "Text": "逐笔对账需要人工确认"}],
    )

    result = service.transcribe_from_url(
        file_url="https://audio.example.com/audio/project-1/src-1/call.mp3",
        source_name="call.mp3",
    )

    assert result.provider_job_id == "task-1"
    assert "00:00-00:05 逐笔对账需要人工确认" in result.markdown


def test_transcribe_from_url_raises_when_result_is_empty(tmp_path: Path, monkeypatch) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(service, "_submit_task", lambda file_url, source_name: "task-1")
    monkeypatch.setattr(service, "_wait_for_result", lambda task_id: [])

    try:
        service.transcribe_from_url(
            file_url="https://audio.example.com/audio/project-1/src-1/call.mp3",
            source_name="call.mp3",
        )
    except ProviderIssue as exc:
        assert exc.provider == "ALIYUN_FILETRANS"
        assert "转写结果为空" in exc.message
    else:
        raise AssertionError("Expected ProviderIssue for empty transcription result")
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_audio_transcription_service.py -v
```

Expected:

- `ModuleNotFoundError` because `audio_transcription_service.py` does not exist yet

- [ ] **Step 3: Implement the Aliyun transcription adapter**

```python
# backend/app/services/audio_transcription_service.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue, ProviderReadiness


ALIYUN_FILETRANS_PROVIDER = "ALIYUN_FILETRANS"
ALIYUN_FILETRANS_PRODUCT = "nls-filetrans"
ALIYUN_FILETRANS_VERSION = "2018-08-17"


@dataclass(frozen=True, slots=True)
class AudioTranscriptionResult:
    provider_job_id: str
    markdown: str


class AudioTranscriptionService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def get_readiness(self) -> ProviderReadiness:
        required = [
            self.settings.aliyun_ak_id,
            self.settings.aliyun_ak_secret,
            self.settings.aliyun_app_key,
        ]
        if any(value in {None, ""} for value in required):
            return ProviderReadiness(
                provider=ALIYUN_FILETRANS_PROVIDER,
                status="not_configured",
                summary="阿里云音频转写未就绪。",
                detail="缺少阿里云 AccessKeyId、AccessKeySecret 或 AppKey 配置。",
                action_label="配置阿里云音频转写",
            )
        return ProviderReadiness(
            provider=ALIYUN_FILETRANS_PROVIDER,
            status="ready",
            summary="阿里云音频转写已就绪。",
            detail=f"region={self.settings.aliyun_filetrans_region}",
            action_label=None,
        )

    @staticmethod
    def _format_timestamp(milliseconds: int) -> str:
        seconds = max(milliseconds, 0) // 1000
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @classmethod
    def format_markdown(cls, utterances: list[dict[str, Any]]) -> str:
        lines = ["# 音频转写", ""]
        for item in utterances:
            text = str(item.get("Text", "")).strip()
            if not text:
                continue
            start = cls._format_timestamp(int(item.get("BeginTime", 0)))
            end = cls._format_timestamp(int(item.get("EndTime", item.get("BeginTime", 0))))
            lines.append(f"{start}-{end} {text}")
        markdown = "\n".join(lines).strip()
        if markdown == "# 音频转写":
            raise ProviderIssue(provider=ALIYUN_FILETRANS_PROVIDER, message="转写结果为空。")
        return markdown

    def _client(self) -> AcsClient:
        return AcsClient(
            self.settings.aliyun_ak_id,
            self.settings.aliyun_ak_secret,
            self.settings.aliyun_filetrans_region,
        )

    def _request(self, *, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = CommonRequest()
        request.set_accept_format("json")
        request.set_domain(f"filetrans.{self.settings.aliyun_filetrans_region}.aliyuncs.com")
        request.set_method("POST")
        request.set_protocol_type("https")
        request.set_version(ALIYUN_FILETRANS_VERSION)
        request.set_product(ALIYUN_FILETRANS_PRODUCT)
        request.set_action_name(action)
        request.add_header("Content-Type", "application/json")
        request.set_content(json.dumps(payload).encode("utf-8"))

        raw = self._client().do_action_with_exception(request)
        return json.loads(raw)

    def _submit_task(self, file_url: str, source_name: str) -> str:
        payload = {
            "appkey": self.settings.aliyun_app_key,
            "file_link": file_url,
            "version": "4.0",
            "enable_words": False,
            "enable_timestamp_alignment": True,
            "source_name": source_name,
        }
        response = self._request(action="SubmitTask", payload=payload)
        task_id = response.get("TaskId")
        if not task_id:
            raise ProviderIssue(provider=ALIYUN_FILETRANS_PROVIDER, message="阿里云未返回 TaskId。")
        return str(task_id)

    def _wait_for_result(self, task_id: str) -> list[dict[str, Any]]:
        deadline = time.time() + self.settings.audio_transcription_timeout_seconds
        while time.time() < deadline:
            payload = self._request(action="GetTaskResult", payload={"TaskId": task_id})
            status_text = str(payload.get("StatusText", "")).upper()
            if status_text in {"QUEUEING", "RUNNING"}:
                time.sleep(self.settings.audio_transcription_poll_interval_seconds)
                continue
            if status_text != "SUCCESS":
                raise ProviderIssue(
                    provider=ALIYUN_FILETRANS_PROVIDER,
                    message=payload.get("StatusMessage") or "阿里云转写失败。",
                )

            result_payload = payload.get("Result")
            if isinstance(result_payload, str):
                result_payload = json.loads(result_payload)
            sentences = result_payload.get("Sentences") or []
            if not isinstance(sentences, list):
                raise ProviderIssue(provider=ALIYUN_FILETRANS_PROVIDER, message="阿里云转写结果格式异常。")
            return sentences

        raise ProviderIssue(provider=ALIYUN_FILETRANS_PROVIDER, message="阿里云转写超时。")

    def transcribe_from_url(self, *, file_url: str, source_name: str) -> AudioTranscriptionResult:
        readiness = self.get_readiness()
        if readiness.status != "ready":
            raise ProviderIssue(provider=ALIYUN_FILETRANS_PROVIDER, message=readiness.detail or readiness.summary)
        task_id = self._submit_task(file_url=file_url, source_name=source_name)
        utterances = self._wait_for_result(task_id)
        markdown = self.format_markdown(utterances)
        return AudioTranscriptionResult(provider_job_id=task_id, markdown=markdown)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_audio_transcription_service.py -v
```

Expected:

- PASS `test_get_readiness_reports_missing_aliyun_configuration`
- PASS `test_format_markdown_preserves_time_ranges`
- PASS `test_transcribe_from_url_returns_provider_job_id_and_markdown`
- PASS `test_transcribe_from_url_raises_when_result_is_empty`

- [ ] **Step 5: Commit the Aliyun adapter**

```powershell
git add backend/app/services/audio_transcription_service.py backend/tests/test_audio_transcription_service.py
git commit -m "feat: add aliyun audio transcription adapter"
```

## Task 4: Replace Synchronous Audio Docling with an Async Audio Orchestrator

**Files:**
- Create: `backend/app/services/audio_ingestion_orchestrator.py`
- Modify: `backend/app/services/project_catalog.py`
- Modify: `backend/app/services/source_ingestion.py`
- Modify: `backend/app/services/docling_normalizer.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_audio_ingestion_orchestrator.py`
- Test: `backend/tests/test_source_ingestion_audio.py`

- [ ] **Step 1: Write the failing orchestration and ingestion tests**

```python
# backend/tests/test_source_ingestion_audio.py
from pathlib import Path

from app.config import AppSettings
from app.services.source_ingestion import SourceIngestionService


class GuardNormalizer:
    def supports(self, source_path: Path) -> bool:
        raise AssertionError("Audio uploads should not ask Docling whether audio is supported")


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
    )


def test_ingest_audio_returns_processing_and_bypasses_docling(tmp_path: Path) -> None:
    service = SourceIngestionService(
        make_settings(tmp_path),
        docling_normalizer=GuardNormalizer(),
    )

    storage_path, normalized = service.ingest_file(
        "project-1",
        "call.mp3",
        b"ID3",
    )

    assert storage_path.endswith("call.mp3")
    assert normalized.source_kind == "audio"
    assert normalized.normalize_status == "processing"
    assert normalized.normalized_path is None
    assert normalized.index_input_mode is None
    assert "正在转写" in normalized.normalize_summary
```

```python
# backend/tests/test_audio_ingestion_orchestrator.py
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import CreateProjectRequest, ProviderIssue
from app.services.audio_ingestion_orchestrator import AudioIngestionOrchestrator
from app.services.audio_transcription_service import AudioTranscriptionResult
from app.services.object_storage_service import UploadedObject
from app.services.project_catalog import ProjectCatalog


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
    )


class FakeStorage:
    def upload_audio_source(self, *, project_id: str, source_id: str, local_path: Path) -> UploadedObject:
        return UploadedObject(
            object_key=f"audio/{project_id}/{source_id}/{local_path.name}",
            url=f"https://audio.example.com/audio/{project_id}/{source_id}/{local_path.name}",
        )


class FakeTranscription:
    def transcribe_from_url(self, *, file_url: str, source_name: str) -> AudioTranscriptionResult:
        return AudioTranscriptionResult(
            provider_job_id="task-1",
            markdown="# 音频转写\n\n00:00-00:05 逐笔对账需要人工确认",
        )


class FakeEvidenceRuntime:
    def __init__(self) -> None:
        self.index_calls: list[tuple[str, str]] = []

    def index_source(self, project_id: str, source_id: str) -> None:
        self.index_calls.append((project_id, source_id))


def test_process_source_writes_normalized_markdown_and_indexes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(name="音频项目", scenario_type="general", summary="test")
    )
    source_dir = settings.projects_dir / project.id / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / "call.mp3"
    raw_path.write_bytes(b"ID3")
    source = catalog.create_source(
        project_id=project.id,
        name="call.mp3",
        source_kind="audio",
        upload_kind="file",
        storage_path=str(raw_path),
        normalized_path=None,
        index_input_mode=None,
        normalize_status="processing",
        normalize_summary="call.mp3 已入库，正在转写；完成后会自动进入项目知识库。",
        index_status="normalization_pending",
        index_error="音频正在转写，完成后会自动进入项目知识库。",
    )
    evidence_runtime = FakeEvidenceRuntime()
    orchestrator = AudioIngestionOrchestrator(
        settings=settings,
        catalog=catalog,
        object_storage=FakeStorage(),
        audio_transcription=FakeTranscription(),
        evidence_runtime=evidence_runtime,
    )

    orchestrator.process_source(project.id, source.id)

    refreshed = catalog.get_source(source.id)
    assert refreshed is not None
    assert refreshed.normalize_status == "parsed"
    assert refreshed.index_status == "indexed"
    assert refreshed.normalized_path is not None
    normalized_path = Path(refreshed.normalized_path)
    assert normalized_path.exists()
    assert "00:00-00:05 逐笔对账需要人工确认" in normalized_path.read_text(encoding="utf-8")
    assert evidence_runtime.index_calls == [(project.id, source.id)]
    jobs = catalog.list_source_processing_jobs(source_id=source.id)
    assert jobs[0].status == "completed"
    assert jobs[0].provider_job_id == "task-1"


def test_process_source_marks_pre_transcription_failure_without_indexing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(name="音频项目", scenario_type="general", summary="test")
    )
    source_dir = settings.projects_dir / project.id / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / "call.mp3"
    raw_path.write_bytes(b"ID3")
    source = catalog.create_source(
        project_id=project.id,
        name="call.mp3",
        source_kind="audio",
        upload_kind="file",
        storage_path=str(raw_path),
        normalized_path=None,
        index_input_mode=None,
        normalize_status="processing",
        normalize_summary="call.mp3 已入库，正在转写；完成后会自动进入项目知识库。",
        index_status="normalization_pending",
        index_error="音频正在转写，完成后会自动进入项目知识库。",
    )

    class FailingStorage:
        def upload_audio_source(self, *, project_id: str, source_id: str, local_path: Path) -> UploadedObject:
            raise ProviderIssue(provider="QINIU_OSS", message="七牛上传失败。")

    orchestrator = AudioIngestionOrchestrator(
        settings=settings,
        catalog=catalog,
        object_storage=FailingStorage(),
        audio_transcription=FakeTranscription(),
        evidence_runtime=FakeEvidenceRuntime(),
    )

    orchestrator.process_source(project.id, source.id)

    refreshed = catalog.get_source(source.id)
    assert refreshed is not None
    assert refreshed.normalize_status == "failed"
    assert refreshed.index_status == "normalization_failed"
    assert refreshed.normalized_path is None
    jobs = catalog.list_source_processing_jobs(source_id=source.id)
    assert jobs[0].status == "failed"
    assert jobs[0].last_error == "七牛上传失败。"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_ingestion_audio.py backend/tests/test_audio_ingestion_orchestrator.py -v
```

Expected:

- FAIL because audio still tries synchronous Docling normalization
- FAIL because `AudioIngestionOrchestrator` does not exist
- FAIL because `ProjectCatalog` has no `update_source_normalization()` helper

- [ ] **Step 3: Implement async audio ingestion semantics**

```python
# backend/app/services/project_catalog.py
    def update_source_normalization(
        self,
        *,
        source_id: str,
        normalized_path: str | None,
        index_input_mode: str | None,
        normalize_status: str,
        normalize_summary: str | None,
        index_status: str,
        index_error: str | None,
    ) -> SourceRecord:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                "SELECT project_id FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
            if not row:
                raise LookupError("Source not found")

            connection.execute(
                """
                UPDATE sources
                SET normalized_path = ?, index_input_mode = ?, normalize_status = ?,
                    normalize_summary = ?, index_status = ?, index_error = ?
                WHERE id = ?
                """,
                (
                    normalized_path,
                    index_input_mode,
                    normalize_status,
                    normalize_summary,
                    index_status,
                    index_error,
                    source_id,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, row["project_id"]),
            )
        updated = self.get_source(source_id)
        if updated is None:
            raise LookupError("Source not found after normalization update")
        return updated
```

```python
# backend/app/services/source_ingestion.py
        if suffix in DoclingNormalizer.AUDIO_SUFFIXES:
            return str(raw_path), NormalizedSource(
                source_kind="audio",
                normalize_status="processing",
                normalize_summary=f"{filename} 已入库，正在转写；完成后会自动进入项目知识库。",
                normalized_path=None,
                index_input_mode=None,
            )

        try:
            if suffix in self.TEXT_FILE_SUFFIXES:
                text = raw_path.read_text(encoding="utf-8", errors="ignore")
                normalized_path = raw_path
                summary = self._summarize_text(text, fallback=summary)
                import_mode = "direct_text"
            elif suffix in self.SPREADSHEET_SUFFIXES:
                workbook = load_workbook(str(raw_path), read_only=True, data_only=True)
                lines: list[str] = []
                for sheet in workbook.worksheets:
                    lines.append(f"# Sheet: {sheet.title}")
                    rows = list(sheet.iter_rows(values_only=True, max_row=6))
                    if rows:
                        header = [str(cell or "") for cell in rows[0]]
                        lines.append("表头: " + " | ".join(header))
                    for sample_row in rows[1:4]:
                        lines.append("样例: " + " | ".join(str(cell or "") for cell in sample_row))
                    lines.append(f"行数估计: {sheet.max_row}, 列数估计: {sheet.max_column}")
                text = "\n".join(lines)
                normalized_path = self._write_normalized_markdown(source_dir, raw_path, text)
                summary = self._summarize_text(text, fallback="XLSX 已转成摘要文本。")
                import_mode = "normalized_text"
            elif self.docling_normalizer.supports(raw_path):
                text = self.docling_normalizer.normalize_to_markdown(raw_path)
                normalized_path = self._write_normalized_markdown(source_dir, raw_path, text)
                summary = self._summarize_text(text, fallback=f"{filename} 已通过 Docling 转成文本。")
                import_mode = "normalized_text"
            else:
                raise ProviderIssue(
                    provider="SOURCE_INGESTION",
                    message=(
                        f"{filename} 当前还没有接入正式的 text-first 标准化链路，"
                        "因此不能标记成已解析或可索引。"
                    ),
                )
```

```python
# backend/app/services/docling_normalizer.py
class DoclingNormalizer:
    DOCUMENT_SUFFIXES = {
        ".pdf",
        ".docx",
        ".pptx",
        ".html",
        ".htm",
    }
    IMAGE_SUFFIXES = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
    }
    AUDIO_SUFFIXES = {
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
    }
    SUPPORTED_SUFFIXES = DOCUMENT_SUFFIXES | IMAGE_SUFFIXES

    def supports(self, source_path: Path) -> bool:
        return source_path.suffix.lower() in self.SUPPORTED_SUFFIXES

    def normalize_to_markdown(self, source_path: Path) -> str:
        suffix = source_path.suffix.lower()
        if suffix in self.AUDIO_SUFFIXES:
            raise ProviderIssue(
                provider=DOCLING_PROVIDER,
                message="音频标准化不再走 Docling；请使用 AudioTranscriptionService。",
            )
        converter_class = self._load_document_converter(suffix=suffix)
        converter = converter_class()
        try:
            result = converter.convert(str(source_path))
        except Exception as exc:
            raise self._conversion_issue(source_path, exc) from exc
        document = getattr(result, "document", None)
        export_to_markdown = getattr(document, "export_to_markdown", None)
        if export_to_markdown is None:
            raise ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=f"Docling 返回了不完整结果，{source_path.name} 缺少 Markdown 导出能力。",
            )
        markdown = export_to_markdown()
        if not isinstance(markdown, str) or not markdown.strip():
            raise ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=f"Docling 没有从 {source_path.name} 提取到可索引文本。",
            )
        return markdown
```

```python
# backend/app/services/audio_ingestion_orchestrator.py
from __future__ import annotations

from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue
from .audio_transcription_service import ALIYUN_FILETRANS_PROVIDER, AudioTranscriptionService
from .object_storage_service import ObjectStorageService
from .project_catalog import ProjectCatalog


class AudioIngestionOrchestrator:
    def __init__(
        self,
        *,
        settings: AppSettings = DEFAULT_SETTINGS,
        catalog: ProjectCatalog,
        object_storage: ObjectStorageService,
        audio_transcription: AudioTranscriptionService,
        evidence_runtime,
    ):
        self.settings = settings
        self.catalog = catalog
        self.object_storage = object_storage
        self.audio_transcription = audio_transcription
        self.evidence_runtime = evidence_runtime

    def process_source(self, project_id: str, source_id: str) -> None:
        source = self.catalog.get_source(source_id)
        if source is None:
            raise LookupError("Source not found")
        if source.project_id != project_id:
            raise ValueError("source_id does not belong to the provided project_id")
        if source.source_kind != "audio":
            raise ValueError("AudioIngestionOrchestrator only handles audio sources")
        if not source.storage_path:
            raise ValueError("Audio source has no storage_path")

        job = self.catalog.create_source_processing_job(
            project_id=project_id,
            source_id=source_id,
            job_type="audio_transcription",
            provider=ALIYUN_FILETRANS_PROVIDER,
            status="processing",
            provider_job_id=None,
            attempt_count=1,
            last_error=None,
        )

        try:
            uploaded = self.object_storage.upload_audio_source(
                project_id=project_id,
                source_id=source_id,
                local_path=Path(source.storage_path),
            )
            transcription = self.audio_transcription.transcribe_from_url(
                file_url=uploaded.url,
                source_name=source.name,
            )
        except ProviderIssue as exc:
            self.catalog.update_source_processing_job(
                job_id=job.id,
                status="failed",
                provider_job_id=None,
                attempt_count=job.attempt_count,
                last_error=exc.message,
            )
            self.catalog.update_source_normalization(
                source_id=source_id,
                normalized_path=None,
                index_input_mode=None,
                normalize_status="failed",
                normalize_summary=exc.message,
                index_status="normalization_failed",
                index_error=f"资料标准化失败，尚未进入项目知识库。{exc.message}",
            )
            return

        normalized_path = Path(source.storage_path).with_suffix(".normalized.md")
        normalized_path.write_text(transcription.markdown, encoding="utf-8")
        self.catalog.update_source_processing_job(
            job_id=job.id,
            status="completed",
            provider_job_id=transcription.provider_job_id,
            attempt_count=job.attempt_count,
            last_error=None,
        )
        self.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=str(normalized_path),
            index_input_mode="normalized_text",
            normalize_status="parsed",
            normalize_summary="ASR 已生成转写文本。",
            index_status="pending",
            index_error=None,
        )

        self.catalog.update_source_index_status(
            source_id=source_id,
            index_status="indexing",
            index_error=None,
        )
        try:
            self.evidence_runtime.index_source(project_id, source_id)
        except ProviderIssue as exc:
            self.catalog.update_source_index_status(
                source_id=source_id,
                index_status="index_failed",
                index_error=exc.message,
            )
            return

        self.catalog.update_source_index_status(
            source_id=source_id,
            index_status="indexed",
            index_error=None,
        )
```

```python
# backend/app/main.py
from .services.audio_ingestion_orchestrator import AudioIngestionOrchestrator
from .services.audio_transcription_service import AudioTranscriptionService
from .services.object_storage_service import ObjectStorageService


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
    agent_runtime: AgentRuntime
    artifact_generation: ArtifactGenerationService
    chat_service: ChatService


def build_services(settings: AppSettings) -> ServiceContainer:
    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)
    docling_normalizer = DoclingNormalizer()
    source_ingestion = SourceIngestionService(settings, docling_normalizer=docling_normalizer)
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
    artifact_generation = ArtifactGenerationService(settings)
    chat_service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=evidence_runtime,
        agent_runtime=agent_runtime,
        artifact_generation=artifact_generation,
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
        agent_runtime=agent_runtime,
        artifact_generation=artifact_generation,
        chat_service=chat_service,
    )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_source_ingestion_audio.py backend/tests/test_audio_ingestion_orchestrator.py -v
```

Expected:

- PASS `test_ingest_audio_returns_processing_and_bypasses_docling`
- PASS `test_process_source_writes_normalized_markdown_and_indexes`
- PASS `test_process_source_marks_pre_transcription_failure_without_indexing`

- [ ] **Step 5: Commit the async audio workflow**

```powershell
git add backend/app/services/audio_ingestion_orchestrator.py backend/app/services/project_catalog.py backend/app/services/source_ingestion.py backend/app/services/docling_normalizer.py backend/app/main.py backend/tests/test_audio_ingestion_orchestrator.py backend/tests/test_source_ingestion_audio.py
git commit -m "feat: add async audio ingestion workflow"
```

## Task 5: Wire Upload, Reindex, and Readiness Routes

**Files:**
- Modify: `backend/app/routes/sources.py`
- Modify: `backend/app/routes/readiness.py`
- Modify: `backend/tests/test_api_flow.py`

- [ ] **Step 1: Add failing API flow tests for audio upload, readiness, and reindex**

```python
# backend/tests/test_api_flow.py
def test_audio_upload_returns_processing_and_exposes_runtime_readiness(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: queued.append((project_id, source_id)),
    )
    monkeypatch.setattr(
        app.state.services.object_storage,
        "get_readiness",
        lambda: ProviderReadiness(
            provider="QINIU_OSS",
            status="ready",
            summary="七牛对象存储已就绪。",
            detail="bucket=audio-bucket",
            action_label=None,
        ),
    )
    monkeypatch.setattr(
        app.state.services.audio_transcription,
        "get_readiness",
        lambda: ProviderReadiness(
            provider="ALIYUN_FILETRANS",
            status="ready",
            summary="阿里云音频转写已就绪。",
            detail="region=cn-shanghai",
            action_label=None,
        ),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "音频上传测试",
                "scenario_type": "general",
                "summary": "验证音频异步标准化返回 processing",
            },
        )
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )
        readiness_response = client.get(f"/api/projects/{project_id}/readiness")

    source = upload_response.json()
    readiness = readiness_response.json()
    assert source["source_kind"] == "audio"
    assert source["normalize_status"] == "processing"
    assert source["index_status"] == "normalization_pending"
    assert queued == [(project_id, source["id"])]
    assert readiness["object_storage"]["provider"] == "QINIU_OSS"
    assert readiness["audio_transcription"]["provider"] == "ALIYUN_FILETRANS"


def test_audio_reindex_restarts_transcription_when_normalized_text_missing(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: queued.append((project_id, source_id)),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={"name": "重试项目", "scenario_type": "general", "summary": "test"},
        )
        project_id = create_response.json()["id"]
        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )
        source_id = upload_response.json()["id"]

        app.state.services.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=None,
            index_input_mode=None,
            normalize_status="failed",
            normalize_summary="阿里云转写超时。",
            index_status="normalization_failed",
            index_error="资料标准化失败，尚未进入项目知识库。阿里云转写超时。",
        )

        reindex_response = client.post(f"/api/projects/{project_id}/sources/{source_id}/reindex")

    payload = reindex_response.json()
    assert reindex_response.status_code == 200
    assert queued == [(project_id, source_id), (project_id, source_id)]
    assert payload["normalize_status"] == "processing"
    assert payload["index_status"] == "normalization_pending"
```

- [ ] **Step 2: Run the API tests and confirm they fail**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api_flow.py -k "audio_upload_returns_processing or audio_reindex_restarts_transcription" -v
```

Expected:

- FAIL because upload still returns the old audio behavior
- FAIL because readiness payload has no `object_storage` or `audio_transcription`
- FAIL because `reindex` always delegates directly to evidence reindex

- [ ] **Step 3: Implement audio-aware upload, readiness, and reindex semantics**

```python
# backend/app/routes/sources.py
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile, status


def _resolve_index_outcome(services, project_id: str, normalized_source) -> tuple[str, str | None]:
    if normalized_source.normalize_status == "processing":
        detail = normalized_source.normalize_summary or "音频正在转写，完成后会自动进入项目知识库。"
        return "normalization_pending", detail

    if normalized_source.normalize_status == "pending":
        detail = normalized_source.normalize_summary or "资料已记录，但还没有完成文本标准化。"
        return "normalization_pending", detail

    if normalized_source.normalize_status != "parsed":
        detail = normalized_source.normalize_summary or "资料标准化失败。"
        return "normalization_failed", f"资料标准化失败，尚未进入项目知识库。{detail}"

    try:
        evidence = services.evidence_runtime.get_global_readiness()
    except ProviderIssue as exc:
        return "error", exc.message

    if evidence.status != "ready":
        return evidence.status, evidence.detail or evidence.summary

    knowledge_base = services.catalog.get_knowledge_base(
        project_id=project_id,
        provider=evidence.provider,
    )
    if knowledge_base is None:
        return "knowledge_base_missing", "资料已标准化，但当前项目还没有初始化项目内知识库。"

    return "pending", "资料已标准化，正在写入项目知识库。"
```

```python
# backend/app/routes/sources.py
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    project_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    upload_kind: str = Form(...),
    name: str = Form(...),
    text_content: str | None = Form(None),
    source_url: str | None = Form(None),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    source_ingestion = services.source_ingestion

    if upload_kind == "file":
        upload_files = files or ([file] if file is not None else [])
        if not upload_files:
            raise HTTPException(status_code=400, detail="file or files is required for file upload")

        created_sources = []
        for upload in upload_files:
            safe_name = Path(upload.filename or name).name
            storage_path, normalized_source = source_ingestion.ingest_file(
                project_id,
                safe_name,
                await upload.read(),
            )
            created = _create_source_record(
                services,
                project_id,
                upload_kind,
                safe_name,
                storage_path,
                normalized_source,
            )
            if created.source_kind == "audio" and created.normalize_status == "processing":
                background_tasks.add_task(services.audio_ingestion.process_source, project_id, created.id)
            created_sources.append(_serialize_source_record(created))
        return created_sources if len(created_sources) > 1 or files else created_sources[0]
```

```python
# backend/app/routes/sources.py
@router.post("/{source_id}/reindex", status_code=status.HTTP_200_OK)
def reindex_source(project_id: str, source_id: str, request: Request, background_tasks: BackgroundTasks):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    source = services.catalog.get_source(source_id)
    if not source or source.project_id != project_id:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.source_kind == "audio" and not source.normalized_path:
        if source.normalize_status == "processing":
            return _serialize_source_record(source)

        if source.normalize_status in {"failed", "pending"}:
            refreshed = services.catalog.update_source_normalization(
                source_id=source_id,
                normalized_path=None,
                index_input_mode=None,
                normalize_status="processing",
                normalize_summary="正在重新转写音频；完成后会自动进入项目知识库。",
                index_status="normalization_pending",
                index_error="音频正在转写，完成后会自动进入项目知识库。",
            )
            background_tasks.add_task(services.audio_ingestion.process_source, project_id, source_id)
            return _serialize_source_record(refreshed)

    try:
        return _serialize_source_record(
            _run_source_index_operation(
                services,
                project_id=project_id,
                source_id=source_id,
                operation="reindex",
                raise_on_error=True,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

```python
# backend/app/routes/readiness.py
def _with_audio_detail(readiness: ProviderReadiness, *, sources) -> ProviderReadiness:
    processing_count = sum(
        1 for source in sources if source.source_kind == "audio" and source.normalize_status == "processing"
    )
    failed_count = sum(
        1 for source in sources if source.source_kind == "audio" and source.normalize_status == "failed"
    )
    detail_parts = [readiness.detail] if readiness.detail else []
    detail_parts.append(f"processing_audio_sources={processing_count}")
    detail_parts.append(f"failed_audio_sources={failed_count}")
    return readiness.model_copy(update={"detail": "; ".join(detail_parts)})


@router.get("/api/providers/readiness", response_model=GlobalReadiness)
def get_global_readiness(request: Request) -> GlobalReadiness:
    services = request.app.state.services
    return GlobalReadiness(
        claude=services.agent_runtime.get_readiness(),
        evidence=services.evidence_runtime.get_global_readiness(),
        object_storage=services.object_storage.get_readiness(),
        audio_transcription=services.audio_transcription.get_readiness(),
    )


@router.get("/api/projects/{project_id}/readiness", response_model=ProjectReadiness)
def get_project_readiness(project_id: str, request: Request) -> ProjectReadiness:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    claude = services.agent_runtime.get_readiness()
    evidence = services.evidence_runtime.get_project_readiness(project_id, claude)
    knowledge_base = services.catalog.get_knowledge_base(
        project_id=project_id,
        provider=evidence.provider,
    )
    sources = services.catalog.list_sources(project_id)
    return ProjectReadiness(
        project_id=project_id,
        claude=claude,
        evidence=evidence,
        knowledge_base=knowledge_base,
        object_storage=_with_audio_detail(services.object_storage.get_readiness(), sources=sources),
        audio_transcription=_with_audio_detail(services.audio_transcription.get_readiness(), sources=sources),
    )
```

- [ ] **Step 4: Run the API tests and confirm they pass**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_api_flow.py -k "audio_upload_returns_processing or audio_reindex_restarts_transcription" -v
```

Expected:

- PASS `test_audio_upload_returns_processing_and_exposes_runtime_readiness`
- PASS `test_audio_reindex_restarts_transcription_when_normalized_text_missing`

- [ ] **Step 5: Commit the route integration**

```powershell
git add backend/app/routes/sources.py backend/app/routes/readiness.py backend/tests/test_api_flow.py
git commit -m "feat: wire audio upload readiness and reindex routes"
```

## Task 6: Surface the Audio Lifecycle in the Workbench UI

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/features/workbench/WorkbenchPage.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add failing frontend tests for audio processing, preview, and runtime cards**

```tsx
// frontend/src/App.test.tsx
it('renders audio sources as processing and refreshes while source work is active', async () => {
  vi.useFakeTimers();
  window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');
  const fetchSpy = installFetchMock({
    '/api/projects/seed-reconciliation': {
      id: 'seed-reconciliation',
      name: '集团业财逐笔对账需求分析',
      scenario_type: 'reconciliation',
      summary: '默认 seed 项目。',
      status: 'active',
      created_at: '2026-04-16T00:00:00+08:00',
      updated_at: '2026-04-16T00:00:00+08:00',
      seed_key: 'seed-reconciliation',
    },
    '/api/projects/seed-reconciliation/sources': [
      {
        id: 'src-audio',
        project_id: 'seed-reconciliation',
        name: 'call.mp3',
        source_kind: 'audio',
        upload_kind: 'file',
        storage_path: '/tmp/call.mp3',
        normalized_path: null,
        index_input_mode: null,
        normalize_status: 'processing',
        normalize_summary: 'call.mp3 已入库，正在转写；完成后会自动进入项目知识库。',
        index_status: 'normalization_pending',
        index_error: '音频正在转写，完成后会自动进入项目知识库。',
        created_at: '2026-04-25T10:00:00+08:00',
      },
    ],
    '/api/projects/seed-reconciliation/messages': [],
    '/api/projects/seed-reconciliation/state': {
      current_understanding: [],
      pending_items: [],
      confirmed_items: [],
      conflict_items: [],
      mvp_items: [],
      versions: [],
      artifacts: [],
    },
    '/api/projects/seed-reconciliation/artifacts': [],
    '/api/projects/seed-reconciliation/readiness': {
      project_id: 'seed-reconciliation',
      claude: {
        provider: 'CLAUDE_AGENT_SDK',
        status: 'ready',
        summary: 'Claude Agent SDK 已就绪。',
        detail: null,
        action_label: null,
      },
      evidence: {
        provider: 'QDRANT_LLAMA_INDEX',
        status: 'ready',
        summary: '项目知识库已就绪。',
        detail: 'Knowledge Base ID: kb-seed',
        action_label: null,
      },
      knowledge_base: {
        id: 'kb-seed',
        project_id: 'seed-reconciliation',
        provider: 'QDRANT_LLAMA_INDEX',
        external_knowledge_base_id: 'kb-seed',
        display_name: 'seed kb',
        description: null,
        status: 'ready',
        status_error: null,
        created_at: '2026-04-25T10:00:00+08:00',
        updated_at: '2026-04-25T10:00:00+08:00',
      },
      object_storage: {
        provider: 'QINIU_OSS',
        status: 'ready',
        summary: '七牛对象存储已就绪。',
        detail: 'bucket=audio-bucket; processing_audio_sources=1; failed_audio_sources=0',
        action_label: null,
      },
      audio_transcription: {
        provider: 'ALIYUN_FILETRANS',
        status: 'ready',
        summary: '阿里云音频转写已就绪。',
        detail: 'region=cn-shanghai; processing_audio_sources=1; failed_audio_sources=0',
        action_label: null,
      },
    },
  });

  render(<App />);

  expect(await screen.findByText('call.mp3')).toBeInTheDocument();
  expect(screen.getByText('标准化：标准化中')).toBeInTheDocument();
  expect(screen.getByText('入库：待标准化')).toBeInTheDocument();
  expect(screen.getByText('call.mp3 已入库，正在转写；完成后会自动进入项目知识库。')).toBeInTheDocument();

  await vi.advanceTimersByTimeAsync(3000);

  await waitFor(() => {
    const sourceCalls = fetchSpy.mock.calls.filter((call) => {
      const input = call[0];
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      return new URL(url, 'http://localhost').pathname === '/api/projects/seed-reconciliation/sources';
    });
    expect(sourceCalls.length).toBeGreaterThan(1);
  });
});
```

```tsx
// frontend/src/App.test.tsx
it('shows audio transcript preview and runtime provider cards', async () => {
  window.history.replaceState({}, '', '/projects/seed-reconciliation/workbench');
  const user = userEvent.setup();

  installFetchMock({
    '/api/projects/seed-reconciliation': {
      id: 'seed-reconciliation',
      name: '集团业财逐笔对账需求分析',
      scenario_type: 'reconciliation',
      summary: '默认 seed 项目。',
      status: 'active',
      created_at: '2026-04-16T00:00:00+08:00',
      updated_at: '2026-04-16T00:00:00+08:00',
      seed_key: 'seed-reconciliation',
    },
    '/api/projects/seed-reconciliation/sources': [
      {
        id: 'src-audio',
        project_id: 'seed-reconciliation',
        name: 'call.mp3',
        source_kind: 'audio',
        upload_kind: 'file',
        storage_path: '/tmp/call.mp3',
        normalized_path: '/tmp/call.normalized.md',
        index_input_mode: 'normalized_text',
        normalize_status: 'parsed',
        normalize_summary: 'ASR 已生成转写文本。',
        index_status: 'indexed',
        index_error: null,
        created_at: '2026-04-25T10:00:00+08:00',
      },
    ],
    '/api/projects/seed-reconciliation/messages': [],
    '/api/projects/seed-reconciliation/state': {
      current_understanding: [],
      pending_items: [],
      confirmed_items: [],
      conflict_items: [],
      mvp_items: [],
      versions: [],
      artifacts: [],
    },
    '/api/projects/seed-reconciliation/artifacts': [],
    '/api/projects/seed-reconciliation/readiness': {
      project_id: 'seed-reconciliation',
      claude: {
        provider: 'CLAUDE_AGENT_SDK',
        status: 'ready',
        summary: 'Claude Agent SDK 已就绪。',
        detail: null,
        action_label: null,
      },
      evidence: {
        provider: 'QDRANT_LLAMA_INDEX',
        status: 'ready',
        summary: '项目知识库已就绪。',
        detail: 'Knowledge Base ID: kb-seed',
        action_label: null,
      },
      knowledge_base: {
        id: 'kb-seed',
        project_id: 'seed-reconciliation',
        provider: 'QDRANT_LLAMA_INDEX',
        external_knowledge_base_id: 'kb-seed',
        display_name: 'seed kb',
        description: null,
        status: 'ready',
        status_error: null,
        created_at: '2026-04-25T10:00:00+08:00',
        updated_at: '2026-04-25T10:00:00+08:00',
      },
      object_storage: {
        provider: 'QINIU_OSS',
        status: 'ready',
        summary: '七牛对象存储已就绪。',
        detail: 'bucket=audio-bucket; processing_audio_sources=0; failed_audio_sources=0',
        action_label: null,
      },
      audio_transcription: {
        provider: 'ALIYUN_FILETRANS',
        status: 'ready',
        summary: '阿里云音频转写已就绪。',
        detail: 'region=cn-shanghai; processing_audio_sources=0; failed_audio_sources=0',
        action_label: null,
      },
    },
  });

  render(<App />);

  await user.click(await screen.findByText('call.mp3'));
  expect(await screen.findByText('ASR 已生成转写文本。')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: '运行状态' }));
  expect(await screen.findByText('七牛对象存储')).toBeInTheDocument();
  expect(screen.getByText('阿里云音频转写')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the frontend tests and confirm they fail**

Run:

```powershell
npm test -- --runInBand src/App.test.tsx
```

Workdir:

```text
frontend/
```

Expected:

- FAIL because source badges still render the old `解析 / 索引` wording
- FAIL because there is no active source polling loop
- FAIL because runtime dialog has no Qiniu/Aliyun provider cards

- [ ] **Step 3: Implement the frontend audio lifecycle**

```ts
// frontend/src/lib/types.ts
export type GlobalReadiness = {
  claude: ProviderReadiness;
  evidence: ProviderReadiness;
  object_storage: ProviderReadiness | null;
  audio_transcription: ProviderReadiness | null;
};

export type ProjectReadiness = {
  project_id: string;
  claude: ProviderReadiness;
  evidence: ProviderReadiness;
  knowledge_base: KnowledgeBaseRecord | null;
  object_storage: ProviderReadiness | null;
  audio_transcription: ProviderReadiness | null;
};
```

```ts
// frontend/src/lib/api.ts
function normalizeGlobalReadiness(readiness: GlobalReadiness): GlobalReadiness {
  return {
    ...readiness,
    object_storage: readiness.object_storage ?? null,
    audio_transcription: readiness.audio_transcription ?? null,
  };
}

function normalizeProjectReadiness(readiness: ProjectReadiness): ProjectReadiness {
  return {
    ...readiness,
    object_storage: readiness.object_storage ?? null,
    audio_transcription: readiness.audio_transcription ?? null,
  };
}

export function getGlobalReadiness() {
  return fetchJson<GlobalReadiness>('/api/providers/readiness').then(normalizeGlobalReadiness);
}

export function getProjectReadiness(projectId: string) {
  return fetchJson<ProjectReadiness>(`/api/projects/${projectId}/readiness`).then(normalizeProjectReadiness);
}
```

```tsx
// frontend/src/App.tsx
  const hasActiveSourceWork = useMemo(
    () =>
      data.sources.some(
        (source) =>
          source.normalize_status === 'processing' ||
          source.index_status === 'normalization_pending' ||
          source.index_status === 'indexing'
      ),
    [data.sources]
  );

  useEffect(() => {
    if (!projectId || !hasActiveSourceWork) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadWorkbench({ silent: true });
    }, 3000);

    return () => window.clearInterval(timer);
  }, [projectId, hasActiveSourceWork]);
```

```tsx
// frontend/src/features/workbench/WorkbenchPage.tsx
function parseStatusLabel(status: string) {
  if (status === 'parsed') return '已标准化';
  if (status === 'processing') return '标准化中';
  if (status === 'pending') return '标准化中';
  if (status === 'failed') return '标准化失败';
  if (status === 'error') return '标准化异常';
  return status;
}

function indexStatusLabel(status: string) {
  if (status === 'indexed') return '已入库';
  if (status === 'indexing') return '入库中';
  if (status === 'pending') return '待入库';
  if (status === 'normalization_pending') return '待标准化';
  if (status === 'normalization_failed') return '标准化失败';
  if (status === 'index_failed') return '入库失败';
  if (status === 'knowledge_base_missing') return '待初始化知识库';
  if (status === 'not_indexable') return '不可入库';
  if (status === 'error') return '异常';
  return status;
}
```

```tsx
// frontend/src/features/workbench/WorkbenchPage.tsx
                          <Badge variant={statusVariant(sourceNormalizeStatus(source))}>
                            {`标准化：${parseStatusLabel(sourceNormalizeStatus(source))}`}
                          </Badge>
                          <Badge variant={statusVariant(sourceIndexStatus(source))}>
                            {`入库：${indexStatusLabel(sourceIndexStatus(source))}`}
                          </Badge>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-muted">
                          {sourceNormalizeSummary(source) ?? '当前还没有标准化摘要。'}
                        </p>
```

```tsx
// frontend/src/features/workbench/WorkbenchPage.tsx
              {readiness.object_storage ? (
                <div className="rounded-[20px] border border-line bg-slate-50/80 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-ink">七牛对象存储</div>
                      <p className="mt-1 text-sm leading-6 text-muted">{readiness.object_storage.summary}</p>
                      {readiness.object_storage.detail ? (
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">
                          {readiness.object_storage.detail}
                        </p>
                      ) : null}
                    </div>
                    <Badge variant={readinessVariant(readiness.object_storage.status)}>
                      {readiness.object_storage.status}
                    </Badge>
                  </div>
                </div>
              ) : null}

              {readiness.audio_transcription ? (
                <div className="rounded-[20px] border border-line bg-slate-50/80 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-ink">阿里云音频转写</div>
                      <p className="mt-1 text-sm leading-6 text-muted">{readiness.audio_transcription.summary}</p>
                      {readiness.audio_transcription.detail ? (
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">
                          {readiness.audio_transcription.detail}
                        </p>
                      ) : null}
                    </div>
                    <Badge variant={readinessVariant(readiness.audio_transcription.status)}>
                      {readiness.audio_transcription.status}
                    </Badge>
                  </div>
                </div>
              ) : null}
```

- [ ] **Step 4: Run the frontend tests and confirm they pass**

Run:

```powershell
npm test -- --runInBand src/App.test.tsx
```

Workdir:

```text
frontend/
```

Expected:

- PASS `renders audio sources as processing and refreshes while source work is active`
- PASS `shows audio transcript preview and runtime provider cards`

- [ ] **Step 5: Commit the frontend lifecycle updates**

```powershell
git add frontend/src/lib/types.ts frontend/src/lib/api.ts frontend/src/App.tsx frontend/src/features/workbench/WorkbenchPage.tsx frontend/src/App.test.tsx
git commit -m "feat: surface audio processing lifecycle in workbench"
```

## Task 7: Final Regression, Content Preview, and Doc Sync

**Files:**
- Modify: `backend/tests/test_api_flow.py`
- Modify: `docs/planning/fullstack-phase1-todo.md`
- Test: `backend/tests/test_evidence_runtime.py`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add the final audio content preview regression and todo sync**

```python
# backend/tests/test_api_flow.py
def test_audio_source_content_returns_full_transcript_after_processing(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: None,
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={"name": "音频预览项目", "scenario_type": "general", "summary": "test"},
        )
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )
        source_id = upload_response.json()["id"]

        normalized_path = app.state.services.settings.projects_dir / project_id / "sources" / "call.normalized.md"
        normalized_path.write_text("# 音频转写\n\n00:00-00:05 逐笔对账需要人工确认", encoding="utf-8")
        app.state.services.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=str(normalized_path),
            index_input_mode="normalized_text",
            normalize_status="parsed",
            normalize_summary="ASR 已生成转写文本。",
            index_status="indexed",
            index_error=None,
        )

        content_response = client.get(f"/api/projects/{project_id}/sources/{source_id}/content")

    payload = content_response.json()
    assert payload["content_status"] == "full_text"
    assert payload["content_origin"] == "normalized_path"
    assert "00:00-00:05 逐笔对账需要人工确认" in payload["content"]
```

```markdown
<!-- docs/planning/fullstack-phase1-todo.md -->
- [x] 音频 source 走“七牛对象存储 + 阿里云转写 + normalized text + 项目内索引”正式主链路
- [x] 音频 source 支持 processing / failed / indexed 的真实状态暴露
- [x] 音频 source 保持音频样式标记，同时支持标准化全文预览
```

- [ ] **Step 2: Run the backend regression suite**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_audio_pipeline_config.py backend/tests/test_audio_pipeline_schema.py backend/tests/test_object_storage_service.py backend/tests/test_audio_transcription_service.py backend/tests/test_audio_ingestion_orchestrator.py backend/tests/test_source_ingestion_audio.py backend/tests/test_api_flow.py -k "audio or readiness" -v
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_evidence_runtime.py -k "audio" -v
```

Expected:

- All targeted audio backend tests PASS
- Existing `EvidenceRuntime` audio indexing tests still PASS without behavior regression

- [ ] **Step 3: Run the frontend regression suite**

Run:

```powershell
npm test -- --runInBand src/App.test.tsx
```

Workdir:

```text
frontend/
```

Expected:

- PASS on the existing App smoke tests
- PASS on the new audio lifecycle and runtime dialog tests

- [ ] **Step 4: Smoke test the full app manually**

Run backend:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8001
```

Run frontend:

```powershell
npm run dev
```

Workdir:

```text
frontend/
```

Verify manually:

- Upload an audio file and confirm the source immediately shows `标准化：标准化中`
- Open the runtime dialog and confirm both `七牛对象存储` and `阿里云音频转写` cards appear
- Wait for completion and confirm the source changes to `标准化：已标准化` and `入库：已入库`
- Open the source preview and confirm transcript正文可见
- Ask a chat question and confirm citations point back to the audio-derived source

- [ ] **Step 5: Commit verification and doc sync**

```powershell
git add backend/tests/test_api_flow.py docs/planning/fullstack-phase1-todo.md
git commit -m "docs: mark audio asr pipeline verification complete"
```

## Self-Review

### Spec coverage

- 当前现状与目标方案分离：Task 4 and Task 5 stop the current synchronous Docling audio path and add the target async path.
- Qiniu + Aliyun provider boundary: Task 2 and Task 3.
- `normalized.md` 作为唯一进入现有 RAG 的输入：Task 4.
- `processing / parsed / failed` lifecycle: Task 4 and Task 5.
- readiness 扩展到 `object_storage / audio_transcription`: Task 1 and Task 5.
- 前端音频状态、预览和运行面板：Task 6.
- 回归和诚实性验收：Task 7.

### Placeholder scan

- No `TODO`, `TBD`, or “handle appropriately” placeholders remain.
- All file paths exist in the current repo or are explicitly created by the plan.
- The old nonexistent `backend/tests/test_source_ingestion.py` reference has been replaced with `backend/tests/test_source_ingestion_audio.py`.

### Type consistency

- Provider names stay `QINIU_OSS` and `ALIYUN_FILETRANS`.
- Audio processing states stay `processing`, `parsed`, `failed`, `normalization_pending`, `normalization_failed`, `index_failed`.
- Service names stay `ObjectStorageService`, `AudioTranscriptionService`, and `AudioIngestionOrchestrator`.
