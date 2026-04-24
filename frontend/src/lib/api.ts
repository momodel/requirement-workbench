import type {
  ArtifactRecord,
  ChatStreamRequest,
  CreateProjectRequest,
  DeleteProjectResult,
  GlobalReadiness,
  KnowledgeBaseRecord,
  MessageRecord,
  ProjectKnowledgeBase,
  ProjectState,
  ProjectReadiness,
  ProjectSummary,
  SourceContentRecord,
  SourceRecord,
  SseEventPayload,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

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

type JsonObject = Record<string, unknown>;

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

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null;
}

function hasNullableStringField(record: JsonObject, fieldName: string): boolean {
  return fieldName in record && (record[fieldName] === null || typeof record[fieldName] === 'string');
}

function assertSourceRecord(value: unknown, context: string): asserts value is SourceRecord {
  if (!isJsonObject(value)) {
    throw new Error(`${context} returned an invalid source payload: expected an object.`);
  }

  const requiredStringFields = [
    'id',
    'project_id',
    'name',
    'source_kind',
    'upload_kind',
    'normalize_status',
    'index_status',
    'created_at',
  ] as const;

  for (const fieldName of requiredStringFields) {
    if (typeof value[fieldName] !== 'string' || value[fieldName].length === 0) {
      throw new Error(`${context} returned an invalid source payload: missing canonical field "${fieldName}".`);
    }
  }

  const nullableStringFields = [
    'storage_path',
    'normalized_path',
    'index_input_mode',
    'normalize_summary',
    'index_error',
  ] as const;

  for (const fieldName of nullableStringFields) {
    if (!hasNullableStringField(value, fieldName)) {
      throw new Error(`${context} returned an invalid source payload: missing canonical field "${fieldName}".`);
    }
  }
}

function assertSourceRecordList(value: unknown, context: string): asserts value is SourceRecord[] {
  if (!Array.isArray(value)) {
    throw new Error(`${context} returned an invalid source payload: expected an array.`);
  }

  value.forEach((record, index) => {
    assertSourceRecord(record, `${context} item ${index}`);
  });
}

function assertSourceContentRecord(value: unknown, context: string): asserts value is SourceContentRecord {
  if (!isJsonObject(value)) {
    throw new Error(`${context} returned an invalid source content payload: expected an object.`);
  }

  const requiredStringFields = ['source_id', 'project_id', 'source_name', 'content_status'] as const;
  for (const fieldName of requiredStringFields) {
    if (typeof value[fieldName] !== 'string' || value[fieldName].length === 0) {
      throw new Error(
        `${context} returned an invalid source content payload: missing canonical field "${fieldName}".`
      );
    }
  }

  const nullableStringFields = ['content_origin', 'content', 'detail'] as const;
  for (const fieldName of nullableStringFields) {
    if (!hasNullableStringField(value, fieldName)) {
      throw new Error(
        `${context} returned an invalid source content payload: missing canonical field "${fieldName}".`
      );
    }
  }
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

export function deleteProject(projectId: string) {
  return fetchJson<DeleteProjectResult>(`/api/projects/${projectId}`, {
    method: 'DELETE',
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
  return fetchJson<unknown>(`/api/projects/${projectId}/sources`).then((payload) => {
    assertSourceRecordList(payload, 'Source list');
    return payload;
  });
}

export function getProjectSourceContent(projectId: string, sourceId: string) {
  return fetchJson<unknown>(`/api/projects/${projectId}/sources/${sourceId}/content`).then((payload) => {
    assertSourceContentRecord(payload, 'Source content');
    return payload;
  });
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

  return fetchJson<unknown>(`/api/projects/${projectId}/sources`, {
    method: 'POST',
    body: formData,
  }).then((payload) => {
    assertSourceRecord(payload, 'Text source upload');
    return payload;
  });
}

export async function uploadUrlSource(projectId: string, payload: { name: string; sourceUrl: string }) {
  const formData = new FormData();
  formData.set('upload_kind', 'url');
  formData.set('name', payload.name);
  formData.set('source_url', payload.sourceUrl);

  return fetchJson<unknown>(`/api/projects/${projectId}/sources`, {
    method: 'POST',
    body: formData,
  }).then((payload) => {
    assertSourceRecord(payload, 'URL source upload');
    return payload;
  });
}

export async function uploadFileSources(projectId: string, files: File[]) {
  const formData = new FormData();
  formData.set('upload_kind', 'file');
  formData.set('name', files[0]?.name ?? '批量文件上传');
  for (const file of files) {
    formData.append('files', file);
  }

  return fetchJson<unknown>(`/api/projects/${projectId}/sources`, {
    method: 'POST',
    body: formData,
  }).then((payload) => {
    assertSourceRecordList(payload, 'File source upload');
    return payload;
  });
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
  return fetchJson<unknown>(`/api/projects/${projectId}/sources/${sourceId}/reindex`, {
    method: 'POST',
  }).then((payload) => {
    assertSourceRecord(payload, 'Source reindex');
    return payload;
  });
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
