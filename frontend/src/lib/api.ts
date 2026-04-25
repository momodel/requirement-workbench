import type {
  ArtifactRecord,
  ChatStreamRequest,
  CreateProjectRequest,
  GlobalReadiness,
  MessageRecord,
  ProjectState,
  ProjectReadiness,
  ProjectSummary,
  SourceRecord,
  SseEventPayload,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

type OptionalAudioReadiness = {
  object_storage?: GlobalReadiness['object_storage'];
  audio_transcription?: GlobalReadiness['audio_transcription'];
};

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

function normalizeAudioReadiness<T extends OptionalAudioReadiness>(
  payload: T
): T & {
  object_storage: NonNullable<GlobalReadiness['object_storage']> | null;
  audio_transcription: NonNullable<GlobalReadiness['audio_transcription']> | null;
} {
  return {
    ...payload,
    object_storage: payload.object_storage ?? null,
    audio_transcription: payload.audio_transcription ?? null,
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

export async function getGlobalReadiness() {
  const readiness = await fetchJson<GlobalReadiness>('/api/providers/readiness');
  return normalizeAudioReadiness(readiness);
}

export function getProject(projectId: string) {
  return fetchJson<ProjectSummary>(`/api/projects/${projectId}`);
}

export async function getProjectReadiness(projectId: string) {
  const readiness = await fetchJson<ProjectReadiness>(`/api/projects/${projectId}/readiness`);
  return normalizeAudioReadiness(readiness);
}

export function listSources(projectId: string) {
  return fetchJson<SourceRecord[]>(`/api/projects/${projectId}/sources`);
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
  });
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
  return fetchJson<SourceRecord>(`/api/projects/${projectId}/sources/${sourceId}/reindex`, {
    method: 'POST',
  });
}

export function initProjectKnowledgeBase(projectId: string) {
  return fetchJson(`/api/projects/${projectId}/knowledge-base/init`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
