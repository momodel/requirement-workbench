import { useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom';

import { ProjectsPage } from './features/projects/ProjectsPage';
import { WorkbenchPage } from './features/workbench/WorkbenchPage';
import {
  createProject,
  deleteProjectSource,
  generateArtifact,
  getGlobalReadiness,
  getProject,
  getProjectKnowledgeBase,
  getProjectReadiness,
  getProjectState,
  initializeProjectKnowledgeBase,
  listArtifacts,
  listMessages,
  listProjects,
  listSources,
  reindexProjectSource,
  streamChat,
  uploadFileSources,
  uploadTextSource,
  uploadUrlSource,
} from './lib/api';
import type {
  ArtifactRecord,
  GlobalReadiness,
  MessageRecord,
  ProjectKnowledgeBase,
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
  knowledgeBase: ProjectKnowledgeBase | null;
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

function prependNotice(current: Notice[], notice: Omit<Notice, 'id'>) {
  return [
    {
      id: `${notice.kind}-${Date.now()}`,
      ...notice,
    },
    ...current,
  ];
}

function applyStatePatch(state: ProjectState | null, key: keyof ProjectState, items: StateItem[]) {
  return {
    ...(state ?? emptyState()),
    [key]: items,
  };
}

function resolvePatchedStateKey(event: string): keyof ProjectState | null {
  const eventToStateKey: Record<string, keyof ProjectState> = {
    current_understanding_patch: 'current_understanding',
    pending_patch: 'pending_items',
    pending_items_patch: 'pending_items',
    confirmed_patch: 'confirmed_items',
    confirmed_items_patch: 'confirmed_items',
    conflict_patch: 'conflict_items',
    conflict_items_patch: 'conflict_items',
    mvp_patch: 'mvp_items',
    mvp_items_patch: 'mvp_items',
  };

  return eventToStateKey[event] ?? null;
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
      if (readiness?.evidence?.status === 'ready') {
        await initializeProjectKnowledgeBase(project.id).catch(() => undefined);
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
    knowledgeBase: null,
  });
  const [loading, setLoading] = useState(true);
  const [readiness, setReadiness] = useState<ProjectReadiness | null>(null);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [initializingKnowledgeBase, setInitializingKnowledgeBase] = useState(false);
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [retryingSourceId, setRetryingSourceId] = useState<string | null>(null);
  const [generatingArtifactType, setGeneratingArtifactType] = useState<string | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [recentInsightIds, setRecentInsightIds] = useState<string[]>([]);
  const autoInitAttemptedProjectId = useRef<string | null>(null);
  const recentInsightTimerRef = useRef<number | null>(null);
  const evidenceStatus = readiness?.evidence?.status ?? null;

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
        getProjectKnowledgeBase(projectId),
        getProjectReadiness(projectId),
      ]).then(([knowledgeBaseResult, readinessResult]) => {
        if (knowledgeBaseResult.status === 'fulfilled') {
          setData((current) => ({
            ...current,
            knowledgeBase: knowledgeBaseResult.value,
          }));
        } else {
          const message =
            knowledgeBaseResult.reason instanceof Error
              ? knowledgeBaseResult.reason.message
              : '知识库状态加载失败。';
          setNotices((current) =>
            prependNotice(current, {
              kind: 'info',
              title: '知识库状态加载较慢',
              body: message,
            })
          );
        }

        if (readinessResult.status === 'fulfilled') {
          setReadiness(readinessResult.value);
        } else {
          const message =
            readinessResult.reason instanceof Error
              ? readinessResult.reason.message
              : 'Provider 状态加载失败。';
          setNotices((current) =>
            prependNotice(current, {
              kind: 'info',
              title: '运行状态加载较慢',
              body: message,
            })
          );
        }
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : '加载工作台失败。';
      setNotices((current) =>
        prependNotice(current, {
          kind: 'error',
          title: '工作台加载失败',
          body: message,
        })
      );
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    autoInitAttemptedProjectId.current = null;
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
    if (!data.project || initializingKnowledgeBase || evidenceStatus !== 'knowledge_base_missing') {
      return;
    }
    if (autoInitAttemptedProjectId.current === projectId) {
      return;
    }

    autoInitAttemptedProjectId.current = projectId;
    void ensureProjectKnowledgeBase();
  }, [data.project, initializingKnowledgeBase, projectId, evidenceStatus]);

  async function ensureProjectKnowledgeBase() {
    if (initializingKnowledgeBase || evidenceStatus !== 'knowledge_base_missing') {
      return true;
    }

    setInitializingKnowledgeBase(true);
    try {
      await initializeProjectKnowledgeBase(projectId);
      await loadWorkbench({ silent: true });
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : '自动初始化项目知识库失败。';
      setNotices((current) =>
        prependNotice(current, {
          kind: 'error',
          title: '项目知识库自动初始化失败',
          body: message,
        })
      );
      return false;
    } finally {
      setInitializingKnowledgeBase(false);
    }
  }

  async function handleSendMessage(message: string) {
    if (evidenceStatus === 'knowledge_base_missing') {
      const ready = await ensureProjectKnowledgeBase();
      if (!ready) {
        return;
      }
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
            setData((current) => ({
              ...current,
              messages: updateAssistantMessage(current.messages, assistantId, (item) => ({
                ...item,
                status_label: payload.label ?? null,
                status_phase: payload.phase ?? null,
              })),
            }));
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

          if (event === 'message_chunk' && payload.text) {
            flushSync(() => {
              setData((current) => ({
                ...current,
                messages: updateAssistantMessage(current.messages, assistantId, (item) => ({
                  ...item,
                  content: payload.replace ? payload.text ?? '' : `${item.content}${payload.text}`,
                  status_label: item.status_label ?? '正在生成回复',
                  status_phase: item.status_phase ?? 'drafting',
                })),
              }));
            });
            return;
          }

          const stateKey = resolvePatchedStateKey(event);
          if (stateKey && payload.items) {
            markRecentInsights(payload.items as StateItem[]);
            setData((current) => ({
              ...current,
              state: applyStatePatch(current.state, stateKey, payload.items as StateItem[]),
            }));
            return;
          }

          if (event === 'version_patch' && payload.items) {
            setData((current) => ({
              ...current,
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
              artifacts: upsertArtifacts(current.artifacts, payload.items as ArtifactRecord[]),
            }));
            return;
          }

          if (event === 'error') {
            setNotices((current) =>
              prependNotice(current, {
                kind: 'error',
                title: payload.provider ?? '分析失败',
                body: payload.message ?? '聊天流返回错误。',
              })
            );
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
      await loadWorkbench({ silent: true });
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

  async function handleUploadUrlSource(payload: { name: string; sourceUrl: string }) {
    setUploading(true);
    try {
      await uploadUrlSource(projectId, payload);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '网页链接导入失败。';
      setNotices((current) => [
        {
          id: `url-${Date.now()}`,
          kind: 'error',
          title: '导入网页链接失败',
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

  async function handleRetrySourceIndex(sourceId: string) {
    setRetryingSourceId(sourceId);
    try {
      await reindexProjectSource(projectId, sourceId);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '资料重建索引失败。';
      setNotices((current) =>
        prependNotice(current, {
          kind: 'error',
          title: '重建索引失败',
          body: message,
        })
      );
    } finally {
      setRetryingSourceId(null);
    }
  }

  async function handleGenerateArtifact(artifactType: 'document' | 'page_solution' | 'interaction_flow') {
    setGeneratingArtifactType(artifactType);
    try {
      await generateArtifact(projectId, artifactType);
      await loadWorkbench({ silent: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : '交付物生成失败。';
      setNotices((current) => [
        {
          id: `artifact-${Date.now()}`,
          kind: 'error',
          title: '交付物生成失败',
          body: message,
        },
        ...current,
      ]);
    } finally {
      setGeneratingArtifactType(null);
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
      knowledgeBase={data.knowledgeBase}
      recentInsightIds={recentInsightIds}
      notices={cleanedNotices}
      sending={sending}
      uploading={uploading}
      deletingSourceId={deletingSourceId}
      retryingSourceId={retryingSourceId}
      initializingKnowledgeBase={initializingKnowledgeBase}
      generatingArtifactType={generatingArtifactType}
      onSendMessage={handleSendMessage}
      onUploadTextSource={handleUploadTextSource}
      onUploadUrlSource={handleUploadUrlSource}
      onUploadFileSource={handleUploadFileSource}
      onDeleteSource={handleDeleteSource}
      onRetrySourceIndex={handleRetrySourceIndex}
      onInitializeKnowledgeBase={ensureProjectKnowledgeBase}
      onGenerateArtifact={handleGenerateArtifact}
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
