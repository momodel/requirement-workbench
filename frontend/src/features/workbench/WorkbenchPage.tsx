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
} from '../../lib/types';
import {
  deriveStageState,
  deriveStateOverviewSections,
  type StateOverviewItem,
  type StateOverviewSection,
  WORKBENCH_STAGE_LABELS,
  WORKBENCH_STAGE_ORDER,
  type WorkbenchStage,
} from './workbench-derived';

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

function relativeTime(value: string) {
  return new Date(value).toLocaleString('zh-CN');
}

function statusVariant(status: string) {
  if (status.includes('failed') || status.includes('error') || status.includes('not_configured')) {
    return 'danger' as const;
  }
  if (status.includes('parsed') || status.includes('generated') || status.includes('seed_ready')) {
    return 'success' as const;
  }
  if (status.includes('pending') || status.includes('queued')) {
    return 'warning' as const;
  }
  return 'default' as const;
}

function readinessVariant(status: string) {
  if (status === 'ready') return 'success' as const;
  if (status.includes('required') || status.includes('config') || status.includes('binding')) {
    return 'warning' as const;
  }
  if (status.includes('error') || status.includes('not_configured')) {
    return 'danger' as const;
  }
  return 'default' as const;
}

function parseStatusLabel(status: string) {
  if (status === 'parsed') return '已解析';
  if (status === 'pending') return '解析中';
  if (status === 'queued') return '排队中';
  return status;
}

function syncStatusLabel(status: string) {
  if (status === 'synced') return '已同步';
  if (status === 'pending_sync') return '待同步';
  if (status === 'sync_failed') return '同步失败';
  if (status === 'error') return '异常';
  if (status === 'binding_required') return '未绑定';
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

function stageTone(
  stage: WorkbenchStage,
  primaryStage: WorkbenchStage,
  revisitingStages: WorkbenchStage[]
) {
  if (stage === primaryStage) {
    return {
      badge: '当前重点',
      cardClass: 'border-accent/20 bg-accentSoft/70 text-accent',
      badgeVariant: 'accent' as const,
    };
  }

  if (revisitingStages.includes(stage)) {
    return {
      badge: '补充中',
      cardClass: 'border-amber-200 bg-amber-50 text-amber-900',
      badgeVariant: 'warning' as const,
    };
  }

  const primaryIndex = WORKBENCH_STAGE_ORDER.indexOf(primaryStage);
  const stageIndex = WORKBENCH_STAGE_ORDER.indexOf(stage);

  if (stageIndex < primaryIndex) {
    return {
      badge: '已形成',
      cardClass: 'border-emerald-200 bg-emerald-50 text-emerald-900',
      badgeVariant: 'success' as const,
    };
  }

  return {
    badge: '待进入',
    cardClass: 'border-line bg-slate-50 text-muted',
    badgeVariant: 'default' as const,
  };
}

function getSectionEmptyText(sectionId: string) {
  if (sectionId === 'artifacts') return '当前还没有交付物。';
  if (sectionId === 'versions') return '关键快照还没有生成。';
  return '当前还没有内容。';
}

function getItemBody(item: StateOverviewItem) {
  if (item.kind === 'artifact') {
    return item.body || '当前还没有摘要。';
  }
  return sanitizeStateBody(item.title, item.body);
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
          <Badge variant={statusVariant(source.parse_status)}>{`解析：${source.parse_status}`}</Badge>
          <Badge variant={statusVariant(source.sync_status)}>{`同步：${source.sync_status}`}</Badge>
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

function WorkbenchStageRail({
  primaryStage,
  revisitingStages,
}: {
  primaryStage: WorkbenchStage;
  revisitingStages: WorkbenchStage[];
}) {
  return (
    <div className="grid shrink-0 grid-cols-5 gap-2 rounded-[20px] border border-white/70 bg-white/85 p-1.5 shadow-panel">
      {WORKBENCH_STAGE_ORDER.map((stage) => {
        const tone = stageTone(stage, primaryStage, revisitingStages);

        return (
          <div
            key={stage}
            className={cn('rounded-[16px] border px-3 py-2 transition-colors', tone.cardClass)}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold">{WORKBENCH_STAGE_LABELS[stage]}</div>
              <Badge variant={tone.badgeVariant}>{tone.badge}</Badge>
            </div>
            <div className="mt-1 text-[12px] leading-5 opacity-80">
              {stage === primaryStage
                ? '当前主线推进重点。'
                : revisitingStages.includes(stage)
                  ? '有新信息正在回流补充。'
                  : '作为分析过程中的阶段语义展示。'}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StateSectionCard({
  section,
  onOpen,
  onOpenItem,
}: {
  section: StateOverviewSection;
  onOpen: () => void;
  onOpenItem: (item: StateOverviewItem) => void;
}) {
  const previewItems = section.items.slice(0, section.id === 'artifacts' ? 3 : 2);

  return (
    <div className="rounded-[20px] border border-line bg-slate-50/80 p-3.5">
      <button
        type="button"
        className="w-full text-left transition hover:text-accent"
        aria-label={section.title}
        onClick={onOpen}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-ink">{section.title}</h3>
              {section.recentCount > 0 ? <Badge variant="accent">本轮新增</Badge> : null}
            </div>
            <p className="mt-1 text-xs leading-5 text-muted">{section.description}</p>
          </div>
          <Badge>{section.totalCount}</Badge>
        </div>
      </button>
      <div className="mt-2.5 grid gap-2">
        {previewItems.length === 0 ? (
          <div className="rounded-[16px] border border-dashed border-line bg-white/80 p-3 text-sm text-muted">
            {getSectionEmptyText(section.id)}
          </div>
        ) : (
          previewItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cn(
                'rounded-[16px] border bg-white p-3 text-left transition hover:border-accent/25 hover:bg-slate-50',
                item.isRecent ? 'border-accent/25 bg-accentSoft/30' : 'border-white'
              )}
              onClick={() => onOpenItem(item)}
            >
              <div className="flex items-start justify-between gap-2">
                {item.title === section.title ? (
                  <div className="text-sm font-medium text-ink">{item.kind === 'artifact' ? item.title : '最新条目'}</div>
                ) : (
                  <div className="text-sm font-medium text-ink">{item.title}</div>
                )}
                {item.kind === 'artifact' ? (
                  <Badge variant={statusVariant(item.status)}>{item.artifactType}</Badge>
                ) : null}
              </div>
              <p className="mt-1.5 line-clamp-2 text-sm leading-6 text-muted">{getItemBody(item)}</p>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted">
                <span>{`形成于 ${WORKBENCH_STAGE_LABELS[item.formedStage]}`}</span>
                {item.updatedAt ? <span>{relativeTime(item.updatedAt)}</span> : null}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function StateSectionDrawer({
  section,
  activeItem,
  onClose,
  onSelectItem,
  onOpenArtifact,
  onOpenDocument,
}: {
  section: StateOverviewSection | null;
  activeItem: StateOverviewItem | null;
  onClose: () => void;
  onSelectItem: (item: StateOverviewItem) => void;
  onOpenArtifact: (artifact: ArtifactRecord) => void;
  onOpenDocument: (artifact: ArtifactRecord) => void;
}) {
  return (
    <Dialog open={Boolean(section)} onOpenChange={(open) => !open && onClose()}>
      {section ? (
        <DialogContent className="left-auto right-4 top-4 h-[calc(100vh-2rem)] w-[min(980px,calc(100vw-2rem))] max-w-none translate-x-0 translate-y-0 p-0 data-[state=open]:animate-none">
          <div className="grid h-full grid-cols-[320px_minmax(0,1fr)]">
            <div className="flex min-h-0 flex-col border-r border-line bg-slate-50/80">
              <DialogHeader className="border-b border-line px-5 py-4">
                <DialogTitle>{section.title}</DialogTitle>
                <DialogDescription>{section.description}</DialogDescription>
              </DialogHeader>
              <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
                <div className="grid gap-2">
                  {section.items.length === 0 ? (
                    <div className="rounded-[16px] border border-dashed border-line bg-white p-3 text-sm text-muted">
                      {getSectionEmptyText(section.id)}
                    </div>
                  ) : (
                    section.items.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={cn(
                          'rounded-[18px] border p-3 text-left transition',
                          activeItem?.id === item.id
                            ? 'border-accent bg-accentSoft/50'
                            : 'border-line bg-white hover:border-accent/25 hover:bg-slate-50'
                        )}
                        onClick={() => onSelectItem(item)}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="text-sm font-semibold text-ink">{item.title}</div>
                          {item.isRecent ? <Badge variant="accent">本轮新增</Badge> : null}
                        </div>
                        <p className="mt-1.5 line-clamp-2 text-sm leading-6 text-muted">{getItemBody(item)}</p>
                      </button>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="flex min-h-0 flex-col bg-white">
              <div className="border-b border-line px-5 py-4">
                <div className="text-sm font-medium text-muted">条目详情</div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                {activeItem ? (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-xl font-semibold text-ink">{activeItem.title}</h3>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Badge variant={statusVariant(activeItem.status)}>{activeItem.status}</Badge>
                          <Badge>{WORKBENCH_STAGE_LABELS[activeItem.updatedStage]}</Badge>
                          {activeItem.isRecent ? <Badge variant="accent">本轮新增</Badge> : null}
                        </div>
                      </div>
                      {activeItem.kind === 'artifact' ? (
                        activeItem.contentFormat === 'html' ? (
                          <Button
                            size="sm"
                            onClick={() =>
                              onOpenArtifact({
                                id: activeItem.id,
                                project_id: '',
                                artifact_type: activeItem.artifactType ?? 'artifact',
                                title: activeItem.title,
                                summary: activeItem.body,
                                status: activeItem.status,
                                content_format: activeItem.contentFormat ?? 'html',
                                storage_path: null,
                                preview_url: activeItem.previewUrl ?? null,
                                body: activeItem.documentBody ?? null,
                                updated_at: activeItem.updatedAt ?? '',
                              })
                            }
                          >
                            打开预览
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() =>
                              onOpenDocument({
                                id: activeItem.id,
                                project_id: '',
                                artifact_type: activeItem.artifactType ?? 'artifact',
                                title: activeItem.title,
                                summary: activeItem.body,
                                status: activeItem.status,
                                content_format: activeItem.contentFormat ?? 'document',
                                storage_path: null,
                                preview_url: activeItem.previewUrl ?? null,
                                body: activeItem.documentBody ?? null,
                                updated_at: activeItem.updatedAt ?? '',
                              })
                            }
                          >
                            查看正文
                          </Button>
                        )
                      ) : null}
                    </div>

                    <div className="grid gap-3 rounded-[22px] border border-line bg-slate-50/80 p-4 text-sm">
                      <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-3">
                        <div className="font-medium text-muted">形成于</div>
                        <div className="text-ink">{WORKBENCH_STAGE_LABELS[activeItem.formedStage]}</div>
                      </div>
                      <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-3">
                        <div className="font-medium text-muted">最近更新于</div>
                        <div className="text-ink">{WORKBENCH_STAGE_LABELS[activeItem.updatedStage]}</div>
                      </div>
                      <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-3">
                        <div className="font-medium text-muted">更新时间</div>
                        <div className="text-ink">
                          {activeItem.updatedAt ? relativeTime(activeItem.updatedAt) : '暂无'}
                        </div>
                      </div>
                      <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-3">
                        <div className="font-medium text-muted">来源资料</div>
                        <div className="text-ink">{`${activeItem.sourceCount} 份`}</div>
                      </div>
                    </div>

                    <div className="rounded-[22px] border border-line bg-white p-4">
                      <div className="mb-3 text-sm font-medium text-muted">正文</div>
                      <div className="whitespace-pre-wrap text-sm leading-7 text-ink">
                        {activeItem.kind === 'artifact' ? activeItem.body || '当前还没有摘要。' : activeItem.body}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-[20px] border border-dashed border-line bg-slate-50 p-4 text-sm leading-6 text-muted">
                    先从左侧列表选择一个条目，再查看详情。
                  </div>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      ) : null}
    </Dialog>
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
  const [notebookUrl, setNotebookUrl] = useState('');
  const [selectedNotebookId, setSelectedNotebookId] = useState('');
  const [selectedSource, setSelectedSource] = useState<SourceRecord | null>(null);
  const [sourcePreviewPosition, setSourcePreviewPosition] = useState({ top: 120, left: 120 });
  const [activeArtifact, setActiveArtifact] = useState<ArtifactRecord | null>(null);
  const [activeDocument, setActiveDocument] = useState<ArtifactRecord | null>(null);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [activeSectionItemId, setActiveSectionItemId] = useState<string | null>(null);
  const sourceInputRef = useRef<HTMLInputElement | null>(null);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);
  const lastMessageContent = messages[messages.length - 1]?.content ?? '';

  const latestVersions = state.versions.slice(0, 3);
  const latestArtifacts = useMemo(() => getLatestArtifactsByType(artifacts), [artifacts]);
  const stageState = useMemo(
    () => deriveStageState(state, recentInsightIds),
    [recentInsightIds, state]
  );
  const overviewSections = useMemo(
    () => deriveStateOverviewSections(state, artifacts, recentInsightIds),
    [artifacts, recentInsightIds, state]
  );
  const activeSection = useMemo(
    () => overviewSections.find((section) => section.id === activeSectionId) ?? null,
    [activeSectionId, overviewSections]
  );
  const activeSectionItem = useMemo(
    () => activeSection?.items.find((item) => item.id === activeSectionItemId) ?? null,
    [activeSection, activeSectionItemId]
  );
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
    chatBottomRef.current?.scrollIntoView({ block: 'end' });
  }, [lastMessageContent, messages.length, notices.length, sending]);

  useEffect(() => {
    if (!activeSection) {
      setActiveSectionItemId(null);
      return;
    }

    if (activeSection.items.length === 0) {
      setActiveSectionItemId(null);
      return;
    }

    if (!activeSection.items.some((item) => item.id === activeSectionItemId)) {
      setActiveSectionItemId(activeSection.items[0]?.id ?? null);
    }
  }, [activeSection, activeSectionItemId]);

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

  async function handleBindNotebook() {
    const url = notebookUrl.trim();
    if (!url) return;
    await onBindProjectNotebook({ sourceUrl: url });
    setNotebookUrl('');
    setIsBindingDialogOpen(false);
  }

  async function handleBindExistingNotebook() {
    if (!selectedNotebookId) return;
    await onBindProjectNotebook({ notebookId: selectedNotebookId });
    setSelectedNotebookId('');
    setIsBindingDialogOpen(false);
  }

  async function handleCreateAndBindNotebook() {
    await onCreateAndBindProjectNotebook();
    setSelectedNotebookId('');
    setNotebookUrl('');
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
                  <Badge variant={readinessVariant(readiness.claude.status)}>{`Claude: ${readiness.claude.status}`}</Badge>
                  <Badge variant={readinessVariant(readiness.notebooklm.status)}>{`NotebookLM: ${readiness.notebooklm.status}`}</Badge>
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

        <WorkbenchStageRail
          primaryStage={stageState.primaryStage}
          revisitingStages={stageState.revisitingStages}
        />

        <section className="grid min-h-0 flex-1 grid-cols-[292px_minmax(0,1fr)_332px] gap-3">
          <Card className="relative flex min-h-0 flex-col overflow-hidden border-white/80 bg-white/92">
            <CardHeader className="shrink-0 p-3 pb-2.5">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-base">项目知识库</CardTitle>
                <div className="text-xs text-muted">{`${sources.length} 份 · ${referencedSourceCount} 已同步 · ${pendingSourceCount} 待处理`}</div>
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
                                aria-label={`重试同步 ${source.name}`}
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
                  {`${overviewSections.length} 个资产分区 · ${totalInsightCount} 条沉淀 · ${artifacts.length} 份交付物`}
                </div>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 overflow-y-auto space-y-3 px-3 pb-3 pt-0">
              <div className="rounded-[20px] border border-line bg-slate-50/80 p-3.5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-ink">产物动作</h3>
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
                  {artifactHistoryCount > 0 ? (
                    <div className="rounded-[16px] border border-dashed border-line bg-white/80 p-3 text-xs text-muted">
                      {`当前已折叠 ${artifactHistoryCount} 个历史版本，侧栏默认只显示每类最新交付物。`}
                    </div>
                  ) : null}
                </div>
              </div>

              {overviewSections.map((section) => (
                <StateSectionCard
                  key={section.id}
                  section={
                    section.id === 'artifacts'
                      ? { ...section, items: section.items.slice(0, 3) }
                      : section.id === 'versions'
                        ? { ...section, items: section.items.slice(0, 2) }
                        : section
                  }
                  onOpen={() => setActiveSectionId(section.id)}
                  onOpenItem={(item) => {
                    setActiveSectionId(section.id);
                    setActiveSectionItemId(item.id);
                  }}
                />
              ))}

              {latestVersions.length > 0 ? (
                <div className="rounded-[20px] border border-line bg-white p-3.5">
                  <div className="text-sm font-semibold text-ink">最近更新</div>
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

      <StateSectionDrawer
        section={activeSection}
        activeItem={activeSectionItem}
        onClose={() => setActiveSectionId(null)}
        onSelectItem={(item) => setActiveSectionItemId(item.id)}
        onOpenArtifact={setActiveArtifact}
        onOpenDocument={setActiveDocument}
      />

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
            <DialogDescription>这里放运行链路和项目绑定状态，不占用知识库主区域。</DialogDescription>
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
                  <Badge variant={readinessVariant(readiness.claude.status)}>{readiness.claude.status}</Badge>
                </div>
              </div>

              <div className="rounded-[20px] border border-line bg-slate-50/80 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-ink">NotebookLM</div>
                    <p className="mt-1 text-sm leading-6 text-muted">{readiness.notebooklm.summary}</p>
                    {readiness.notebooklm.detail ? (
                      <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">
                        {readiness.notebooklm.detail}
                      </p>
                    ) : null}
                  </div>
                  <Badge variant={readinessVariant(readiness.notebooklm.status)}>{readiness.notebooklm.status}</Badge>
                </div>
                <div className="mt-4 flex flex-wrap gap-3">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setIsRuntimeDialogOpen(false);
                      setIsBindingDialogOpen(true);
                    }}
                    disabled={bindingNotebook}
                  >
                    {bindingNotebook ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    绑定项目 Notebook
                  </Button>
                </div>
              </div>
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
            <DialogTitle>绑定项目 Notebook</DialogTitle>
            <DialogDescription>
              为当前项目绑定专属的 NotebookLM notebook，后面所有 grounding 都走这个项目自己的 notebook。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="rounded-[20px] border border-line bg-white p-4">
              <div className="text-sm font-semibold text-ink">已登记的 Notebook</div>
              <div className="mt-3 grid gap-3">
                {notebookLibrary.length === 0 ? (
                  <div className="rounded-[16px] border border-dashed border-line bg-slate-50 p-3 text-sm leading-6 text-muted">
                    当前项目内还没有可用的 Notebook 列表。你可以直接粘贴 NotebookLM 链接完成绑定，或者直接创建一个项目专属 Notebook。
                  </div>
                ) : (
                  notebookLibrary.map((notebook) => (
                    <button
                      key={notebook.id}
                      type="button"
                      className={cn(
                        'rounded-[18px] border p-4 text-left transition',
                        selectedNotebookId === notebook.id
                          ? 'border-accent bg-accentSoft'
                          : 'border-line bg-slate-50 hover:border-accent/30 hover:bg-white'
                      )}
                      onClick={() => setSelectedNotebookId(notebook.id)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-semibold text-ink">{notebook.name}</div>
                          <p className="mt-2 text-sm leading-6 text-muted">{notebook.description}</p>
                        </div>
                        <Badge variant={selectedNotebookId === notebook.id ? 'accent' : 'default'}>
                          {selectedNotebookId === notebook.id ? '已选择' : `使用 ${notebook.use_count} 次`}
                        </Badge>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {notebook.topics.map((topic) => (
                          <Badge key={`${notebook.id}-${topic}`}>
                            {topic}
                          </Badge>
                        ))}
                      </div>
                    </button>
                  ))
                )}
              </div>
              <div className="mt-3 flex justify-end">
                <Button onClick={handleBindExistingNotebook} disabled={bindingNotebook || !selectedNotebookId}>
                  {bindingNotebook ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  绑定已登记 Notebook
                </Button>
              </div>
            </div>
            <div className="rounded-[20px] border border-line bg-white p-4">
              <div className="text-sm font-semibold text-ink">为当前项目创建专属 Notebook</div>
              <p className="mt-2 text-sm leading-6 text-muted">
                直接用当前项目名创建新的 NotebookLM notebook，并自动完成项目绑定。后续新需求项目也走这条正式能力。
              </p>
              <div className="mt-4 flex justify-end">
                <Button onClick={handleCreateAndBindNotebook} disabled={bindingNotebook}>
                  {bindingNotebook ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  创建并绑定 Notebook
                </Button>
              </div>
            </div>
            <Input
              id="notebook-url"
              name="notebook-url"
              value={notebookUrl}
              onChange={(event) => setNotebookUrl(event.target.value)}
              placeholder="https://notebooklm.google.com/notebook/..."
            />
            <div className="rounded-[20px] border border-line bg-slate-50 p-4 text-sm leading-6 text-muted">
              这里绑定的是项目级 notebook，不再依赖全局默认 notebook。绑定完成后，后续上传到当前项目的资料会按后端标准化结果自动同步到这个 notebook。
            </div>
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setIsBindingDialogOpen(false)}>
                取消
              </Button>
              <Button onClick={handleBindNotebook} disabled={bindingNotebook || !notebookUrl.trim()}>
                {bindingNotebook ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                绑定项目 Notebook
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
