import type {
  ArtifactRecord,
  ChatStreamRequest,
  CreateProjectRequest,
  GlobalReadiness,
  KnowledgeBaseRecord,
  MessageRecord,
  ProjectKnowledgeBase,
  ProjectState,
  ProjectReadiness,
  ProjectSummary,
  SourceRecord,
  SseEventPayload,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

type LegacySourceRecord = Omit<
  SourceRecord,
  'index_input_mode' | 'normalize_status' | 'normalize_summary' | 'index_status' | 'index_error'
> & {
  index_input_mode?: string | null;
  normalize_status?: string;
  normalize_summary?: string | null;
  index_status?: string;
  index_error?: string | null;
  notebook_import_mode?: string | null;
  parse_status?: string;
  parse_summary?: string | null;
  sync_status?: string;
  sync_error?: string | null;
};

type LegacyReadinessProvider = {
  provider: string;
  status: string;
  summary: string;
  detail: string | null;
  action_label: string | null;
};

type LegacyReadinessPayload = {
  claude: LegacyReadinessProvider;
  evidence?: LegacyReadinessProvider;
  notebooklm?: LegacyReadinessProvider;
};

// Keep notebook-era field compatibility at the transport edge only.
// UI components should consume the normalized SourceRecord shape exclusively.

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const raw = await response.text();
    let detail = raw;
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as { detail?: unknown };
        if (typeof parsed.detail === 'string') {
          detail = parsed.detail;
        } else if (parsed.detail !== undefined) {
          detail = JSON.stringify(parsed.detail);
        }
      } catch {
        detail = raw;
      }
    }
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function normalizeReadinessStatus(status: string): string {
  if (status === 'binding_required') {
    return 'knowledge_base_missing';
  }
  return status;
}

function normalizeIndexStatus(status: string): string {
  if (status === 'synced') return 'indexed';
  if (status === 'pending_sync') return 'pending';
  if (status === 'sync_failed') return 'index_failed';
  if (status === 'binding_required') return 'knowledge_base_missing';
  return status;
}

function normalizeProviderReadiness<T extends GlobalReadiness | ProjectReadiness>(readiness: T): T {
  const legacyReadiness = readiness as T & LegacyReadinessPayload;
  const evidenceReadiness = legacyReadiness.evidence ?? legacyReadiness.notebooklm;

  return {
    ...readiness,
    claude: {
      ...readiness.claude,
      status: normalizeReadinessStatus(readiness.claude.status),
    },
    evidence: {
      ...(evidenceReadiness ?? {
        provider: 'UNKNOWN',
        status: 'not_configured',
        summary: 'Evidence Runtime 未配置。',
        detail: null,
        action_label: null,
      }),
      status: normalizeReadinessStatus((evidenceReadiness ?? { status: 'not_configured' }).status),
    },
  };
}

function normalizeKnowledgeBaseRecord(
  knowledgeBase: KnowledgeBaseRecord | null | undefined
): KnowledgeBaseRecord | null {
  return knowledgeBase ?? null;
}

function normalizeSourceRecord(source: LegacySourceRecord): SourceRecord {
  const indexInputMode = source.index_input_mode ?? source.notebook_import_mode ?? null;
  const normalizeStatus = source.normalize_status ?? source.parse_status ?? 'pending';
  const normalizeSummary = source.normalize_summary ?? source.parse_summary ?? null;
  const indexStatus = normalizeIndexStatus(source.index_status ?? source.sync_status ?? 'pending');
  const indexError = source.index_error ?? source.sync_error ?? null;

  return {
    id: source.id,
    project_id: source.project_id,
    name: source.name,
    source_kind: source.source_kind,
    upload_kind: source.upload_kind,
    storage_path: source.storage_path,
    normalized_path: source.normalized_path,
    index_input_mode: indexInputMode,
    normalize_status: normalizeStatus,
    normalize_summary: normalizeSummary,
    index_status: indexStatus,
    index_error: indexError,
    created_at: source.created_at,
  };
}

export function listProjects() {
  return fetchJson<ProjectSummary[]>('/api/projects');
}

export function createProject(payload: CreateProjectRequest) {
  return fetchJson<ProjectSummary>('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getGlobalReadiness() {
  return fetchJson<GlobalReadiness>('/api/providers/readiness').then((payload) =>
    normalizeProviderReadiness(payload)
  );
}

export function getProject(projectId: string) {
  return fetchJson<ProjectSummary>(`/api/projects/${projectId}`);
}

export function getProjectReadiness(projectId: string) {
  return fetchJson<ProjectReadiness>(`/api/projects/${projectId}/readiness`).then((payload) => ({
    ...normalizeProviderReadiness(payload),
    knowledge_base: normalizeKnowledgeBaseRecord(payload.knowledge_base),
  }));
}

export function getProjectKnowledgeBase(projectId: string) {
  return fetchJson<ProjectKnowledgeBase>(`/api/projects/${projectId}/knowledge-base`).then(
    (payload) => ({
      ...payload,
      knowledge_base: normalizeKnowledgeBaseRecord(payload.knowledge_base),
      readiness: {
        ...payload.readiness,
        status: normalizeReadinessStatus(payload.readiness.status),
      },
    })
  );
}

export function listSources(projectId: string) {
  return fetchJson<LegacySourceRecord[]>(`/api/projects/${projectId}/sources`).then((sources) =>
    sources.map(normalizeSourceRecord)
  );
}

export function listMessages(projectId: string) {
  return fetchJson<MessageRecord[]>(`/api/projects/${projectId}/messages`);
}

export function getProjectState(projectId: string) {
  return fetchJson<ProjectState>(`/api/projects/${projectId}/state`);
}

export function listArtifacts(projectId: string) {
  return fetchJson<ArtifactRecord[]>(`/api/projects/${projectId}/artifacts`);
}

export async function uploadTextSource(projectId: string, payload: { name: string; text: string }) {
  const formData = new FormData();
  formData.set('upload_kind', 'text');
  formData.set('name', payload.name);
  formData.set('text_content', payload.text);

  return fetchJson<LegacySourceRecord>(`/api/projects/${projectId}/sources`, {
    method: 'POST',
    body: formData,
  }).then(normalizeSourceRecord);
}

export async function uploadUrlSource(projectId: string, payload: { name: string; sourceUrl: string }) {
  const formData = new FormData();
  formData.set('upload_kind', 'url');
  formData.set('name', payload.name);
  formData.set('source_url', payload.sourceUrl);

  return fetchJson<LegacySourceRecord>(`/api/projects/${projectId}/sources`, {
    method: 'POST',
    body: formData,
  }).then(normalizeSourceRecord);
}

export async function uploadFileSources(projectId: string, files: File[]) {
  const formData = new FormData();
  formData.set('upload_kind', 'file');
  formData.set('name', files[0]?.name ?? '批量文件上传');
  for (const file of files) {
    formData.append('files', file);
  }

  return fetchJson<LegacySourceRecord[]>(`/api/projects/${projectId}/sources`, {
    method: 'POST',
    body: formData,
  }).then((sources) => sources.map(normalizeSourceRecord));
}

export function deleteProjectSource(projectId: string, sourceId: string) {
  return fetchJson<{ id: string; project_id: string; name: string; deleted: boolean }>(
    `/api/projects/${projectId}/sources/${sourceId}`,
    {
      method: 'DELETE',
    }
  );
}

export function reindexProjectSource(projectId: string, sourceId: string) {
  return fetchJson<LegacySourceRecord>(`/api/projects/${projectId}/sources/${sourceId}/reindex`, {
    method: 'POST',
  }).then(normalizeSourceRecord);
}

export function initializeProjectKnowledgeBase(projectId: string) {
  return fetchJson<KnowledgeBaseRecord>(`/api/projects/${projectId}/knowledge-base/init`, {
    method: 'POST',
  });
}

export async function generateArtifact(
  projectId: string,
  artifactType: 'document' | 'page_solution' | 'interaction_flow'
) {
  return fetchJson<ArtifactRecord>(`/api/projects/${projectId}/artifacts/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ artifact_type: artifactType }),
  });
}

function parseEventBlock(block: string) {
  const lines = block.split('\n');
  const event = lines.find((line) => line.startsWith('event: '))?.slice(7).trim();
  const dataLine = lines.find((line) => line.startsWith('data: '))?.slice(6).trim();
  if (!event || !dataLine) {
    return null;
  }
  return {
    event,
    data: JSON.parse(dataLine) as SseEventPayload,
  };
}

export async function streamChat(
  projectId: string,
  payload: ChatStreamRequest,
  onEvent: (event: string, data: SseEventPayload) => void
) {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  if (!response.body) {
    throw new Error('SSE response body is empty.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      const parsed = parseEventBlock(block.trim());
      if (parsed) {
        onEvent(parsed.event, parsed.data);
      }
    }
  }

  if (buffer.trim()) {
    const parsed = parseEventBlock(buffer.trim());
    if (parsed) {
      onEvent(parsed.event, parsed.data);
    }
  }
}
