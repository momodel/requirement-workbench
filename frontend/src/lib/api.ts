import type {
  ArtifactRecord,
  BindNotebookRequest,
  ChatStreamRequest,
  CreateProjectRequest,
  CreateNotebookBindingResponse,
  CreateNotebookRequest,
  GlobalReadiness,
  MessageRecord,
  NotebookLibraryItem,
  NotebookBindingRecord,
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
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
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
  return fetchJson<GlobalReadiness>('/api/providers/readiness');
}

export function getProject(projectId: string) {
  return fetchJson<ProjectSummary>(`/api/projects/${projectId}`);
}

export function getProjectReadiness(projectId: string) {
  return fetchJson<ProjectReadiness>(`/api/projects/${projectId}/readiness`);
}

export function listProjectNotebookLibrary(projectId: string) {
  return fetchJson<NotebookLibraryItem[]>(`/api/projects/${projectId}/notebook-library`);
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

export function retryProjectSourceSync(projectId: string, sourceId: string) {
  return fetchJson<SourceRecord>(`/api/projects/${projectId}/sources/${sourceId}/retry-sync`, {
    method: 'POST',
  });
}

export function bindProjectNotebook(projectId: string, payload: BindNotebookRequest) {
  return fetchJson<NotebookBindingRecord>(`/api/projects/${projectId}/notebook-binding`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function createAndBindProjectNotebook(projectId: string, payload: CreateNotebookRequest = {}) {
  return fetchJson<CreateNotebookBindingResponse>(`/api/projects/${projectId}/notebook-create-and-bind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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
