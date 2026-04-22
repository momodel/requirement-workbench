import {
  AlertCircle,
  ArrowUpRight,
  Bot,
  FileText,
  FolderKanban,
  Loader2,
  MonitorCog,
  PanelRight,
  RotateCw,
  Send,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react';
import { createPortal } from 'react-dom';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link } from 'react-router-dom';

import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { cn } from '../../lib/utils';
import type {
  ArtifactRecord,
  MessageRecord,
  NotebookLibraryItem,
  ProjectReadiness,
  ProjectState,
  ProjectSummary,
  SourceRecord,
  StateItem,
} from '../../lib/types';

type WorkbenchPageProps = {
  project: ProjectSummary;
  readiness: ProjectReadiness | null;
  sources: SourceRecord[];
  messages: MessageRecord[];
  state: ProjectState;
  artifacts: ArtifactRecord[];
  recentInsightIds: string[];
  notebookLibrary: NotebookLibraryItem[];
  notices: Array<{ id: string; kind: 'error' | 'info'; title: string; body: string }>;
  sending: boolean;
  uploading: boolean;
  deletingSourceId: string | null;
  retryingSourceId: string | null;
  bindingNotebook: boolean;
  generatingArtifactType: string | null;
  onSendMessage: (message: string) => Promise<void>;
  onUploadTextSource: (payload: { name: string; text: string }) => Promise<void>;
  onUploadFileSource: (files: File[]) => Promise<void>;
  onDeleteSource: (sourceId: string) => Promise<void>;
  onRetrySourceSync: (sourceId: string) => Promise<void>;
  onBindProjectNotebook: (payload: { sourceUrl?: string; notebookId?: string }) => Promise<void>;
  onCreateAndBindProjectNotebook: () => Promise<void>;
  onGenerateArtifact: (artifactType: 'document' | 'page_solution' | 'interaction_flow') => Promise<void>;
};

const STAGES = [
  '需求接入',
  '业务理解',
  '需求收敛',
  '方案定义',
  '设计交付',
];

const STATE_SECTIONS: Array<{
  key: keyof ProjectState;
  label: string;
}> = [
  { key: 'current_understanding', label: '当前理解' },
  { key: 'pending_items', label: '待确认项' },
  { key: 'confirmed_items', label: '已确认项' },
  { key: 'conflict_items', label: '冲突项' },
  { key: 'mvp_items', label: 'MVP' },
  { key: 'versions', label: '版本快照' },
];

function relativeTime(value: string) {
  return new Date(value).toLocaleString('zh-CN');
}

function statusVariant(status: string) {
  if (status.includes('failed') || status.includes('error') || status.includes('not_configured')) {
    return 'danger' as const;
  }
  if (
    status.includes('parsed') ||
    status.includes('generated') ||
    status.includes('seed_ready') ||
    status.includes('synced') ||
    status.includes('ready') ||
    status.includes('bound')
  ) {
    return 'success' as const;
  }
  if (status.includes('pending') || status.includes('queued') || status.includes('missing') || status.includes('required')) {
    return 'warning' as const;
  }
  return 'default' as const;
}

function readinessVariant(status: string) {
  if (status === 'ready') return 'success' as const;
  if (status.includes('failed') || status.includes('error')) {
    return 'danger' as const;
  }
  if (
    status.includes('required') ||
    status.includes('config') ||
    status.includes('binding') ||
    status.includes('missing') ||
    status.includes('auth')
  ) {
    return 'warning' as const;
  }
  return 'default' as const;
}

function readinessStatusLabel(status: string) {
  if (status === 'ready') return '已就绪';
  if (status === 'knowledge_base_missing') return '待初始化';
  if (status === 'auth_required') return '待认证';
  if (status === 'binding_required') return '待绑定';
  if (status === 'not_configured') return '未配置';
  if (status.includes('failed') || status.includes('error')) return '异常';
  return status;
}

function parseStatusLabel(status: string) {
  if (status === 'parsed') return '已解析';
  if (status === 'pending') return '解析中';
  if (status === 'queued') return '排队中';
  if (status === 'error') return '解析异常';
  return status;
}

function syncStatusLabel(status: string) {
  if (status === 'synced') return '已入库';
  if (status === 'pending_sync') return '待入库';
  if (status === 'sync_failed') return '入库失败';
  if (status === 'error') return '入库异常';
  if (status === 'binding_required') return '知识库未就绪';
  if (status === 'not_configured') return '未配置';
  return status;
}

function sanitizeStateBody(title: string, body: string) {
  if (!body) return '';

  const fragments = body
    .split(/[；;]+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .filter((part) => !/^(content|impact|source|reason|notes|evidence|confidence|resolution|answer_needed)\s*:/i.test(part));

  const deduped = Array.from(new Set(fragments)).map((part) => {
    const normalizedTitle = title.trim();
    const titlePrefix = `${normalizedTitle}：`;
    const titlePrefixAlt = `${normalizedTitle}:`;
    if (part.startsWith(titlePrefix)) {
      return part.slice(titlePrefix.length).trim();
    }
    if (part.startsWith(titlePrefixAlt)) {
      return part.slice(titlePrefixAlt.length).trim();
    }
    return part;
  });

  return deduped.join('；') || body;
}

function getLatestArtifactsByType(artifacts: ArtifactRecord[]) {
  const latest = new Map<string, ArtifactRecord>();
  for (const artifact of artifacts) {
    if (!latest.has(artifact.artifact_type)) {
      latest.set(artifact.artifact_type, artifact);
    }
  }
  return Array.from(latest.values());
}

function SourcePreview({
  source,
  position,
  onClose,
}: {
  source: SourceRecord;
  position: { top: number; left: number };
  onClose: () => void;
}) {
  return createPortal(
    <div
      className="fixed z-50 w-[360px] rounded-[24px] border border-line bg-white p-5 shadow-panel"
      style={{ top: position.top, left: position.left }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted">File Preview</div>
          <h3 className="mt-2 text-lg font-semibold text-ink">{source.name}</h3>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          关闭
        </Button>
      </div>
      <div className="mt-4 space-y-3 text-sm text-muted">
        <div className="flex flex-wrap gap-2">
          <Badge>{source.source_kind}</Badge>
          <Badge variant={statusVariant(source.parse_status)}>{`解析：${parseStatusLabel(source.parse_status)}`}</Badge>
          <Badge variant={statusVariant(source.sync_status)}>{`入库：${syncStatusLabel(source.sync_status)}`}</Badge>
        </div>
        <p className="text-xs text-muted">{`导入时间：${relativeTime(source.created_at)}`}</p>
        <p>{source.parse_summary ?? '当前还没有解析摘要。'}</p>
        {source.sync_error ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-amber-800">
            {source.sync_error}
          </div>
        ) : null}
      </div>
    </div>,
    document.body
  );
}

function StateBlock({
  label,
  items,
  recentInsightIds,
}: {
  label: string;
  items: StateItem[];
  recentInsightIds: string[];
}) {
  return (
    <div className="rounded-[20px] border border-line bg-slate-50/80 p-3.5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink">{label}</h3>
        <Badge>{items.length}</Badge>
      </div>
      <div className="mt-2.5 grid gap-2.5">
        {items.length === 0 ? (
          <div className="rounded-[16px] border border-dashed border-line bg-white/80 p-3 text-sm text-muted">
            当前还没有内容。
          </div>
        ) : (
          items.slice(0, 4).map((item) => (
            <div
              key={item.id}
              className={cn(
                'rounded-[16px] border border-white bg-white p-3 transition-colors',
                recentInsightIds.includes(item.id) && 'border-accent/30 bg-accentSoft/40'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium text-ink">{item.title}</div>
                {recentInsightIds.includes(item.id) ? <Badge variant="accent">本轮新增</Badge> : null}
              </div>
              <p className="mt-1.5 text-sm leading-6 text-muted">{sanitizeStateBody(item.title, item.body)}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted">
                {item.status ? <span>{`状态：${item.status}`}</span> : null}
                {item.updated_at ? <span>{`更新于 ${relativeTime(item.updated_at)}`}</span> : null}
                <span>{`来源 ${item.source_ids.length} 份资料`}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function MessageMarkdown({ content }: { content: string }) {
  return (
    <div className="markdown-body text-sm leading-6 text-inherit">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          pre: ({ children }) => (
            <pre className="mb-3 overflow-x-auto rounded-2xl bg-slate-950/95 p-3 font-mono text-[0.92em] text-slate-100 last:mb-0">
              {children}
            </pre>
          ),
          code: ({ children }) => (
            <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.92em] text-ink">
              {children}
            </code>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-sky-700 underline decoration-sky-300 underline-offset-2"
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function WorkbenchPage({
  project,
  readiness,
  sources,
  messages,
  state,
  artifacts,
  recentInsightIds,
  notebookLibrary,
  notices,
  sending,
  uploading,
  deletingSourceId,
  retryingSourceId,
  bindingNotebook,
  generatingArtifactType,
  onSendMessage,
  onUploadTextSource,
  onUploadFileSource,
  onDeleteSource,
  onRetrySourceSync,
  onBindProjectNotebook,
  onCreateAndBindProjectNotebook,
  onGenerateArtifact,
}: WorkbenchPageProps) {
  const [composer, setComposer] = useState('');
  const [isImportDialogOpen, setIsImportDialogOpen] = useState(false);
  const [isBindingDialogOpen, setIsBindingDialogOpen] = useState(false);
  const [isRuntimeDialogOpen, setIsRuntimeDialogOpen] = useState(false);
  const [sourceName, setSourceName] = useState('访谈纪要');
  const [sourceText, setSourceText] = useState('');
  const [knowledgeBaseUrl, setKnowledgeBaseUrl] = useState('');
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState('');
  const [selectedSource, setSelectedSource] = useState<SourceRecord | null>(null);
  const [sourcePreviewPosition, setSourcePreviewPosition] = useState({ top: 120, left: 120 });
  const [activeArtifact, setActiveArtifact] = useState<ArtifactRecord | null>(null);
  const [activeDocument, setActiveDocument] = useState<ArtifactRecord | null>(null);
  const sourceInputRef = useRef<HTMLInputElement | null>(null);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);
  const lastMessageContent = messages[messages.length - 1]?.content ?? '';

  const latestVersions = state.versions.slice(0, 3);
  const stageIndex = useMemo(() => {
    if (state.artifacts.length > 0) return 4;
    if (state.mvp_items.length > 0) return 3;
    if (state.confirmed_items.length > 0 || state.conflict_items.length > 0) return 2;
    if (state.current_understanding.length > 0) return 1;
    return 0;
  }, [state]);

  const latestArtifacts = useMemo(() => getLatestArtifactsByType(artifacts), [artifacts]);
  const evidenceReadiness = readiness?.evidence ?? readiness?.notebooklm;
  const knowledgeBase = readiness?.knowledge_base ?? null;
  const artifactHistoryCount = Math.max(artifacts.length - latestArtifacts.length, 0);
  const referencedSourceCount = sources.filter(
    (source) => source.sync_status.includes('synced') || source.sync_status.includes('bound')
  ).length;
  const pendingSourceCount = sources.filter(
    (source) =>
      source.parse_status.includes('pending') ||
      source.sync_status.includes('pending') ||
      source.sync_status.includes('queued')
  ).length;
  const totalInsightCount =
    state.current_understanding.length +
    state.pending_items.length +
    state.confirmed_items.length +
    state.conflict_items.length +
    state.mvp_items.length;

  useEffect(() => {
    const chatBottom = chatBottomRef.current;
    if (chatBottom && typeof chatBottom.scrollIntoView === 'function') {
      chatBottom.scrollIntoView({ block: 'end' });
    }
  }, [lastMessageContent, messages.length, notices.length, sending]);

  async function handleSend() {
    const trimmed = composer.trim();
    if (!trimmed) return;
    setComposer('');
    await onSendMessage(trimmed);
  }

  async function handleUploadText() {
    const name = sourceName.trim();
    const text = sourceText.trim();
    if (!name || !text) return;
    await onUploadTextSource({ name, text });
    setSourceText('');
    setSourceName('访谈纪要');
    setIsImportDialogOpen(false);
  }

  async function handleBindKnowledgeBaseUrl() {
    const sourceUrl = knowledgeBaseUrl.trim();
    if (!sourceUrl) return;
    await onBindProjectNotebook({ sourceUrl });
    setKnowledgeBaseUrl('');
    setIsBindingDialogOpen(false);
  }

  async function handleBindRegisteredKnowledgeBase() {
    if (!selectedKnowledgeBaseId) return;
    await onBindProjectNotebook({ notebookId: selectedKnowledgeBaseId });
    setSelectedKnowledgeBaseId('');
    setIsBindingDialogOpen(false);
  }

  async function handleCreateAndBindKnowledgeBase() {
    await onCreateAndBindProjectNotebook();
    setSelectedKnowledgeBaseId('');
    setKnowledgeBaseUrl('');
    setIsBindingDialogOpen(false);
  }

  function handleComposerKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }

    event.preventDefault();
    if (!sending && composer.trim()) {
      void handleSend();
    }
  }

  return (
    <main className="h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(23,71,111,0.12),_transparent_26%),linear-gradient(180deg,_#eef4f9_0%,_#f8fafc_50%,_#eef2f7_100%)] px-3 pb-3 pt-3 text-ink md:px-4">
      <div className="mx-auto flex h-full max-w-[1700px] flex-col gap-3">
        <Card className="shrink-0 border-white/70 bg-white/90">
          <CardContent className="flex items-center justify-between gap-4 p-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <Sparkles className="h-4 w-4 shrink-0 text-muted" />
              <h1 className="truncate text-[1.65rem] font-semibold tracking-tight">{project.name}</h1>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Badge variant="accent">{project.status}</Badge>
              <Badge>{project.scenario_type}</Badge>
              {readiness ? (
                <>
                  <Badge variant={readinessVariant(readiness.claude.status)}>
                    {`Claude: ${readinessStatusLabel(readiness.claude.status)}`}
                  </Badge>
                  {evidenceReadiness ? (
                    <Badge variant={readinessVariant(evidenceReadiness.status)}>
                      {`Evidence: ${readinessStatusLabel(evidenceReadiness.status)}`}
                    </Badge>
                  ) : null}
                </>
              ) : null}
              <Button variant="ghost" size="sm" asChild>
                <Link to="/">
                  <FolderKanban className="mr-1.5 h-4 w-4" />
                  项目列表
                </Link>
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setIsRuntimeDialogOpen(true)}>
                <MonitorCog className="mr-1.5 h-4 w-4" />
                运行状态
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="grid shrink-0 grid-cols-5 gap-2 rounded-[20px] border border-white/70 bg-white/85 p-1.5 shadow-panel">
          {STAGES.map((stage, index) => (
            <div
              key={stage}
              className={cn(
                'rounded-[16px] border border-transparent px-3 py-2 text-sm transition-colors',
                index < stageIndex && 'bg-emerald-50 text-emerald-900',
                index === stageIndex && 'border-accent/15 bg-accentSoft text-accent',
                index > stageIndex && 'bg-slate-50 text-muted'
              )}
            >
              <div className="text-[10px] uppercase tracking-[0.18em]">{`Stage ${index + 1}`}</div>
              <div className="mt-0.5 font-medium">{stage}</div>
            </div>
          ))}
        </div>

        <section className="grid min-h-0 flex-1 grid-cols-[292px_minmax(0,1fr)_332px] gap-3">
          <Card className="relative flex min-h-0 flex-col overflow-hidden border-white/80 bg-white/92">
            <CardHeader className="shrink-0 p-3 pb-2.5">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-base">项目知识库</CardTitle>
                <div className="text-xs text-muted">{`${sources.length} 份 · ${referencedSourceCount} 已入库 · ${pendingSourceCount} 待处理`}</div>
              </div>
            </CardHeader>
            <CardContent
              data-testid="sources-panel-content"
              className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-hidden px-3 pb-3 pt-0"
            >
              <div className="flex flex-wrap gap-2 rounded-[18px] border border-line bg-slate-50/80 p-2.5">
                <Button variant="subtle" size="sm" onClick={() => setIsImportDialogOpen(true)} disabled={uploading}>
                  {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                  导入文本资料
                </Button>
                <Button variant="secondary" size="sm" onClick={() => sourceInputRef.current?.click()} disabled={uploading}>
                  上传文件
                </Button>
                <input
                  ref={sourceInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={async (event) => {
                    const files = Array.from(event.target.files ?? []);
                    if (files.length > 0) {
                      await onUploadFileSource(files);
                      event.target.value = '';
                    }
                  }}
                />
              </div>

              <div data-testid="sources-scroll-area" className="min-h-0 flex-1 overflow-y-auto pr-1">
                <div className="grid gap-2.5">
                  {sources.map((source) => {
                    const canRetrySync =
                      source.sync_status === 'sync_failed' || source.sync_status === 'error';

                    return (
                      <div
                        key={source.id}
                        className="rounded-[18px] border border-line bg-white p-2 transition hover:border-accent/30 hover:bg-slate-50"
                      >
                        <div className="flex items-start gap-2">
                          <button
                            type="button"
                            className="min-w-0 flex-1 text-left"
                            onClick={(event) => {
                              const rect = event.currentTarget.getBoundingClientRect();
                              setSourcePreviewPosition({
                                top: Math.min(rect.top, window.innerHeight - 300),
                                left: Math.min(rect.right + 12, window.innerWidth - 380),
                              });
                              setSelectedSource(source);
                            }}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="truncate text-sm font-semibold text-ink">{source.name}</div>
                              <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                            </div>
                          </button>
                          <div className="flex shrink-0 items-center gap-0.5">
                            {canRetrySync ? (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                aria-label={`重试入库 ${source.name}`}
                                disabled={retryingSourceId === source.id}
                                onClick={async (event) => {
                                  event.stopPropagation();
                                  await onRetrySourceSync(source.id);
                                }}
                              >
                                {retryingSourceId === source.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <RotateCw className="h-4 w-4" />
                                )}
                              </Button>
                            ) : null}
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              aria-label={`删除 ${source.name}`}
                              disabled={deletingSourceId === source.id}
                              onClick={async (event) => {
                                event.stopPropagation();
                                await onDeleteSource(source.id);
                              }}
                            >
                              {deletingSourceId === source.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </Button>
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          <Badge>{source.source_kind}</Badge>
                          <Badge variant={statusVariant(source.parse_status)}>
                            {parseStatusLabel(source.parse_status)}
                          </Badge>
                          <Badge variant={statusVariant(source.sync_status)}>
                            {syncStatusLabel(source.sync_status)}
                          </Badge>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="flex min-h-0 flex-col overflow-hidden border-white/80 bg-white/92">
            <CardHeader className="shrink-0 border-b border-line/70 px-3 py-2.5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <CardTitle className="text-base">需求分析</CardTitle>
                  <div className="text-xs text-muted">{`${messages.length} 轮消息 · ${totalInsightCount} 条沉淀`}</div>
                </div>
                {sending ? (
                  <Badge variant="accent">
                    <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                    正在分析
                  </Badge>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto] gap-3 p-0">
              <div className="min-h-0 overflow-y-auto px-3 py-3">
                <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={cn(
                        'flex gap-3',
                        message.role === 'user' ? 'justify-end' : 'justify-start'
                      )}
                    >
                      <div
                        className={cn(
                          'max-w-[78%] rounded-[24px] px-4 py-3.5 shadow-sm',
                          message.role === 'user'
                            ? 'bg-accent text-white'
                            : message.role === 'assistant'
                              ? 'border border-line bg-slate-50 text-ink'
                              : 'border border-amber-200 bg-amber-50 text-amber-900'
                        )}
                      >
                        <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.16em] opacity-80">
                          {message.role === 'assistant' ? <Bot className="h-3.5 w-3.5" /> : null}
                          {message.role}
                        </div>
                        {message.role === 'assistant' && message.status_label ? (
                          <div className="mb-2.5 flex items-center gap-2 rounded-[14px] border border-line/80 bg-white/70 px-3 py-2 text-xs font-medium text-muted">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            <span>{message.status_label}</span>
                          </div>
                        ) : null}
                        <MessageMarkdown content={message.content} />
                        {message.source_refs.length > 0 ? (
                          <div className="mt-2.5 flex flex-wrap gap-2">
                            {message.source_refs.map((reference, index) => (
                              <Badge key={`${message.id}-${index}`} variant="accent">
                                {reference.title ?? '引用'}
                              </Badge>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}

                  {notices.map((notice) => (
                    <div
                      key={notice.id}
                      className="rounded-[20px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
                    >
                      <div className="flex items-center gap-2 font-medium">
                        <AlertCircle className="h-4 w-4" />
                        {notice.title}
                      </div>
                      <p className="mt-2 whitespace-pre-wrap leading-6">{notice.body}</p>
                    </div>
                  ))}
                  <div ref={chatBottomRef} />
                </div>
              </div>

              <div className="border-t border-line/70 px-3 py-2.5">
                <div className="mx-auto flex w-full max-w-4xl flex-col gap-3">
                  <Textarea
                    id="chat-composer"
                    name="chat-composer"
                    value={composer}
                    onChange={(event) => setComposer(event.target.value)}
                    onKeyDown={handleComposerKeyDown}
                    placeholder="继续补充背景、确认范围，或让系统基于当前资料生成理解。"
                    className="min-h-[92px]"
                  />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap gap-2">
                      <Button variant="secondary" onClick={() => setComposer('请基于当前资料生成你对真实需求的理解，并列出待确认项。')}>
                        基于当前资料生成理解
                      </Button>
                      <Button variant="secondary" onClick={() => setComposer('请把本轮结论写入沉淀，并判断是否已经可以形成 MVP 方向。')}>
                        把本轮结论写入沉淀
                      </Button>
                    </div>
                    <Button onClick={handleSend} disabled={sending || !composer.trim()}>
                      {sending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                      继续分析
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="flex min-h-0 flex-col overflow-hidden border-white/80 bg-white/92">
            <CardHeader className="shrink-0 p-3 pb-2.5">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <PanelRight className="h-4 w-4 text-muted" />
                  <CardTitle className="text-base">沉淀总集</CardTitle>
                </div>
                <div className="text-xs text-muted">
                  {`${state.current_understanding.length} 当前理解 · ${state.pending_items.length} 待确认 · ${artifacts.length} 交付物`}
                </div>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-y-auto space-y-3 px-3 pb-3 pt-0">
              {STATE_SECTIONS.map((section) => (
                <StateBlock
                  key={section.key}
                  label={section.label}
                  items={state[section.key]}
                  recentInsightIds={recentInsightIds}
                />
              ))}

              <div className="rounded-[20px] border border-line bg-slate-50/80 p-3.5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-ink">交付物</h3>
                  <Badge>{latestArtifacts.length}</Badge>
                </div>
                <div className="mt-2.5 grid gap-2.5">
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="subtle"
                      size="sm"
                      disabled={generatingArtifactType === 'document'}
                      onClick={() => onGenerateArtifact('document')}
                    >
                      {generatingArtifactType === 'document' ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <FileText className="mr-2 h-3.5 w-3.5" />}
                      生成文档稿
                    </Button>
                    <Button
                      variant="subtle"
                      size="sm"
                      disabled={generatingArtifactType === 'page_solution'}
                      onClick={() => onGenerateArtifact('page_solution')}
                    >
                      页面方案
                    </Button>
                    <Button
                      variant="subtle"
                      size="sm"
                      disabled={generatingArtifactType === 'interaction_flow'}
                      onClick={() => onGenerateArtifact('interaction_flow')}
                    >
                      交互稿
                    </Button>
                  </div>
                  {latestArtifacts.length === 0 ? (
                    <div className="rounded-[16px] border border-dashed border-line bg-white/80 p-3 text-sm text-muted">
                      当前还没有交付物。
                    </div>
                  ) : (
                    latestArtifacts.map((artifact) => (
                      <button
                        key={artifact.id}
                        type="button"
                        className="rounded-[16px] border border-white bg-white p-3 text-left transition hover:border-accent/25 hover:bg-slate-50"
                        onClick={() => {
                          if (artifact.content_format === 'html') {
                            setActiveArtifact(artifact);
                          } else {
                            setActiveDocument(artifact);
                          }
                        }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-ink">{artifact.title}</div>
                            <p className="mt-1.5 text-sm leading-6 text-muted">{artifact.summary}</p>
                          </div>
                          <Badge variant={statusVariant(artifact.status)}>{artifact.status}</Badge>
                        </div>
                        <div className="mt-2 text-xs text-muted">
                          {artifact.updated_at ? relativeTime(artifact.updated_at) : '刚刚更新'}
                        </div>
                      </button>
                    ))
                  )}
                  {artifactHistoryCount > 0 ? (
                    <div className="rounded-[16px] border border-dashed border-line bg-white/80 p-3 text-xs text-muted">
                      {`当前已折叠 ${artifactHistoryCount} 个历史版本，侧栏默认只显示每类最新交付物。`}
                    </div>
                  ) : null}
                </div>
              </div>

              {latestVersions.length > 0 ? (
                <div className="rounded-[20px] border border-line bg-white p-3.5">
                  <div className="text-sm font-semibold text-ink">最近版本</div>
                  <div className="mt-2.5 grid gap-2.5">
                    {latestVersions.map((version) => (
                      <div key={version.id} className="rounded-[16px] border border-line bg-slate-50 p-3">
                        <div className="text-sm font-medium text-ink">{version.title}</div>
                        <p className="mt-1.5 text-sm leading-6 text-muted">{version.body}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </section>
      </div>

      {selectedSource ? (
        <SourcePreview
          source={selectedSource}
          position={sourcePreviewPosition}
          onClose={() => setSelectedSource(null)}
        />
      ) : null}

      <Dialog open={Boolean(activeArtifact)} onOpenChange={(open) => !open && setActiveArtifact(null)}>
        {activeArtifact ? (
          <DialogContent className="w-[min(1320px,94vw)] max-w-none p-0">
            <div className="flex h-[82vh] flex-col">
              <DialogHeader className="border-b border-line px-6 py-5">
                <DialogTitle>{activeArtifact.title}</DialogTitle>
                <DialogDescription>{activeArtifact.summary}</DialogDescription>
              </DialogHeader>
              <div className="min-h-0 flex-1 bg-slate-100">
                {activeArtifact.preview_url ? (
                  <iframe
                    title={activeArtifact.title}
                    src={activeArtifact.preview_url}
                    className="h-full w-full border-0 bg-white"
                  />
                ) : null}
              </div>
            </div>
          </DialogContent>
        ) : null}
      </Dialog>

      <Dialog open={Boolean(activeDocument)} onOpenChange={(open) => !open && setActiveDocument(null)}>
        {activeDocument ? (
          <DialogContent className="left-auto right-4 top-4 h-[calc(100vh-2rem)] w-[520px] max-w-none translate-x-0 translate-y-0 p-0 data-[state=open]:animate-none">
            <div className="flex h-full flex-col">
              <DialogHeader className="border-b border-line px-6 py-5">
                <DialogTitle>{activeDocument.title}</DialogTitle>
                <DialogDescription>{activeDocument.summary}</DialogDescription>
              </DialogHeader>
              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-muted">
                  {activeDocument.body ?? '当前文档还没有正文。'}
                </pre>
              </div>
            </div>
          </DialogContent>
        ) : null}
      </Dialog>

      <Dialog open={isRuntimeDialogOpen} onOpenChange={setIsRuntimeDialogOpen}>
        <DialogContent className="w-[min(640px,92vw)]">
          <DialogHeader>
            <DialogTitle>运行状态</DialogTitle>
            <DialogDescription>这里放 Claude、证据运行时和项目知识库状态，不占用主分析区。</DialogDescription>
          </DialogHeader>
          {readiness ? (
            <div className="grid gap-4 py-2">
              <div className="rounded-[20px] border border-line bg-slate-50/80 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-ink">Claude Agent SDK</div>
                    <p className="mt-1 text-sm leading-6 text-muted">{readiness.claude.summary}</p>
                    {readiness.claude.detail ? (
                      <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">{readiness.claude.detail}</p>
                    ) : null}
                  </div>
                  <Badge variant={readinessVariant(readiness.claude.status)}>
                    {readinessStatusLabel(readiness.claude.status)}
                  </Badge>
                </div>
              </div>

              {evidenceReadiness ? (
                <div className="rounded-[20px] border border-line bg-slate-50/80 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-ink">Evidence Runtime</div>
                      <p className="mt-1 text-sm leading-6 text-muted">{evidenceReadiness.summary}</p>
                      {evidenceReadiness.detail ? (
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">
                          {evidenceReadiness.detail}
                        </p>
                      ) : null}
                    </div>
                    <Badge variant={readinessVariant(evidenceReadiness.status)}>
                      {readinessStatusLabel(evidenceReadiness.status)}
                    </Badge>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setIsRuntimeDialogOpen(false);
                        setIsBindingDialogOpen(true);
                      }}
                    >
                      项目知识库详情
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="py-2 text-sm leading-6 text-muted">当前还没有拿到 provider 状态，请先刷新。</div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={isImportDialogOpen} onOpenChange={setIsImportDialogOpen}>
        <DialogContent className="w-[min(640px,92vw)]">
          <DialogHeader>
            <DialogTitle>导入文本资料</DialogTitle>
            <DialogDescription>把访谈纪要、需求原话或规则说明作为文本资料导入当前项目。</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <Input
              id="source-name"
              name="source-name"
              value={sourceName}
              onChange={(event) => setSourceName(event.target.value)}
              placeholder="例如：客户访谈纪要"
            />
            <Textarea
              id="source-text"
              name="source-text"
              value={sourceText}
              onChange={(event) => setSourceText(event.target.value)}
              placeholder="粘贴纪要、需求原话或规则说明。"
              className="min-h-[220px]"
            />
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setIsImportDialogOpen(false)}>
                取消
              </Button>
              <Button onClick={handleUploadText} disabled={uploading || !sourceName.trim() || !sourceText.trim()}>
                {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                导入文本资料
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={isBindingDialogOpen} onOpenChange={setIsBindingDialogOpen}>
        <DialogContent className="w-[min(640px,92vw)]">
          <DialogHeader>
            <DialogTitle>绑定项目知识库</DialogTitle>
            <DialogDescription>
              为当前项目绑定专属知识库入口。后续资料入库、证据检索和引用都走这个项目自己的知识库。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="rounded-[20px] border border-line bg-white p-4">
              <div className="text-sm font-semibold text-ink">已登记的知识库</div>
              <div className="mt-3 grid gap-3">
                {notebookLibrary.length === 0 ? (
                  <div className="rounded-[16px] border border-dashed border-line bg-slate-50 p-3 text-sm leading-6 text-muted">
                    当前还没有可直接复用的已登记知识库。你可以粘贴知识库入口链接完成绑定，或者直接为当前项目创建一个专属知识库。
                  </div>
                ) : (
                  notebookLibrary.map((notebook) => (
                    <button
                      key={notebook.id}
                      type="button"
                      className={cn(
                        'rounded-[18px] border p-4 text-left transition',
                        selectedKnowledgeBaseId === notebook.id
                          ? 'border-accent bg-accentSoft'
                          : 'border-line bg-slate-50 hover:border-accent/30 hover:bg-white'
                      )}
                      onClick={() => setSelectedKnowledgeBaseId(notebook.id)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-ink">{notebook.name}</div>
                          <p className="mt-2 text-sm leading-6 text-muted">{notebook.description}</p>
                        </div>
                        <Badge variant={selectedKnowledgeBaseId === notebook.id ? 'accent' : 'default'}>
                          {selectedKnowledgeBaseId === notebook.id ? '已选择' : `使用 ${notebook.use_count} 次`}
                        </Badge>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {notebook.topics.map((topic) => (
                          <Badge key={`${notebook.id}-${topic}`}>{topic}</Badge>
                        ))}
                      </div>
                    </button>
                  ))
                )}
              </div>
              <div className="mt-3 flex justify-end">
                <Button onClick={handleBindRegisteredKnowledgeBase} disabled={bindingNotebook || !selectedKnowledgeBaseId}>
                  {bindingNotebook ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  绑定已登记知识库
                </Button>
              </div>
            </div>
            <div className="rounded-[20px] border border-line bg-white p-4">
              <div className="text-sm font-semibold text-ink">为当前项目创建专属知识库</div>
              <p className="mt-2 text-sm leading-6 text-muted">
                直接用当前项目名创建新的项目级知识库，并自动完成绑定。后续资料会沿用这条证据链路继续入库。
              </p>
              <div className="mt-4 flex justify-end">
                <Button onClick={handleCreateAndBindKnowledgeBase} disabled={bindingNotebook}>
                  {bindingNotebook ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  创建并绑定知识库
                </Button>
              </div>
            </div>
            <Input
              id="knowledge-base-url"
              name="knowledge-base-url"
              value={knowledgeBaseUrl}
              onChange={(event) => setKnowledgeBaseUrl(event.target.value)}
              placeholder="粘贴知识库入口链接，例如项目知识库地址"
            />
            <div className="rounded-[20px] border border-line bg-slate-50 p-4 text-sm leading-6 text-muted">
              这里绑定的是项目级知识库入口，不把具体 provider 名称直接当成唯一产品对象暴露给用户。
            </div>
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setIsBindingDialogOpen(false)}>
                取消
              </Button>
              <Button onClick={handleBindKnowledgeBaseUrl} disabled={bindingNotebook || !knowledgeBaseUrl.trim()}>
                {bindingNotebook ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                绑定知识库入口
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
