import { useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom';

import { ProjectsPage } from './features/projects/ProjectsPage';
import { WorkbenchPage } from './features/workbench/WorkbenchPage';
import {
  bindProjectNotebook,
  createProject,
  createAndBindProjectNotebook,
  deleteProjectSource,
  getGlobalReadiness,
  getProject,
  getProjectReadiness,
  getProjectState,
  listArtifacts,
  listMessages,
  listProjectNotebookLibrary,
  listProjects,
  listSources,
  retryProjectSourceSync,
  streamChat,
  uploadFileSources,
  uploadTextSource,
} from './lib/api';
import type {
  ArtifactRecord,
  GlobalReadiness,
  MessageActionEvent,
  MessageRecord,
  NotebookLibraryItem,
  ProjectReadiness,
  ProjectState,
  ProjectSummary,
  SourceRecord,
  StateItem,
} from './lib/types';

type WorkbenchData = {
  project: ProjectSummary | null;
  sources: SourceRecord[];
  messages: MessageRecord[];
  state: ProjectState | null;
  artifacts: ArtifactRecord[];
  notebookLibrary: NotebookLibraryItem[];
};

type Notice = {
  id: string;
  kind: 'error' | 'info';
  title: string;
  body: string;
};

function emptyState(): ProjectState {
  return {
    current_understanding: [],
    pending_items: [],
    confirmed_items: [],
    conflict_items: [],
    mvp_items: [],
    versions: [],
    artifacts: [],
  };
}

function upsertItems(existing: StateItem[], incoming: StateItem[]) {
  const map = new Map(existing.map((item) => [item.id, item]));
  for (const item of incoming) {
    map.set(item.id, item);
  }
  return Array.from(map.values());
}

function upsertArtifacts(existing: ArtifactRecord[], incoming: ArtifactRecord[]) {
  const map = new Map(existing.map((item) => [item.id, item]));
  for (const item of incoming) {
    map.set(item.id, item);
  }
  return Array.from(map.values());
}

function collectItemIds(items: StateItem[] | undefined) {
  return (items ?? []).map((item) => item.id);
}

function updateAssistantMessage(
  messages: MessageRecord[],
  assistantId: string,
  updater: (message: MessageRecord) => MessageRecord
) {
  return messages.map((item) => (item.id === assistantId ? updater(item) : item));
}

function appendAssistantAction(
  messages: MessageRecord[],
  assistantId: string,
  action: MessageActionEvent
) {
  return updateAssistantMessage(messages, assistantId, (item) => {
    const actions = item.action_events ?? [];
    const existingIndex = actions.findIndex((current) => current.id === action.id);

    if (existingIndex >= 0) {
      const nextActions = [...actions];
      nextActions[existingIndex] = action;
      return { ...item, action_events: nextActions };
    }

    return {
      ...item,
      action_events: [...actions, action],
    };
  });
}

function buildPatchAction(
  kind: MessageActionEvent['kind'],
  label: string,
  payload: { created_at: string; items?: unknown[] }
): MessageActionEvent {
  const count = Array.isArray(payload.items) ? payload.items.length : 0;
  return {
    id: `${kind}:${payload.created_at}:${label}:${count}`,
    kind,
    label: count > 0 ? `${label}（${count}）` : label,
  };
}

function buildArtifactAction(items: ArtifactRecord[], createdAt: string): MessageActionEvent {
  const typeLabelMap: Record<string, string> = {
    document: '文档稿',
    page_solution: '页面方案',
    interaction_flow: '交互稿',
  };
  const labels = items.map((item) => typeLabelMap[item.artifact_type] ?? item.title).slice(0, 3);

  return {
    id: `artifact:${createdAt}:${items.map((item) => item.id).join(',')}`,
    kind: 'artifact',
    label:
      labels.length > 0
        ? `已生成交付物：${labels.join('、')}`
        : '已生成交付物',
  };
}

function buildStatusAction(payload: {
  created_at: string;
  phase?: string;
  label?: string;
}): MessageActionEvent {
  const phase = payload.phase ?? '';
  let kind: MessageActionEvent['kind'] = 'status';
  if (phase.startsWith('tool_running:')) {
    kind = 'tool_running';
  } else if (phase.startsWith('tool_completed:')) {
    kind = 'tool_completed';
  }

  return {
    id: `status:${phase || payload.created_at}`,
    kind,
    label: payload.label ?? '',
  };
}

function HomeRoute() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [readiness, setReadiness] = useState<GlobalReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void Promise.all([listProjects(), getGlobalReadiness()])
      .then(([nextProjects, nextReadiness]) => {
        setProjects(nextProjects);
        setReadiness(nextReadiness);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return (
      <main className="min-h-screen p-8 text-ink">
        <div className="mx-auto max-w-3xl rounded-[28px] border border-rose-200 bg-rose-50 p-6 text-rose-800 shadow-panel">
          <div className="text-sm font-medium uppercase tracking-[0.18em]">加载失败</div>
          <p className="mt-3 leading-7">{error}</p>
        </div>
      </main>
    );
  }

  async function handleCreateProject(payload: {
    name: string;
    scenario_type: string;
    summary: string;
  }) {
    setCreating(true);
    try {
      const project = await createProject(payload);
      if (readiness?.notebooklm.status === 'ready') {
        await createAndBindProjectNotebook(project.id);
      }
      setProjects((current) => [project, ...current]);
      navigate(`/projects/${project.id}/workbench`);
    } catch (err) {
      const message = err instanceof Error ? err.message : '创建项目失败。';
      setError(message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <ProjectsPage
      projects={projects}
      readiness={readiness}
      creating={creating}
      onCreateProject={handleCreateProject}
    />
  );
}

function WorkbenchRoute() {
  const { projectId = '' } = useParams();
  const [data, setData] = useState<WorkbenchData>({
    project: null,
    sources: [],
    messages: [],
    state: null,
    artifacts: [],
    notebookLibrary: [],
  });
  const [loading, setLoading] = useState(true);
  const [readiness, setReadiness] = useState<ProjectReadiness | null>(null);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [bindingNotebook, setBindingNotebook] = useState(false);
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [retryingSourceId, setRetryingSourceId] = useState<string | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [recentInsightIds, setRecentInsightIds] = useState<string[]>([]);
  const autoBindAttemptedProjectId = useRef<string | null>(null);
  const recentInsightTimerRef = useRef<number | null>(null);

  function markRecentInsights(items: StateItem[]) {
    const nextIds = collectItemIds(items);
    if (nextIds.length === 0) {
      return;
    }

    setRecentInsightIds(nextIds);
    if (recentInsightTimerRef.current) {
      window.clearTimeout(recentInsightTimerRef.current);
    }
    recentInsightTimerRef.current = window.setTimeout(() => {
      setRecentInsightIds([]);
      recentInsightTimerRef.current = null;
    }, 4000);
  }

  async function loadWorkbench(options?: { silent?: boolean }) {
    if (!options?.silent) {
      setLoading(true);
    }
    try {
      const [project, sources, messages, state, artifacts] = await Promise.all([
        getProject(projectId),
        listSources(projectId),
        listMessages(projectId),
        getProjectState(projectId),
        listArtifacts(projectId),
      ]);
      setData((current) => ({
        ...current,
        project,
        sources,
        messages,
        state,
        artifacts,
      }));

      void Promise.allSettled([
        listProjectNotebookLibrary(projectId),
        getProjectReadiness(projectId),
      ]).then(([notebookLibraryResult, readinessResult]) => {
        if (notebookLibraryResult.status === 'fulfilled') {
          setData((current) => ({
            ...current,
            notebookLibrary: notebookLibraryResult.value,
          }));
        } else {
          const message =
            notebookLibraryResult.reason instanceof Error
              ? notebookLibraryResult.reason.message
              : 'Notebook 列表加载失败。';
          setNotices((current) => [
            {
              id: `notebook-library-${Date.now()}`,
              kind: 'info',
              title: 'Notebook 列表加载较慢',
              body: message,
            },
            ...current,
          ]);
        }

        if (readinessResult.status === 'fulfilled') {
          setReadiness(readinessResult.value);
        } else {
          const message =
            readinessResult.reason instanceof Error
              ? readinessResult.reason.message
              : 'Provider 状态加载失败。';
          setNotices((current) => [
            {
              id: `readiness-${Date.now()}`,
              kind: 'info',
              title: '运行状态加载较慢',
              body: message,
            },
            ...current,
          ]);
        }
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : '加载工作台失败。';
      setNotices((current) => [
        {
          id: `load-${Date.now()}`,
          kind: 'error',
          title: '工作台加载失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    autoBindAttemptedProjectId.current = null;
    setRecentInsightIds([]);
    void loadWorkbench();
  }, [projectId]);

  useEffect(() => {
    return () => {
      if (recentInsightTimerRef.current) {
        window.clearTimeout(recentInsightTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!data.project || bindingNotebook || readiness?.notebooklm.status !== 'binding_required') {
      return;
    }
    if (autoBindAttemptedProjectId.current === projectId) {
      return;
    }

    autoBindAttemptedProjectId.current = projectId;
    void ensureProjectNotebookBinding();
  }, [bindingNotebook, data.project, projectId, readiness?.notebooklm.status]);

  async function ensureProjectNotebookBinding() {
    if (bindingNotebook || readiness?.notebooklm.status !== 'binding_required') {
      return true;
    }

    setBindingNotebook(true);
    try {
      await createAndBindProjectNotebook(projectId);
      await loadWorkbench({ silent: true });
      return true;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : '自动创建并绑定项目 Notebook 失败。';
      setNotices((current) => [
        {
          id: `auto-bind-${Date.now()}`,
          kind: 'error',
          title: '项目 Notebook 自动绑定失败',
          body: message,
        },
        ...current,
      ]);
      return false;
    } finally {
      setBindingNotebook(false);
    }
  }

  async function handleSendMessage(message: string) {
    const notebookReady = await ensureProjectNotebookBinding();
    if (!notebookReady) {
      return;
    }

    setSending(true);
    const userMessage: MessageRecord = {
      id: `local-user-${Date.now()}`,
      role: 'user',
      content: message,
      source_refs: [],
      created_at: new Date().toISOString(),
      stream_group_id: null,
    };
    const assistantId = `local-assistant-${Date.now()}`;

    flushSync(() => {
      setData((current) => ({
        ...current,
        messages: [
          ...current.messages,
          userMessage,
          {
            id: assistantId,
            role: 'assistant',
            content: '',
            source_refs: [],
            created_at: new Date().toISOString(),
            stream_group_id: null,
            status_label: '已接收问题，准备开始分析',
            status_phase: 'received',
          },
        ],
      }));
    });

    try {
      await streamChat(
        projectId,
        {
          message,
          selected_source_ids: [],
          request_artifact_types: [],
          client_context: { route: 'workbench' },
        },
        (event, payload) => {
          if (event === 'assistant_status' && payload.label) {
            const shouldRecordAction = payload.phase !== 'agent_started';
            setData((current) => ({
              ...current,
              messages: shouldRecordAction
                ? appendAssistantAction(
                    updateAssistantMessage(current.messages, assistantId, (item) => ({
                      ...item,
                      status_label: payload.label ?? null,
                      status_phase: payload.phase ?? null,
                    })),
                    assistantId,
                    buildStatusAction(payload)
                  )
                : updateAssistantMessage(current.messages, assistantId, (item) => ({
                    ...item,
                    status_label: payload.label ?? null,
                    status_phase: payload.phase ?? null,
                  })),
            }));
            return;
          }

          if (event === 'message_chunk' && payload.text) {
            flushSync(() => {
              setData((current) => ({
                ...current,
                messages: updateAssistantMessage(current.messages, assistantId, (item) => ({
                  ...item,
                  content: payload.replace ? payload.text ?? '' : `${item.content}${payload.text}`,
                  status_label: item.status_label ?? '正在生成回复',
                  status_phase: item.status_phase ?? 'agent_streaming',
                })),
              }));
            });
            return;
          }

          if (event === 'citations' && payload.items) {
            setData((current) => ({
              ...current,
              messages: updateAssistantMessage(current.messages, assistantId, (item) => ({
                ...item,
                source_refs: payload.items as MessageRecord['source_refs'],
              })),
            }));
            return;
          }

          if (event === 'current_understanding_patch' && payload.items) {
            markRecentInsights(payload.items as StateItem[]);
            setData((current) => ({
              ...current,
              messages: appendAssistantAction(
                current.messages,
                assistantId,
                buildPatchAction('state', '已写入当前理解', payload)
              ),
              state: {
                ...(current.state ?? emptyState()),
                current_understanding: upsertItems(
                  current.state?.current_understanding ?? [],
                  payload.items as StateItem[]
                ),
              },
            }));
            return;
          }

          if (event === 'pending_items_patch' && payload.items) {
            markRecentInsights(payload.items as StateItem[]);
            setData((current) => ({
              ...current,
              messages: appendAssistantAction(
                current.messages,
                assistantId,
                buildPatchAction('state', '已写入待确认项', payload)
              ),
              state: {
                ...(current.state ?? emptyState()),
                pending_items: upsertItems(
                  current.state?.pending_items ?? [],
                  payload.items as StateItem[]
                ),
              },
            }));
            return;
          }

          if (event === 'confirmed_items_patch' && payload.items) {
            markRecentInsights(payload.items as StateItem[]);
            setData((current) => ({
              ...current,
              messages: appendAssistantAction(
                current.messages,
                assistantId,
                buildPatchAction('state', '已写入已确认项', payload)
              ),
              state: {
                ...(current.state ?? emptyState()),
                confirmed_items: upsertItems(
                  current.state?.confirmed_items ?? [],
                  payload.items as StateItem[]
                ),
              },
            }));
            return;
          }

          if (event === 'conflict_items_patch' && payload.items) {
            markRecentInsights(payload.items as StateItem[]);
            setData((current) => ({
              ...current,
              messages: appendAssistantAction(
                current.messages,
                assistantId,
                buildPatchAction('state', '已写入冲突项', payload)
              ),
              state: {
                ...(current.state ?? emptyState()),
                conflict_items: upsertItems(
                  current.state?.conflict_items ?? [],
                  payload.items as StateItem[]
                ),
              },
            }));
            return;
          }

          if (event === 'mvp_items_patch' && payload.items) {
            markRecentInsights(payload.items as StateItem[]);
            setData((current) => ({
              ...current,
              messages: appendAssistantAction(
                current.messages,
                assistantId,
                buildPatchAction('state', '已写入 MVP 方向', payload)
              ),
              state: {
                ...(current.state ?? emptyState()),
                mvp_items: upsertItems(
                  current.state?.mvp_items ?? [],
                  payload.items as StateItem[]
                ),
              },
            }));
            return;
          }

          if (event === 'version_patch' && payload.items) {
            setData((current) => ({
              ...current,
              messages: appendAssistantAction(
                current.messages,
                assistantId,
                buildPatchAction('version', '已生成版本快照', payload)
              ),
              state: {
                ...(current.state ?? emptyState()),
                versions: upsertItems(
                  current.state?.versions ?? [],
                  payload.items as StateItem[]
                ),
              },
            }));
            return;
          }

          if (event === 'artifact_patch' && payload.items) {
            setData((current) => ({
              ...current,
              messages: appendAssistantAction(
                current.messages,
                assistantId,
                buildArtifactAction(payload.items as ArtifactRecord[], payload.created_at)
              ),
              artifacts: upsertArtifacts(current.artifacts, payload.items as ArtifactRecord[]),
            }));
            return;
          }

          if (event === 'error') {
            setNotices((current) => [
              {
                id: `notice-${Date.now()}`,
                kind: 'error',
                title: payload.provider ?? '分析失败',
                body: payload.message ?? '聊天流返回错误。',
              },
              ...current,
            ]);
            setData((current) => ({
              ...current,
              messages: updateAssistantMessage(current.messages, assistantId, (item) => ({
                ...item,
                status_label: null,
                status_phase: null,
              })),
            }));
            return;
          }

          if (event === 'done') {
            setData((current) => ({
              ...current,
              messages: updateAssistantMessage(current.messages, assistantId, (item) => ({
                ...item,
                status_label: null,
                status_phase: null,
              })),
            }));
          }
        }
      );
    } catch (error) {
      const messageText = error instanceof Error ? error.message : '聊天请求失败。';
      setNotices((current) => [
        {
          id: `chat-${Date.now()}`,
          kind: 'error',
          title: '聊天请求失败',
          body: messageText,
        },
        ...current,
      ]);
      setData((current) => ({
        ...current,
        messages: updateAssistantMessage(current.messages, assistantId, (item) => ({
          ...item,
          status_label: null,
          status_phase: null,
        })),
      }));
    } finally {
      setSending(false);
    }
  }

  async function handleUploadTextSource(payload: { name: string; text: string }) {
    setUploading(true);
    try {
      await uploadTextSource(projectId, payload);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '文本资料导入失败。';
      setNotices((current) => [
        {
          id: `upload-${Date.now()}`,
          kind: 'error',
          title: '导入资料失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      setUploading(false);
    }
  }

  async function handleUploadFileSource(files: File[]) {
    setUploading(true);
    try {
      await uploadFileSources(projectId, files);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '文件上传失败。';
      setNotices((current) => [
        {
          id: `file-${Date.now()}`,
          kind: 'error',
          title: '上传文件失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteSource(sourceId: string) {
    setDeletingSourceId(sourceId);
    try {
      await deleteProjectSource(projectId, sourceId);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '资料删除失败。';
      setNotices((current) => [
        {
          id: `delete-${Date.now()}`,
          kind: 'error',
          title: '删除资料失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      setDeletingSourceId(null);
    }
  }

  async function handleRetrySourceSync(sourceId: string) {
    setRetryingSourceId(sourceId);
    try {
      await retryProjectSourceSync(projectId, sourceId);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '资料重试同步失败。';
      setNotices((current) => [
        {
          id: `retry-source-${Date.now()}`,
          kind: 'error',
          title: '重试同步失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      setRetryingSourceId(null);
    }
  }

  async function handleBindProjectNotebook(payload: { sourceUrl?: string; notebookId?: string }) {
    setBindingNotebook(true);
    try {
      await bindProjectNotebook(projectId, {
        source_url: payload.sourceUrl,
        notebook_id: payload.notebookId,
      });
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '绑定项目 notebook 失败。';
      setNotices((current) => [
        {
          id: `binding-${Date.now()}`,
          kind: 'error',
          title: '绑定项目 notebook 失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      setBindingNotebook(false);
    }
  }

  async function handleCreateAndBindProjectNotebook() {
    setBindingNotebook(true);
    try {
      await createAndBindProjectNotebook(projectId);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建并绑定项目 Notebook 失败。';
      setNotices((current) => [
        {
          id: `bind-create-${Date.now()}`,
          kind: 'error',
          title: '创建并绑定项目 Notebook 失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      setBindingNotebook(false);
    }
  }

  const cleanedNotices = useMemo(() => notices.slice(0, 4), [notices]);

  if (loading || !data.project || !data.state) {
    return (
      <main className="min-h-screen p-8 text-ink">
        <div className="mx-auto max-w-4xl rounded-[28px] border border-line bg-white p-8 shadow-panel">
          <div className="text-xs uppercase tracking-[0.18em] text-muted">Loading</div>
          <h1 className="mt-3 text-3xl font-semibold">正在加载工作台</h1>
          <p className="mt-3 text-sm leading-7 text-muted">项目、资料、聊天与沉淀总集正在初始化。</p>
        </div>
      </main>
    );
  }

  return (
    <WorkbenchPage
      project={data.project}
      readiness={readiness}
      sources={data.sources}
      messages={data.messages}
      state={data.state}
      artifacts={data.artifacts}
      recentInsightIds={recentInsightIds}
      notebookLibrary={data.notebookLibrary}
      notices={cleanedNotices}
      sending={sending}
      uploading={uploading}
      deletingSourceId={deletingSourceId}
      retryingSourceId={retryingSourceId}
      bindingNotebook={bindingNotebook}
      onSendMessage={handleSendMessage}
        onUploadTextSource={handleUploadTextSource}
        onUploadFileSource={handleUploadFileSource}
        onDeleteSource={handleDeleteSource}
        onRetrySourceSync={handleRetrySourceSync}
        onBindProjectNotebook={handleBindProjectNotebook}
        onCreateAndBindProjectNotebook={handleCreateAndBindProjectNotebook}
      />
  );
}

export default function App() {
  return (
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/projects/:projectId/workbench" element={<WorkbenchRoute />} />
        <Route path="/project/:projectId/workbench" element={<Navigate to="/projects/seed-reconciliation/workbench" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
