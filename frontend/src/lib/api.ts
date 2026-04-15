import type {
  ArtifactRecord,
  ChatEvent,
  ProjectState,
  ProjectSummary,
  SourceRecord
} from './types';

const API_BASE = '/api';

const seedProject: ProjectSummary = {
  id: 'seed-reconciliation',
  name: '业财逐笔对账',
  summary: '默认 seed project，用来验证全栈一期的项目、资料、聊天和沉淀链路。',
  status: 'seed',
  scenarioType: 'financial-reconciliation',
  updatedAt: '刚刚'
};

const seedSources: SourceRecord[] = [
  {
    id: 'src-order-fields',
    name: '订单字段说明.md',
    sourceKind: 'markdown',
    uploadKind: 'seed',
    parseStatus: 'parsed',
    parseSummary: '包含订单号、业务类型、含税金额和退款标记。',
    syncStatus: 'pending'
  },
  {
    id: 'src-finance-rules',
    name: '财务科目口径.pdf',
    sourceKind: 'pdf',
    uploadKind: 'seed',
    parseStatus: 'parsed',
    parseSummary: '定义结算、退款、冲销对应的财务科目口径。',
    syncStatus: 'pending'
  }
];

const seedState: ProjectState = {
  currentUnderstanding: [
    {
      id: 'understanding-1',
      title: '当前工作台骨架已切到 project-first',
      body: '后续状态不再挂在 stage 页面上，而是围绕项目对象持续维护。'
    }
  ],
  pendingItems: [
    {
      id: 'pending-1',
      title: '接入真实 SSE 聊天流',
      body: '当前前端先用 fallback seed 渲染，后续替换为真实 API。'
    }
  ],
  confirmedItems: [],
  conflictItems: [],
  mvpItems: [],
  versions: [
    {
      id: 'version-1',
      title: '初始化版本',
      body: '仓库已完成旧 demo 归档与一期主工程骨架创建。'
    }
  ],
  artifacts: []
};

type BackendProjectSummary = {
  id: string;
  name: string;
  summary: string;
  status: string;
  scenario_type: string;
  updated_at?: string;
  updatedAt?: string;
};

type BackendSourceRecord = {
  id: string;
  name: string;
  source_kind: string;
  upload_kind?: string;
  storage_path?: string;
  normalized_path?: string;
  parse_status: string;
  parse_summary?: string;
  sync_status?: string;
};

type BackendStateItem = {
  id: string;
  title: string;
  body: string;
};

type BackendProjectState = {
  current_understanding: BackendStateItem[];
  pending_items: BackendStateItem[];
  confirmed_items: BackendStateItem[];
  conflict_items: BackendStateItem[];
  mvp_items: BackendStateItem[];
  versions: BackendStateItem[];
  artifacts: BackendStateItem[];
};

type BackendArtifactRecord = {
  id: string;
  artifact_type: string;
  title: string;
  summary: string;
  status: string;
  content_format: string;
  storage_path?: string;
};

async function tryFetchJson<T>(path: string): Promise<T | null> {
  if (typeof fetch !== 'function') {
    return null;
  }

  try {
    const response = await fetch(`${API_BASE}${path}`);
    if (!response.ok) {
      return null;
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function tryFetchText(path: string): Promise<string | null> {
  if (typeof fetch !== 'function') {
    return null;
  }

  try {
    const response = await fetch(`${API_BASE}${path}`);
    if (!response.ok) {
      return null;
    }

    return await response.text();
  } catch {
    return null;
  }
}

async function postJson<T>(path: string, payload: Record<string, unknown>): Promise<T | null> {
  if (typeof fetch !== 'function') {
    return null;
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function mapProjectSummary(project: BackendProjectSummary): ProjectSummary {
  return {
    id: project.id,
    name: project.name,
    summary: project.summary,
    status: project.status,
    scenarioType: project.scenario_type,
    updatedAt: project.updated_at ?? project.updatedAt ?? '刚刚'
  };
}

function mapSourceRecord(source: BackendSourceRecord): SourceRecord {
  return {
    id: source.id,
    name: source.name,
    sourceKind: source.source_kind,
    uploadKind: source.upload_kind,
    storagePath: source.storage_path,
    normalizedPath: source.normalized_path,
    parseStatus: source.parse_status,
    parseSummary: source.parse_summary,
    syncStatus: source.sync_status ?? 'pending'
  };
}

function mapProjectState(state: BackendProjectState): ProjectState {
  return {
    currentUnderstanding: state.current_understanding,
    pendingItems: state.pending_items,
    confirmedItems: state.confirmed_items,
    conflictItems: state.conflict_items,
    mvpItems: state.mvp_items,
    versions: state.versions,
    artifacts: state.artifacts
  };
}

function mapArtifactRecord(record: BackendArtifactRecord): ArtifactRecord {
  return {
    id: record.id,
    artifactType: record.artifact_type,
    title: record.title,
    summary: record.summary,
    status: record.status,
    contentFormat: record.content_format,
    storagePath: record.storage_path
  };
}

function parseSsePayload(text: string): ChatEvent[] {
  return text
    .trim()
    .split('\n\n')
    .filter(Boolean)
    .map((block) => {
      const eventLine = block
        .split('\n')
        .find((line) => line.startsWith('event:'));
      const dataLine = block
        .split('\n')
        .find((line) => line.startsWith('data:'));

      return {
        event: eventLine?.replace('event:', '').trim() ?? 'message_chunk',
        data: dataLine ? (JSON.parse(dataLine.replace('data:', '').trim()) as Record<string, unknown>) : {}
      };
    });
}

function parseSseBlock(block: string): ChatEvent | null {
  const eventLine = block
    .split('\n')
    .find((line) => line.startsWith('event:'));
  const dataLine = block
    .split('\n')
    .find((line) => line.startsWith('data:'));

  if (!eventLine || !dataLine) {
    return null;
  }

  return {
    event: eventLine.replace('event:', '').trim(),
    data: JSON.parse(dataLine.replace('data:', '').trim()) as Record<string, unknown>
  };
}

function encodeBase64(bytes: Uint8Array): string {
  const binary = Array.from(bytes, (byte) => String.fromCharCode(byte)).join('');
  if (typeof btoa === 'function') {
    return btoa(binary);
  }

  const bufferImpl = (globalThis as { Buffer?: { from(input: Uint8Array): { toString(type: string): string } } }).Buffer;
  if (bufferImpl) {
    return bufferImpl.from(bytes).toString('base64');
  }

  throw new Error('No base64 encoder available in current runtime.');
}

async function getFileBytes(file: File): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === 'function') {
    return new Uint8Array(await file.arrayBuffer());
  }

  if (typeof file.text === 'function') {
    const text = await file.text();
    return new TextEncoder().encode(text);
  }

  return new Uint8Array();
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const projects = await tryFetchJson<BackendProjectSummary[]>('/projects');
  if (projects) {
    return projects.map(mapProjectSummary);
  }

  return [seedProject];
}

export async function createProject(
  name: string,
  summary: string,
  scenarioType: string
): Promise<ProjectSummary> {
  const project = await postJson<BackendProjectSummary>('/projects', {
    name,
    summary,
    scenario_type: scenarioType
  });

  if (project) {
    return mapProjectSummary(project);
  }

  return {
    id: `project-${Date.now()}`,
    name,
    summary,
    status: 'draft',
    scenarioType,
    updatedAt: '刚刚'
  };
}

export async function getProject(projectId: string): Promise<ProjectSummary> {
  const project = await tryFetchJson<BackendProjectSummary>(`/projects/${projectId}`);
  if (project) {
    return mapProjectSummary(project);
  }

  if (projectId === seedProject.id) {
    return seedProject;
  }

  throw new Error(`Unknown project: ${projectId}`);
}

export async function listSources(projectId: string): Promise<SourceRecord[]> {
  const sources = await tryFetchJson<BackendSourceRecord[]>(`/projects/${projectId}/sources`);
  if (sources) {
    return sources.map(mapSourceRecord);
  }

  if (projectId === seedProject.id) {
    return seedSources;
  }

  return [];
}

export async function getProjectState(projectId: string): Promise<ProjectState> {
  const state = await tryFetchJson<BackendProjectState>(`/projects/${projectId}/state`);
  if (state) {
    return mapProjectState(state);
  }

  if (projectId === seedProject.id) {
    return seedState;
  }

  return {
    currentUnderstanding: [],
    pendingItems: [],
    confirmedItems: [],
    conflictItems: [],
    mvpItems: [],
    versions: [],
    artifacts: []
  };
}

export async function createTextSource(
  projectId: string,
  name: string,
  text: string
): Promise<SourceRecord> {
  const source = await postJson<BackendSourceRecord>(`/projects/${projectId}/sources`, {
    upload_kind: 'text',
    name,
    text
  });

  if (source) {
    return mapSourceRecord(source);
  }

  return {
    id: `seed-${Date.now()}`,
    name,
    sourceKind: 'text',
    uploadKind: 'text',
    parseStatus: 'parsed',
    parseSummary: text.slice(0, 80),
    syncStatus: 'pending'
  };
}

export async function createUrlSource(
  projectId: string,
  name: string,
  url: string
): Promise<SourceRecord> {
  const source = await postJson<BackendSourceRecord>(`/projects/${projectId}/sources`, {
    upload_kind: 'url',
    name,
    url
  });

  if (source) {
    return mapSourceRecord(source);
  }

  return {
    id: `seed-${Date.now()}`,
    name,
    sourceKind: 'url',
    uploadKind: 'url',
    parseStatus: 'parsed',
    parseSummary: url,
    syncStatus: 'pending'
  };
}

export async function createFileSource(projectId: string, file: File): Promise<SourceRecord> {
  const bytes = await getFileBytes(file);
  const sourceKind = file.name.split('.').pop()?.toLowerCase() ?? 'file';
  const source = await postJson<BackendSourceRecord>(`/projects/${projectId}/sources`, {
    upload_kind: 'file',
    name: file.name,
    source_kind: sourceKind,
    mime_type: file.type,
    content_base64: encodeBase64(bytes)
  });

  if (source) {
    return mapSourceRecord(source);
  }

  return {
    id: `seed-${Date.now()}`,
    name: file.name,
    sourceKind,
    uploadKind: 'file',
    parseStatus: 'parsed',
    parseSummary: `${file.name} 已作为本地 fallback 文件接入。`,
    syncStatus: 'pending'
  };
}

export async function sendChatRound(
  projectId: string,
  message: string,
  onEvent?: (event: ChatEvent) => void
): Promise<ChatEvent[]> {
  if (typeof fetch !== 'function') {
    const fallbackEvents = [
      {
        event: 'message_chunk',
        data: { project_id: projectId, text: `已收到输入：${message}` }
      },
      { event: 'done', data: { project_id: projectId } }
    ];
    fallbackEvents.forEach((event) => onEvent?.(event));
    return fallbackEvents;
  }

  try {
    const response = await fetch(`${API_BASE}/projects/${projectId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ message })
    });

    if (!response.ok) {
      throw new Error('chat stream failed');
    }

    if (response.body) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const events: ChatEvent[] = [];
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
          const event = parseSseBlock(block.trim());
          if (!event) {
            continue;
          }
          events.push(event);
          onEvent?.(event);
        }
      }

      if (buffer.trim()) {
        const event = parseSseBlock(buffer.trim());
        if (event) {
          events.push(event);
          onEvent?.(event);
        }
      }

      if (events.length > 0) {
        return events;
      }
    }

    const payload = await response.text();
    const events = parseSsePayload(payload);
    events.forEach((event) => onEvent?.(event));
    return events;
  } catch {
    const fallbackEvents = [
      {
        event: 'message_chunk',
        data: { project_id: projectId, text: `已收到输入：${message}` }
      },
      { event: 'done', data: { project_id: projectId } }
    ];
    fallbackEvents.forEach((event) => onEvent?.(event));
    return fallbackEvents;
  }
}

export async function generateArtifact(
  projectId: string,
  artifactType: string
): Promise<ArtifactRecord> {
  const artifact = await postJson<BackendArtifactRecord>(
    `/projects/${projectId}/artifacts/generate`,
    { artifact_type: artifactType }
  );

  if (artifact) {
    return mapArtifactRecord(artifact);
  }

  return {
    id: `artifact-${Date.now()}`,
    artifactType,
    title: `${artifactType} 占位稿`,
    summary: '后端未启动，当前返回本地 fallback artifact。',
    status: 'fallback',
    contentFormat: artifactType === 'document' ? 'json' : 'html'
  };
}

export async function listArtifacts(projectId: string): Promise<ArtifactRecord[]> {
  const artifacts = await tryFetchJson<BackendArtifactRecord[]>(`/projects/${projectId}/artifacts`);
  if (artifacts) {
    return artifacts.map(mapArtifactRecord);
  }

  return [];
}

export async function getArtifactContent(projectId: string, artifactId: string): Promise<string> {
  const content = await tryFetchText(`/projects/${projectId}/artifacts/${artifactId}/content`);
  if (content) {
    return content;
  }

  return JSON.stringify({ title: 'Fallback Artifact', sections: [] }, null, 2);
}
