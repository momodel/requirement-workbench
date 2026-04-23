PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  scenario_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  seed_key TEXT
);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  upload_kind TEXT NOT NULL,
  storage_path TEXT,
  normalized_path TEXT,
  index_input_mode TEXT,
  notebook_import_mode TEXT,
  normalize_status TEXT,
  parse_status TEXT,
  normalize_summary TEXT,
  parse_summary TEXT,
  index_status TEXT,
  sync_status TEXT,
  index_error TEXT,
  sync_error TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  source_refs_json TEXT,
  created_at TEXT NOT NULL,
  stream_group_id TEXT
);

CREATE TABLE IF NOT EXISTS state_items (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL,
  source_ids_json TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_snapshots (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  trigger_kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  state_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  external_knowledge_base_id TEXT NOT NULL,
  display_name TEXT,
  description TEXT,
  status TEXT NOT NULL,
  status_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_chunks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  knowledge_base_id TEXT REFERENCES knowledge_bases(id) ON DELETE SET NULL,
  chunk_order INTEGER NOT NULL,
  modality TEXT NOT NULL,
  content TEXT NOT NULL,
  locator_json TEXT,
  content_hash TEXT NOT NULL,
  embedding_status TEXT NOT NULL DEFAULT 'pending',
  index_error TEXT,
  indexed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_artifacts (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL,
  content_format TEXT NOT NULL,
  storage_path TEXT,
  metadata_json TEXT,
  body TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_project_id ON sources(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_project_id ON messages(project_id);
CREATE INDEX IF NOT EXISTS idx_state_items_project_id ON state_items(project_id);
CREATE INDEX IF NOT EXISTS idx_state_items_category ON state_items(category);
CREATE INDEX IF NOT EXISTS idx_versions_project_id ON version_snapshots(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_project_id ON demo_artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_project_id ON knowledge_bases(project_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_status ON knowledge_bases(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_bases_project_provider ON knowledge_bases(project_id, provider);
CREATE INDEX IF NOT EXISTS idx_source_chunks_project_id ON source_chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_source_chunks_source_id ON source_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_source_chunks_knowledge_base_id ON source_chunks(knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_source_chunks_embedding_status ON source_chunks(embedding_status);
CREATE INDEX IF NOT EXISTS idx_source_chunks_content_hash ON source_chunks(content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_chunks_source_chunk_order ON source_chunks(source_id, chunk_order);
