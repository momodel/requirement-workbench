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
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  upload_kind TEXT NOT NULL,
  storage_path TEXT,
  normalized_path TEXT,
  notebook_import_mode TEXT,
  parse_status TEXT NOT NULL,
  parse_summary TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  source_refs_json TEXT,
  created_at TEXT NOT NULL,
  stream_group_id TEXT
);

CREATE TABLE IF NOT EXISTS state_items (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL,
  source_ids_json TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS version_snapshots (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  trigger_kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  state_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notebook_bindings (
  project_id TEXT PRIMARY KEY,
  notebook_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  sync_status TEXT NOT NULL,
  last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS demo_artifacts (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL,
  content_format TEXT NOT NULL,
  storage_path TEXT,
  metadata_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
