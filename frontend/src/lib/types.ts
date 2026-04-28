export type ProjectSummary = {
  id: string;
  name: string;
  scenario_type: string;
  summary: string;
  status: string;
  created_at: string;
  updated_at: string;
  seed_key: string | null;
};

export type CreateProjectRequest = {
  name: string;
  scenario_type: string;
  summary: string;
};

export type KnowledgeBaseRecord = {
  id: string;
  project_id: string;
  provider: string;
  external_knowledge_base_id: string;
  display_name: string | null;
  description: string | null;
  status: string;
  status_error: string | null;
  created_at: string;
  updated_at: string;
};

export type ProviderReadiness = {
  provider: string;
  status: string;
  summary: string;
  detail: string | null;
  action_label: string | null;
};

export type GlobalReadiness = {
  claude: ProviderReadiness;
  evidence: ProviderReadiness;
  object_storage: ProviderReadiness | null;
  audio_transcription: ProviderReadiness | null;
  wiki?: ProviderReadiness | null;
};

export type ProjectReadiness = {
  project_id: string;
  claude: ProviderReadiness;
  evidence: ProviderReadiness;
  object_storage: ProviderReadiness | null;
  audio_transcription: ProviderReadiness | null;
  wiki?: ProviderReadiness | null;
  knowledge_base: KnowledgeBaseRecord | null;
};

export type MobileVoiceBootstrap = {
  project: ProjectSummary;
  evidence: ProviderReadiness;
  voice: ProviderReadiness;
  initial_prompt: string;
  recent_rounds: SourceRecord[];
};

export type SourceRecord = {
  id: string;
  project_id: string;
  name: string;
  source_kind: string;
  upload_kind: string;
  storage_path: string | null;
  normalized_path: string | null;
  index_input_mode: string | null;
  normalize_status: string;
  normalize_summary: string | null;
  index_status: string;
  index_error: string | null;
  wiki_sync_status?: string | null;
  wiki_error?: string | null;
  wiki_maintained_at?: string | null;
  created_at: string;
};

export type SourceContentRecord = {
  source_id: string;
  project_id: string;
  source_name: string;
  content_status: string;
  content_origin: string | null;
  content: string | null;
  detail: string;
};

export type WikiPageMeta = {
  slug: string;
  title: string;
  kind: string;
  source_ids: string[];
  last_maintained_at: string | null;
  last_maintained_by: string | null;
};

export type WikiPage = WikiPageMeta & {
  body: string;
};

export type WikiRecord = {
  project_id: string;
  page_count: number;
  last_maintained_at: string | null;
  pending_source_ids: string[];
  detail: string | null;
};

export type WikiMaintenanceResult = {
  project_id: string;
  status: 'maintained' | 'skipped' | 'failed';
  pages_changed: string[];
  log_entry: string | null;
  error: string | null;
  trigger_kind: string | null;
};

export type MessageRecord = {
  id: string;
  role: string;
  content: string;
  source_refs: Array<{ title?: string; snippet?: string; source_id?: string }>;
  image_results?: ChatImageResult[];
  created_at: string;
  stream_group_id: string | null;
  status_label?: string | null;
  status_phase?: string | null;
  action_events?: MessageActionEvent[];
};

export type ChatImageResult = {
  id: string;
  title: string;
  summary?: string | null;
  url: string;
  content_type?: string | null;
  prompt?: string | null;
};

export type MessageActionEvent = {
  id: string;
  kind:
    | 'status'
    | 'tool_running'
    | 'tool_completed'
    | 'state'
    | 'version'
    | 'artifact'
    | 'citation';
  label: string;
};

export type StateItem = {
  id: string;
  title: string;
  body: string;
  status: string;
  category: string | null;
  updated_at: string | null;
  source_ids: string[];
};

export type ProjectState = {
  current_understanding: StateItem[];
  pending_items: StateItem[];
  confirmed_items: StateItem[];
  conflict_items: StateItem[];
  mvp_items: StateItem[];
  versions: StateItem[];
  artifacts: StateItem[];
};

export type ArtifactRecord = {
  id: string;
  project_id: string;
  artifact_type: 'document' | 'page_solution' | 'interaction_flow' | string;
  title: string;
  summary: string;
  status: string;
  content_format: string;
  storage_path: string | null;
  preview_url: string | null;
  body: string | null;
  updated_at: string;
};

export type ChatStreamRequest = {
  message: string;
  selected_source_ids: string[];
  request_artifact_types: Array<'document' | 'page_solution' | 'interaction_flow'>;
  image_attachments?: ChatImageAttachment[];
  client_context?: Record<string, unknown>;
};

export type ChatImageAttachment = {
  name: string;
  content_type: string;
  data_url: string;
};

export type ChatCitation = {
  title: string;
  snippet?: string | null;
  source_id?: string | null;
};

export type SseEventPayload = {
  project_id: string;
  [key: string]: unknown;
  created_at: string;
  op?: 'replace' | 'upsert' | 'remove';
  items?: unknown[];
  text?: string;
  replace?: boolean;
  label?: string;
  phase?: string;
  provider?: string;
  message?: string;
  stream_group_id?: string;
};
