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

function normalizeProviderReadiness<T extends GlobalReadiness | ProjectReadiness>(readiness: T): T {
  const evidence = readiness.evidence ?? readiness.notebooklm;
  return {
    ...readiness,
    evidence,
    notebooklm: readiness.notebooklm ?? evidence,
  };
}

function normalizeKnowledgeBaseRecord(
  knowledgeBase: KnowledgeBaseRecord | null | undefined
): KnowledgeBaseRecord | null {
  return knowledgeBase ?? null;
}

function normalizeSourceRecord(source: SourceRecord): SourceRecord {
  const indexInputMode = source.index_input_mode ?? source.notebook_import_mode ?? null;
  const normalizeStatus = source.normalize_status ?? source.parse_status ?? 'pending';
  const normalizeSummary = source.normalize_summary ?? source.parse_summary ?? null;
  const indexStatus = source.index_status ?? source.sync_status ?? 'pending';
  const indexError = source.index_error ?? source.sync_error ?? null;

  return {
    ...source,
    index_input_mode: indexInputMode,
    normalize_status: normalizeStatus,
    normalize_summary: normalizeSummary,
    index_status: indexStatus,
    index_error: indexError,
    notebook_import_mode: source.notebook_import_mode ?? indexInputMode,
    parse_status: source.parse_status ?? normalizeStatus,
    parse_summary: source.parse_summary ?? normalizeSummary,
    sync_status: source.sync_status ?? indexStatus,
    sync_error: source.sync_error ?? indexError,
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
    notebook_binding: payload.notebook_binding ?? null,
  }));
}

export function getProjectKnowledgeBase(projectId: string) {
  return fetchJson<ProjectKnowledgeBase>(`/api/projects/${projectId}/knowledge-base`).then(
    (payload) => ({
      ...payload,
      knowledge_base: normalizeKnowledgeBaseRecord(payload.knowledge_base),
    })
  );
}

export function listSources(projectId: string) {
  return fetchJson<SourceRecord[]>(`/api/projects/${projectId}/sources`).then((sources) =>
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

  return fetchJson<SourceRecord>(`/api/projects/${projectId}/sources`, {
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

  return fetchJson<SourceRecord[]>(`/api/projects/${projectId}/sources`, {
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
  return fetchJson<SourceRecord>(`/api/projects/${projectId}/sources/${sourceId}/reindex`, {
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
