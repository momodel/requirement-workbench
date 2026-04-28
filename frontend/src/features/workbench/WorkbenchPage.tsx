import {
  AlertCircle,
  X,
  ChevronDown,
  ChevronRight,
  History,
  List,
  Bot,
  CheckCircle2,
  FolderKanban,
  Loader2,
  MonitorCog,
  PanelRight,
  Paperclip,
  RotateCcw,
  Send,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react';
import { createPortal } from 'react-dom';
import type { ClipboardEvent as ReactClipboardEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
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
import {
  getArtifactDisplayLabel,
  getArtifactFormatLabel,
  getArtifactStatusLabel,
  getArtifactTypeLabel,
} from '../../lib/artifact-display';
import { listArtifacts, listArtifactHistory, promoteArtifact } from '../../lib/api';
import { Textarea } from '../../components/ui/textarea';
import { cn } from '../../lib/utils';
import type {
  ArtifactRecord,
  ChatImageAttachment,
  MessageActionEvent,
  MessageRecord,
  ProjectReadiness,
  ProjectState,
  ProjectSummary,
  SourceContentRecord,
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
  notices: Array<{ id: string; kind: 'error' | 'info'; title: string; body: string }>;
  sending: boolean;
  uploading: boolean;
  deletingSourceId: string | null;
  retryingSourceId: string | null;
  initializingKnowledgeBase: boolean;
  onSendMessage: (message: string, imageAttachments?: ChatImageAttachment[]) => Promise<void>;
  onUploadTextSource: (payload: { name: string; text: string }) => Promise<void>;
  onUploadFileSource: (files: File[]) => Promise<void>;
  onDeleteSource: (sourceId: string) => Promise<void>;
  onReindexSource: (sourceId: string) => Promise<void>;
  onRequestSourceContent: (sourceId: string) => Promise<SourceContentRecord>;
  onInitializeKnowledgeBase: () => Promise<boolean>;
  onArtifactsChanged?: (artifacts: ArtifactRecord[]) => void;
};

type PendingChatImage = ChatImageAttachment & {
  id: string;
  previewUrl: string;
};

function relativeTime(value: string) {
  return new Date(value).toLocaleString('zh-CN');
}

function compactRelativeTime(value: string) {
  const ts = new Date(value).getTime();
  if (Number.isNaN(ts)) return value;
  const delta = Date.now() - ts;
  if (delta < 0) return '刚刚';
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (delta < minute) return '刚刚';
  if (delta < hour) return `${Math.floor(delta / minute)} 分钟前`;
  if (delta < day) {
    const d = new Date(ts);
    return `今天 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
  if (delta < 7 * day) return `${Math.floor(delta / day)} 天前`;
  const d = new Date(ts);
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function statusVariant(status: string) {
  if (status.includes('failed') || status.includes('error') || status.includes('not_configured')) {
    return 'danger' as const;
  }
  if (
    status.includes('parsed') ||
    status.includes('indexed') ||
    status.includes('generated') ||
    status.includes('seed_ready')
  ) {
    return 'success' as const;
  }
  if (
    status.includes('pending') ||
    status.includes('queued') ||
    status.includes('processing') ||
    status.includes('indexing')
  ) {
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

function runtimeHealth(readiness: ProjectReadiness | null, initializingKnowledgeBase: boolean) {
  const statuses = [
    readiness?.claude.status,
    readiness?.evidence?.status,
    readiness?.wiki?.status,
    initializingKnowledgeBase ? 'pending' : null,
  ].filter(Boolean) as string[];

  if (statuses.length === 0) {
    return { label: '未知', dotClass: 'bg-stone/40', buttonClass: 'border-line bg-ivory text-muted' };
  }
  if (statuses.some((status) => /failed|error|not_configured|required|missing/i.test(status))) {
    return { label: '异常', dotClass: 'bg-[#fbeeec]0', buttonClass: 'border-[#e3c8c4] bg-[#fbeeec] text-errorWarm' };
  }
  if (statuses.some((status) => /pending|queued|initializing|binding|config/i.test(status))) {
    return { label: '处理中', dotClass: 'bg-[#f5ead2]0', buttonClass: 'border-[#e6d3b3] bg-[#f5ead2] text-[#7a5a1d]' };
  }
  if (statuses.every((status) => status === 'ready')) {
    return { label: '就绪', dotClass: 'bg-[#e6efe5]0', buttonClass: 'border-line bg-ivory text-ink' };
  }
  return { label: '检查中', dotClass: 'bg-[#f5ead2]0', buttonClass: 'border-[#e6d3b3] bg-[#f5ead2] text-[#7a5a1d]' };
}

function parseStatusLabel(status: string) {
  if (status === 'parsed') return '已标准化';
  if (status === 'processing') return '标准化中';
  if (status === 'pending') return '标准化中';
  if (status === 'queued') return '排队中';
  if (status === 'failed') return '标准化失败';
  if (status === 'error') return '标准化异常';
  if (status === 'not_configured') return '标准化未配置';
  return status;
}

function sourceCompactStatus(source: SourceRecord) {
  const normalizeStatus = sourceNormalizeStatus(source);
  const indexStatus = sourceIndexStatus(source);

  if (indexStatus === 'index_failed' || indexStatus === 'error') {
    return { label: '索引失败', dotClass: 'bg-[#fbeeec]0', textClass: 'text-errorWarm' };
  }
  if (normalizeStatus === 'pending' || normalizeStatus === 'queued') {
    return { label: parseStatusLabel(normalizeStatus), dotClass: 'bg-[#f5ead2]0', textClass: 'text-[#7a5a1d]' };
  }
  if (indexStatus === 'indexing' || indexStatus === 'pending' || indexStatus === 'queued') {
    return { label: indexStatusLabel(indexStatus), dotClass: 'bg-[#f5ead2]0', textClass: 'text-[#7a5a1d]' };
  }
  if (indexStatus === 'indexed') {
    return { label: '已索引', dotClass: 'bg-[#e6efe5]0', textClass: 'text-[#3d6b50]' };
  }
  if (normalizeStatus === 'parsed') {
    return { label: '已解析', dotClass: 'bg-[#e6efe5]0', textClass: 'text-[#3d6b50]' };
  }
  return { label: indexStatusLabel(indexStatus), dotClass: 'bg-stone/40', textClass: 'text-muted' };
}

function sourceKindLabel(sourceKind: string) {
  return sourceKind.replace(/^file:/, '').toUpperCase();
}

function indexStatusLabel(status: string) {
  if (status === 'indexed') return '已入库';
  if (status === 'indexing') return '入库中';
  if (status === 'pending') return '待入库';
  if (status === 'normalization_pending') return '待标准化';
  if (status === 'normalization_failed') return '标准化失败';
  if (status === 'index_failed') return '入库失败';
  if (status === 'not_configured') return '未配置';
  if (status === 'knowledge_base_missing') return '待初始化知识库';
  if (status === 'not_indexable') return '不可索引';
  if (status === 'error') return '异常';
  return status;
}

function sourceWikiBadge(source: SourceRecord) {
  const status = source.wiki_sync_status;
  // Only surface non-default wiki states so the row stays compact when wiki
  // maintenance succeeded. The "boring" maintained state is implied by
  // "已索引" already; only call out in-flight or failure cases.
  if (!status || status === 'maintained') return null;
  if (status === 'maintaining') {
    return { label: 'wiki 写入中', dotClass: 'bg-[#7a5a1d]', textClass: 'text-[#7a5a1d]' };
  }
  if (status === 'failed') {
    return { label: 'wiki 失败', dotClass: 'bg-errorWarm', textClass: 'text-errorWarm' };
  }
  if (status === 'skipped') {
    return { label: 'wiki 跳过', dotClass: 'bg-stone/60', textClass: 'text-muted' };
  }
  return { label: `wiki ${status}`, dotClass: 'bg-stone/60', textClass: 'text-muted' };
}

function sourceNormalizeStatus(source: SourceRecord): string {
  return source.normalize_status ?? (source as unknown as { parse_status?: string }).parse_status ?? 'pending';
}

function sourceNormalizeSummary(source: SourceRecord): string | null {
  return source.normalize_summary ?? (source as unknown as { parse_summary?: string | null }).parse_summary ?? null;
}

function sourceIndexStatus(source: SourceRecord): string {
  return source.index_status ?? (source as unknown as { sync_status?: string }).sync_status ?? 'pending';
}

function sourceIndexError(source: SourceRecord): string | null {
  return source.index_error ?? (source as unknown as { sync_error?: string | null }).sync_error ?? null;
}

function canRetrySource(source: SourceRecord) {
  const indexStatus = sourceIndexStatus(source);
  if (
    indexStatus === 'index_failed' ||
    indexStatus === 'error' ||
    indexStatus === 'normalization_failed' ||
    indexStatus === 'not_configured'
  ) {
    return true;
  }

  if (source.source_kind !== 'audio') {
    return false;
  }

  const normalizeStatus = sourceNormalizeStatus(source);
  return normalizeStatus === 'failed' || normalizeStatus === 'error' || normalizeStatus === 'not_configured';
}

function sourceContentLabel(record: SourceContentRecord | null) {
  if (!record) return '完整正文';
  if (record.content_status === 'summary_only') return '当前摘要';
  if (record.content_status === 'unavailable') return '暂无正文';
  return '完整正文';
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
      cardClass: 'border-[#e6d3b3] bg-[#f5ead2] text-[#7a5a1d]',
      badgeVariant: 'warning' as const,
    };
  }

  const primaryIndex = WORKBENCH_STAGE_ORDER.indexOf(primaryStage);
  const stageIndex = WORKBENCH_STAGE_ORDER.indexOf(stage);

  if (stageIndex < primaryIndex) {
    return {
      badge: '已形成',
      cardClass: 'border-[#cdded0] bg-[#e6efe5] text-[#3d6b50]',
      badgeVariant: 'success' as const,
    };
  }

  return {
    badge: '待进入',
    cardClass: 'border-line bg-parchment text-muted',
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


function toArtifactRecord(item: StateOverviewItem): ArtifactRecord {
  return {
    id: item.id,
    project_id: '',
    artifact_type: item.artifactType ?? 'artifact',
    title: item.title,
    summary: item.body,
    status: item.status,
    content_format: item.contentFormat ?? 'document',
    storage_path: null,
    preview_url: item.previewUrl ?? null,
    body: item.documentBody ?? null,
    revision_number: 1,
    updated_at: item.updatedAt ?? '',
  };
}

function itemTimestamp(item: StateOverviewItem) {
  if (!item.updatedAt) return 0;
  const timestamp = new Date(item.updatedAt).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function getSectionLastUpdated(section: StateOverviewSection) {
  const latestTimestamp = Math.max(0, ...section.items.map(itemTimestamp));
  if (latestTimestamp === 0) return '暂无更新';
  return relativeTime(new Date(latestTimestamp).toISOString());
}

function getRecentOverviewItems(sections: StateOverviewSection[]) {
  return sections
    .flatMap((section) =>
      section.items
        .filter((item) => item.isRecent || (item.kind === 'artifact' && itemTimestamp(item) > 0))
        .map((item) => ({ section, item }))
    )
    .sort((left, right) => itemTimestamp(right.item) - itemTimestamp(left.item))
    .slice(0, 5);
}

function getArtifactStatusSummaryLabel(section: StateOverviewSection) {
  const summary = section.artifactStatusSummary;
  if (!summary) return null;

  const parts = [];
  if (summary.generating > 0) parts.push(`${summary.generating} 生成中`);
  if (summary.generated > 0) parts.push(`${summary.generated} 已生成`);
  if (summary.failed > 0) parts.push(`${summary.failed} 失败`);
  return parts.length > 0 ? parts.join(' · ') : '暂无交付物';
}

function getSectionSummaryLine(section: StateOverviewSection) {
  return getArtifactStatusSummaryLabel(section) ?? section.description;
}

function getArtifactMeta(item: StateOverviewItem) {
  if (item.kind !== 'artifact') {
    return null;
  }

  return {
    typeLabel: getArtifactTypeLabel(item.artifactType ?? ''),
    displayLabel: getArtifactDisplayLabel({
      artifact_type: item.artifactType ?? '',
      content_format: item.contentFormat ?? '',
    }),
    formatLabel: getArtifactFormatLabel(item.artifactType ?? '', item.contentFormat),
    statusLabel: getArtifactStatusLabel(item.status),
  };
}

function RuntimeProviderCard({
  title,
  summary,
  detail,
  status,
}: {
  title: string;
  summary: string;
  detail: string | null;
  status: string;
}) {
  return (
    <div className="rounded-[20px] border border-line bg-slate-50/80 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium text-ink">{title}</div>
          <p className="mt-1 text-sm leading-6 text-muted">{summary}</p>
          {detail ? <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">{detail}</p> : null}
        </div>
        <Badge variant={readinessVariant(status)}>{status}</Badge>
      </div>
    </div>
  );
}

function SourcePreview({
  source,
  position,
  contentRecord,
  loading,
  error,
  onClose,
}: {
  source: SourceRecord;
  position: { top: number; left: number };
  contentRecord: SourceContentRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const contentScrollRef = useRef<HTMLDivElement | null>(null);
  const previewText = contentRecord?.content ?? sourceNormalizeSummary(source) ?? '当前还没有可展示的正文。';

  useEffect(() => {
    const scrollContainer = contentScrollRef.current;
    if (!scrollContainer) {
      return;
    }
    if (typeof scrollContainer.scrollTo === 'function') {
      scrollContainer.scrollTo({ top: 0, behavior: 'auto' });
      return;
    }
    scrollContainer.scrollTop = 0;
  }, [source.id]);

  return createPortal(
    <div
      className="fixed z-50 w-[360px] rounded-[24px] border border-borderCream bg-ivory p-5 shadow-whisper"
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
          <Badge variant={statusVariant(sourceNormalizeStatus(source))}>
            {`标准化：${parseStatusLabel(sourceNormalizeStatus(source))}`}
          </Badge>
          <Badge variant={statusVariant(sourceIndexStatus(source))}>
            {`入库：${indexStatusLabel(sourceIndexStatus(source))}`}
          </Badge>
        </div>
        <p className="text-xs text-muted">{`导入时间：${relativeTime(source.created_at)}`}</p>
        <div className="rounded-[18px] border border-line bg-slate-50/80 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted">
              {sourceContentLabel(contentRecord)}
            </div>
            {loading ? <Loader2 className="h-4 w-4 animate-spin text-muted" /> : null}
          </div>
          <p className="mt-2 text-xs leading-5 text-muted">
            {error ?? contentRecord?.detail ?? '正在拉取资料正文。'}
          </p>
          <div
            ref={contentScrollRef}
            className="mt-3 max-h-[52vh] overflow-y-auto rounded-[14px] border border-white bg-white px-3 py-3 text-sm leading-7 text-ink"
          >
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>正在加载完整正文…</span>
              </div>
            ) : (
              <div className="whitespace-pre-wrap">{previewText}</div>
            )}
          </div>
        </div>
        {sourceNormalizeSummary(source) && contentRecord?.content_status === 'full_text' ? (
          <div className="rounded-[18px] border border-line bg-white p-4">
            <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted">标准化摘要</div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted">{sourceNormalizeSummary(source)}</p>
          </div>
        ) : null}
        {sourceIndexError(source) ? (
          <div className="rounded-2xl border border-[#e6d3b3] bg-[#f5ead2] p-3 text-[#7a5a1d]">
            {sourceIndexError(source)}
          </div>
        ) : null}
      </div>
    </div>,
    document.body
  );
}

function SourceFileRow({
  source,
  deletingSourceId,
  retryingSourceId,
  onPreview,
  onDeleteSource,
  onReindexSource,
}: {
  source: SourceRecord;
  deletingSourceId: string | null;
  retryingSourceId: string | null;
  onPreview: (source: SourceRecord, rect: DOMRect) => void;
  onDeleteSource: (sourceId: string) => Promise<void>;
  onReindexSource: (sourceId: string) => Promise<void>;
}) {
  const canRetrySync = canRetrySource(source);
  const compactStatus = sourceCompactStatus(source);
  const wikiBadge = sourceWikiBadge(source);
  const normalizeStatus = sourceNormalizeStatus(source);
  const indexStatus = sourceIndexStatus(source);
  const legacyIndexLabel = indexStatusLabel(indexStatus);

  return (
    <div className="group overflow-hidden rounded-[16px] border border-borderCream bg-ivory px-2.5 py-2 transition hover:border-accent/25 hover:bg-parchment/70">
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-[12px] border border-line bg-parchment text-xs font-semibold text-muted transition group-hover:border-accent/20 group-hover:text-accent"
          onClick={(event) => onPreview(source, event.currentTarget.getBoundingClientRect())}
          aria-label={`查看 ${source.name}`}
        >
          {sourceKindLabel(source.source_kind).slice(0, 3)}
        </button>
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={(event) => onPreview(source, event.currentTarget.getBoundingClientRect())}
        >
          <div className="truncate text-sm font-semibold text-ink">{source.name}</div>
          <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
            <span className={cn('flex shrink-0 items-center gap-1', compactStatus.textClass)}>
              <span className={cn('h-1.5 w-1.5 rounded-full', compactStatus.dotClass)} />
              <span className="whitespace-nowrap">{compactStatus.label}</span>
            </span>
            {wikiBadge ? (
              <>
                <span className="shrink-0">·</span>
                <span
                  className={cn('flex shrink-0 items-center gap-1', wikiBadge.textClass)}
                  title={source.wiki_error ?? undefined}
                >
                  <span className={cn('h-1.5 w-1.5 rounded-full', wikiBadge.dotClass)} />
                  <span className="whitespace-nowrap">{wikiBadge.label}</span>
                </span>
              </>
            ) : null}
            <span className="shrink-0">·</span>
            <span
              className="min-w-0 truncate text-muted"
              title={relativeTime(source.created_at)}
            >
              {compactRelativeTime(source.created_at)}
            </span>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-0.5">
          {canRetrySync ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-accent"
              aria-label={`重建索引 ${source.name}`}
              disabled={retryingSourceId === source.id}
              onClick={async (event) => {
                event.stopPropagation();
                await onReindexSource(source.id);
              }}
            >
              {retryingSourceId === source.id ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
              重试
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted"
            aria-label={`删除 ${source.name}`}
            disabled={deletingSourceId === source.id}
            onClick={async (event) => {
              event.stopPropagation();
              await onDeleteSource(source.id);
            }}
          >
            {deletingSourceId === source.id ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>
      </div>
      {sourceNormalizeSummary(source) ? (
        <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-muted">
          {sourceNormalizeSummary(source)}
        </p>
      ) : null}
      <div className="sr-only">
        <span>{`标准化：${parseStatusLabel(normalizeStatus)}`}</span>
        <span>{`入库：${legacyIndexLabel}`}</span>
      </div>
    </div>
  );
}

function RuntimeStatusButton({
  readiness,
  initializingKnowledgeBase,
  onClick,
}: {
  readiness: ProjectReadiness | null;
  initializingKnowledgeBase: boolean;
  onClick: () => void;
}) {
  const health = runtimeHealth(readiness, initializingKnowledgeBase);

  return (
    <Button
      variant="secondary"
      size="sm"
      className={cn('h-9 gap-2 px-3', health.buttonClass)}
      onClick={onClick}
      title={`运行状态：${health.label}`}
    >
      <span className={cn('h-2 w-2 rounded-full', health.dotClass)} />
      <MonitorCog className="h-4 w-4" />
      运行状态
    </Button>
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
    <div className="flex min-w-0 items-center gap-1">
      {WORKBENCH_STAGE_ORDER.map((stage, index) => {
        const tone = stageTone(stage, primaryStage, revisitingStages);
        const isActive = stage === primaryStage;
        const isDone = WORKBENCH_STAGE_ORDER.indexOf(stage) < WORKBENCH_STAGE_ORDER.indexOf(primaryStage);

        return (
          <div key={stage} className="flex min-w-0 items-start gap-1">
            <div
              className={cn(
                'flex w-16 flex-col items-center gap-0.5 rounded-[14px] px-1.5 py-1 text-[11px] font-medium transition-colors',
                isActive
                  ? 'bg-accentSoft text-accent shadow-sm'
                  : isDone
                    ? 'text-[#3d6b50]'
                    : revisitingStages.includes(stage)
                      ? 'bg-[#f5ead2] text-[#7a5a1d]'
                      : 'text-muted'
              )}
              title={tone.badge}
            >
              <span
                className={cn(
                  'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px]',
                  isActive
                    ? 'border-accent bg-accent text-white'
                    : isDone
                      ? 'border-[#cdded0] bg-[#e6efe5] text-[#3d6b50]'
                      : 'border-borderCream bg-ivory text-muted'
                )}
              >
                {index + 1}
              </span>
              <span className="w-full truncate text-center leading-4">{WORKBENCH_STAGE_LABELS[stage]}</span>
            </div>
            {index < WORKBENCH_STAGE_ORDER.length - 1 ? (
              <div className={cn('mt-3 hidden h-px w-3 xl:block', isDone ? 'bg-accent/45' : 'bg-line')} />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function ArtifactInlineActions({
  item,
  onOpenArtifact,
  onOpenDocument,
  showPendingBadge = true,
}: {
  item: StateOverviewItem;
  onOpenArtifact: (artifact: ArtifactRecord) => void;
  onOpenDocument: (artifact: ArtifactRecord) => void;
  showPendingBadge?: boolean;
}) {
  if (item.kind !== 'artifact') return null;

  const artifact = toArtifactRecord(item);
  const isHtml = item.contentFormat === 'html';

  if (item.status === 'generating') {
    return showPendingBadge ? <Badge variant="warning">生成中</Badge> : null;
  }
  if (item.status === 'failed') {
    return showPendingBadge ? <Badge variant="danger">失败</Badge> : null;
  }

  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      className="h-7 px-2.5 text-xs"
      onClick={(event) => {
        event.stopPropagation();
        if (isHtml) {
          onOpenArtifact(artifact);
          return;
        }
        onOpenDocument(artifact);
      }}
    >
      {isHtml ? '预览' : '正文'}
    </Button>
  );
}

function StateSectionCard({
  section,
  isExpanded,
  onToggle,
  onOpen,
  onOpenItem,
}: {
  section: StateOverviewSection;
  isExpanded: boolean;
  onToggle: () => void;
  onOpen: () => void;
  onOpenItem: (item: StateOverviewItem) => void;
}) {
  const previewItems = section.items.slice(0, 3);
  const summaryLine = getSectionSummaryLine(section);
  const hasGeneratingArtifacts = Boolean(section.artifactStatusSummary?.generating);

  return (
    <div className="rounded-[14px] border border-borderCream bg-ivory px-2.5 py-2 transition hover:border-accent/20">
      <div className="flex min-h-8 items-center gap-2">
        <button
          type="button"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted transition hover:bg-parchment hover:text-accent"
          aria-label={`${isExpanded ? '收起' : '展开'} ${section.title}`}
          aria-expanded={isExpanded}
          onClick={onToggle}
        >
          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        <button
          type="button"
          className="min-w-0 flex-1 text-left transition hover:text-accent"
          aria-label={section.title}
          onClick={onOpen}
          title={section.description}
        >
          <div className="flex min-w-0 items-center gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-1.5">
                <h3 className="truncate text-sm font-semibold text-ink">{section.title}</h3>
                {hasGeneratingArtifacts ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#9a7c2e]" aria-label="交付物生成中" />
                ) : null}
                {section.recentCount > 0 ? <span className="h-2 w-2 shrink-0 rounded-full bg-accent" aria-label="本轮新增" /> : null}
              </div>
              <div className="truncate text-[11px] text-muted" title={summaryLine}>
                {summaryLine}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {section.artifactStatusSummary?.failed ? <span className="h-2 w-2 rounded-full bg-[#fbeeec]0" aria-label="失败" /> : null}
              {section.recentCount > 0 ? <span className="h-2 w-2 rounded-full bg-accent" aria-label="本轮新增" /> : null}
              <span className="grid h-6 min-w-6 place-items-center rounded-full border border-line bg-parchment px-1.5 text-[11px] text-muted">
                {section.totalCount}
              </span>
            </div>
          </div>
        </button>

        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 w-7 shrink-0 rounded-full p-0"
          aria-label={`查看全部 ${section.title}`}
          onClick={onOpen}
        >
          <List className="h-3.5 w-3.5" />
        </Button>
      </div>

      {isExpanded ? (
        <div className="mt-1.5 border-t border-line/60 pt-1.5">
          {previewItems.length === 0 ? (
            <div className="rounded-[10px] border border-dashed border-line bg-parchment/70 px-2.5 py-1.5 text-xs text-muted">
              {getSectionEmptyText(section.id)}
            </div>
          ) : (
            <div className="grid gap-0.5">
              {previewItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={cn(
                    'group flex min-w-0 items-center gap-2 rounded-[8px] px-2 py-1 text-left transition hover:bg-parchment',
                    item.isRecent ? 'bg-accentSoft/30' : ''
                  )}
                  onClick={() => onOpenItem(item)}
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-stone/40 group-hover:bg-accent" />
                  <span className="min-w-0 flex-1 truncate text-xs leading-5 text-muted">
                    <span className="font-medium text-ink">{item.title === section.title ? '最新条目' : item.title}</span>
                    <span className="text-stone"> · </span>
                    {getItemBody(item)}
                  </span>
                </button>
              ))}
            </div>
          )}
          {section.items.length > previewItems.length ? (
            <button
              type="button"
              className="mt-1 w-full rounded-[8px] px-2.5 py-1 text-xs font-medium text-accent transition hover:bg-accentSoft/40"
              onClick={onOpen}
            >
              {`查看全部（${section.totalCount}）`}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
function RecentUpdatesCard({
  items,
  onOpenItem,
}: {
  items: Array<{ section: StateOverviewSection; item: StateOverviewItem }>;
  onOpenItem: (section: StateOverviewSection, item: StateOverviewItem) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const visibleItems = isExpanded ? items : items.slice(0, 3);
  const hiddenCount = Math.max(0, items.length - visibleItems.length);

  return (
    <div className="min-w-0 overflow-hidden rounded-[14px] border border-accent/15 bg-accentSoft/20 px-2.5 py-2">
      <div className="flex min-h-8 items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-ink">本轮更新</div>
          <div className="truncate text-[11px] text-muted">最近新增或改动，先看这里。</div>
        </div>
        <span className="grid h-7 min-w-7 place-items-center rounded-full bg-accentSoft px-2 text-xs font-semibold text-accent">
          {items.length}
        </span>
      </div>
      {items.length === 0 ? (
        <div className="mt-1.5 truncate rounded-[10px] border border-dashed border-accent/20 bg-ivory/75 px-2.5 py-1.5 text-xs text-muted">
          暂无最近更新。
        </div>
      ) : (
        <div className="mt-1.5 min-w-0 border-t border-accent/10 pt-1.5">
          <div className={cn('grid min-w-0 gap-0.5', isExpanded ? 'max-h-[148px] overflow-y-auto pr-1' : '')}>
            {visibleItems.map(({ section, item }) => {
              const artifactMeta = getArtifactMeta(item);
              return (
                <button
                  key={`${section.id}-${item.id}`}
                  type="button"
                  className="group grid min-w-0 grid-cols-[10px_minmax(0,1fr)_auto] items-center gap-2 rounded-[8px] px-1.5 py-1 text-left transition hover:bg-ivory/70"
                  onClick={() => onOpenItem(section, item)}
                >
                  <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_0_3px_rgba(37,99,235,0.12)]" />
                  <span className="min-w-0">
                    <span className="block truncate text-xs leading-5 text-ink">{item.title}</span>
                  </span>
                  <span className="shrink-0 text-[11px] text-muted">
                    {artifactMeta?.typeLabel ?? section.title}
                  </span>
                </button>
              );
            })}
          </div>
          {items.length > 3 ? (
            <button
              type="button"
              className="mt-1.5 w-full rounded-[10px] border border-accent/15 bg-ivory/70 px-2.5 py-1.5 text-xs font-medium text-accent transition hover:bg-ivory"
              onClick={() => setIsExpanded((open) => !open)}
            >
              {isExpanded ? '收起本轮更新' : `展开其余 ${hiddenCount} 条更新`}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function ArtifactStickyPanel({
  section,
  onOpen,
  onOpenItem,
  onOpenArtifact,
  onOpenDocument,
}: {
  section: StateOverviewSection | null;
  onOpen: () => void;
  onOpenItem: (item: StateOverviewItem) => void;
  onOpenArtifact: (artifact: ArtifactRecord) => void;
  onOpenDocument: (artifact: ArtifactRecord) => void;
}) {
  const items = section?.items.slice(0, 3) ?? [];

  return (
    <div className="shrink-0 border-t border-line/70 bg-ivory px-3 pb-3 pt-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-ink">交付物</div>
          <div className="text-[11px] text-muted">{section ? getSectionSummaryLine(section) : '文档稿、页面方案和交互稿。'}</div>
        </div>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" aria-label="查看全部交付物" onClick={onOpen}>
          查看全部
        </Button>
      </div>
      {items.length === 0 ? (
        <button
          type="button"
          className="w-full rounded-[14px] border border-dashed border-line bg-parchment/70 px-3 py-3 text-left text-sm text-muted"
          onClick={onOpen}
        >
          当前还没有交付物。
        </button>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {items.map((item) => {
            const artifactMeta = getArtifactMeta(item);
            return (
              <div
                key={item.id}
                role="button"
                tabIndex={0}
                className={cn(
                  'min-w-0 rounded-[14px] border bg-ivory px-2.5 py-2 text-left transition hover:border-accent/30 hover:bg-parchment',
                  item.status === 'failed' ? 'border-[#e9d4cf]' : 'border-line'
                )}
                onClick={() => onOpenItem(item)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onOpenItem(item);
                  }
                }}
              >
                <div className="truncate text-sm font-semibold text-ink">{artifactMeta?.typeLabel ?? item.title}</div>
                <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted">
                  <span
                    className={cn(
                      'h-1.5 w-1.5 rounded-full',
                      item.status === 'generated'
                        ? 'bg-[#e6efe5]0'
                        : item.status === 'failed'
                          ? 'bg-[#fbeeec]0'
                          : item.status === 'generating'
                            ? 'bg-blue-500'
                            : 'bg-[#f5ead2]0'
                    )}
                  />
                  <span className="truncate">{artifactMeta?.statusLabel ?? item.status}</span>
                </div>
                {item.status === 'generating' ? (
                  <div className="mt-2 h-1.5 rounded-full bg-sand">
                    <div className="h-full w-3/5 rounded-full bg-accent" />
                  </div>
                ) : null}
                <div className="mt-2">
                  <ArtifactInlineActions
                    item={item}
                    onOpenArtifact={onOpenArtifact}
                    onOpenDocument={onOpenDocument}
                    showPendingBadge={false}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
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
            <div className="flex min-h-0 flex-col border-r border-line bg-parchment/70">
              <DialogHeader className="border-b border-line px-5 py-4">
                <DialogTitle>{section.title}</DialogTitle>
                <DialogDescription>{section.description}</DialogDescription>
              </DialogHeader>
              <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
                <div className="grid gap-2">
                  {section.items.length === 0 ? (
                    <div className="rounded-[16px] border border-dashed border-borderCream bg-ivory p-3 text-sm text-muted">
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
                            : 'border-borderCream bg-ivory hover:border-accent/25 hover:bg-parchment'
                        )}
                        onClick={() => onSelectItem(item)}
                      >
                        {(() => {
                          const artifactMeta = getArtifactMeta(item);
                          return (
                        <div className="flex items-start justify-between gap-2">
                          <div className="text-sm font-semibold text-ink">{item.title}</div>
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            {artifactMeta ? <Badge variant="default">{artifactMeta.typeLabel}</Badge> : null}
                            {item.isRecent ? <Badge variant="accent">本轮新增</Badge> : null}
                          </div>
                        </div>
                          );
                        })()}
                        <p className="mt-1.5 line-clamp-2 text-sm leading-6 text-muted">{getItemBody(item)}</p>
                        {item.kind === 'artifact' ? (
                          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted">
                            <span>{getArtifactFormatLabel(item.artifactType ?? '', item.contentFormat)}</span>
                            <span>{getArtifactStatusLabel(item.status)}</span>
                          </div>
                        ) : null}
                      </button>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="flex min-h-0 flex-col bg-ivory">
              <div className="border-b border-line px-5 py-4">
                <div className="text-sm font-medium text-muted">条目详情</div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                {activeItem ? (
                  (() => {
                    const artifactMeta = getArtifactMeta(activeItem);

                    return (
                      <div className="space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-xl font-semibold text-ink">{activeItem.title}</h3>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {artifactMeta ? <Badge variant="default">{artifactMeta.displayLabel}</Badge> : null}
                          <Badge variant={statusVariant(activeItem.status)}>
                            {artifactMeta ? artifactMeta.statusLabel : activeItem.status}
                          </Badge>
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
                                revision_number: 1,
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
                                revision_number: 1,
                                updated_at: activeItem.updatedAt ?? '',
                              })
                            }
                          >
                            查看正文
                          </Button>
                        )
                      ) : null}
                    </div>

                    <div className="grid gap-3 rounded-[22px] border border-line bg-parchment/70 p-4 text-sm">
                      {activeItem.kind === 'artifact' ? (
                        <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-3">
                          <div className="font-medium text-muted">产物类型</div>
                          <div className="text-ink">{getArtifactDisplayLabel({
                            artifact_type: activeItem.artifactType ?? '',
                            content_format: activeItem.contentFormat ?? '',
                          })}</div>
                        </div>
                      ) : null}
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

                    <div className="rounded-[22px] border border-borderCream bg-ivory p-4">
                      <div className="mb-3 text-sm font-medium text-muted">正文</div>
                      <div className="whitespace-pre-wrap text-sm leading-7 text-ink">
                        {activeItem.kind === 'artifact' ? activeItem.body || '当前还没有摘要。' : activeItem.body}
                      </div>
                    </div>
                  </div>
                    );
                  })()
                ) : (
                  <div className="rounded-[20px] border border-dashed border-line bg-parchment p-4 text-sm leading-6 text-muted">
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
            <pre className="mb-3 overflow-x-auto rounded-2xl bg-warmDarker p-3 font-mono text-[0.92em] text-warmSilver last:mb-0">
              {children}
            </pre>
          ),
          code: ({ children }) => (
            <code className="rounded-[6px] bg-sand px-1.5 py-0.5 font-mono text-[0.92em] text-charcoal">
              {children}
            </code>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-terracotta underline decoration-terracotta/40 underline-offset-2"
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

function DocumentMarkdown({ content }: { content: string }) {
  return (
    <div className="markdown-body text-sm leading-7 text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="mb-3 mt-4 text-xl font-semibold text-ink first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-5 text-lg font-semibold text-ink first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-2 mt-4 text-base font-semibold text-ink first:mt-0">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="mb-2 mt-3 text-sm font-semibold text-ink first:mt-0">{children}</h4>
          ),
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          ul: ({ children }) => (
            <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
          ),
          li: ({ children }) => <li>{children}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold text-ink">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
          blockquote: ({ children }) => (
            <blockquote className="mb-3 border-l-2 border-borderWarm pl-3 text-muted last:mb-0">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-line" />,
          pre: ({ children }) => (
            <pre className="mb-3 overflow-x-auto rounded-2xl bg-warmDarker p-3 font-mono text-[0.92em] text-warmSilver last:mb-0">
              {children}
            </pre>
          ),
          code: ({ children }) => (
            <code className="rounded-[6px] bg-sand px-1.5 py-0.5 font-mono text-[0.92em] text-charcoal">
              {children}
            </code>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-terracotta underline decoration-terracotta/40 underline-offset-2"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="mb-3 overflow-x-auto last:mb-0">
              <table className="w-full border-collapse text-left text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-sand/60">{children}</thead>,
          th: ({ children }) => (
            <th className="border border-line px-3 py-2 font-semibold text-ink">{children}</th>
          ),
          td: ({ children }) => (
            <td className="border border-line px-3 py-2 align-top">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function ArtifactVersionSwitcher({
  projectId,
  artifact,
  onSelectRevision,
  onPromoted,
}: {
  projectId: string;
  artifact: ArtifactRecord;
  onSelectRevision: (next: ArtifactRecord) => void;
  onPromoted: (next: ArtifactRecord) => void;
}) {
  const [history, setHistory] = useState<ArtifactRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listArtifactHistory(projectId, artifact.artifact_type)
      .then((items) => {
        if (cancelled) return;
        setHistory(items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, artifact.artifact_type]);

  const sortedHistory = useMemo(
    () => [...history].sort((a, b) => b.revision_number - a.revision_number),
    [history]
  );
  const latestRevision = sortedHistory[0]?.revision_number ?? artifact.revision_number;
  const isLatest = artifact.revision_number === latestRevision;
  const canPromote = !isLatest && artifact.status === 'generated';

  const handleSelect = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const nextId = event.target.value;
    const next = history.find((item) => item.id === nextId);
    if (next) onSelectRevision(next);
  };

  const handlePromote = async () => {
    setPromoting(true);
    setError(null);
    try {
      const promoted = await promoteArtifact(projectId, artifact.id);
      onPromoted(promoted);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPromoting(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-parchment/40 px-6 py-3 text-xs">
      <History className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
      <span className="text-muted">版本</span>
      <select
        value={artifact.id}
        onChange={handleSelect}
        disabled={loading || sortedHistory.length === 0}
        className="rounded-md border border-line bg-ivory px-2 py-1 text-xs text-ink disabled:cursor-not-allowed"
      >
        {sortedHistory.length === 0 ? (
          <option value={artifact.id}>v{artifact.revision_number}（当前）</option>
        ) : (
          sortedHistory.map((item) => (
            <option key={item.id} value={item.id}>
              {`v${item.revision_number} · ${getArtifactStatusLabel(item.status)}${
                item.updated_at ? ` · ${compactRelativeTime(item.updated_at)}` : ''
              }`}
            </option>
          ))
        )}
      </select>
      {loading ? <span className="text-muted">加载历史中…</span> : null}
      {!isLatest ? (
        <span className="rounded-full border border-[#e6cfbf] bg-[#f4e3d2] px-2 py-0.5 text-[#7a4520]">
          查看历史版本（只读）
        </span>
      ) : null}
      {canPromote ? (
        <Button
          variant="secondary"
          size="sm"
          className="ml-auto h-7 px-2 text-xs"
          onClick={handlePromote}
          disabled={promoting}
        >
          {promoting ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <RotateCcw className="mr-1 h-3 w-3" />}
          设为当前最新
        </Button>
      ) : null}
      {error ? <span className="ml-auto text-[#a94422]">{error}</span> : null}
    </div>
  );
}

function actionEventTone(kind: MessageActionEvent['kind']) {
  if (kind === 'artifact') {
    return 'border-[#e6cfbf] bg-[#f4e3d2] text-[#7a4520]';
  }
  if (kind === 'version') {
    return 'border-[#dfd4e0] bg-[#ebe4ec] text-[#5e4a6b]';
  }
  if (kind === 'state') {
    return 'border-[#cdded0] bg-[#e6efe5] text-[#3d6b50]';
  }
  if (kind === 'tool_running') {
    return 'border-[#e6d3b3] bg-[#f5ead2] text-[#7a5a1d]';
  }
  if (kind === 'tool_completed') {
    return 'border-borderWarm bg-sand text-charcoal';
  }
  return 'border-line bg-ivory/85 text-muted';
}

export function WorkbenchPage({
  project,
  readiness,
  sources,
  messages,
  state,
  artifacts,
  recentInsightIds,
  notices,
  sending,
  uploading,
  deletingSourceId,
  retryingSourceId,
  initializingKnowledgeBase,
  onSendMessage,
  onUploadTextSource,
  onUploadFileSource,
  onDeleteSource,
  onReindexSource,
  onRequestSourceContent,
  onInitializeKnowledgeBase,
  onArtifactsChanged,
}: WorkbenchPageProps) {
  const refreshArtifacts = async () => {
    if (!onArtifactsChanged) return;
    try {
      const updated = await listArtifacts(project.id);
      onArtifactsChanged(updated);
    } catch {
      // 静默：刷新失败不阻断 dialog 中的版本切换体验。
    }
  };
  const [composer, setComposer] = useState('');
  const [isImportDialogOpen, setIsImportDialogOpen] = useState(false);
  const [isRuntimeDialogOpen, setIsRuntimeDialogOpen] = useState(false);
  const [sourceName, setSourceName] = useState('访谈纪要');
  const [sourceText, setSourceText] = useState('');
  const [selectedSource, setSelectedSource] = useState<SourceRecord | null>(null);
  const [selectedSourceContent, setSelectedSourceContent] = useState<SourceContentRecord | null>(null);
  const [selectedSourceContentError, setSelectedSourceContentError] = useState<string | null>(null);
  const [loadingSourceContent, setLoadingSourceContent] = useState(false);
  const [sourcePreviewPosition, setSourcePreviewPosition] = useState({ top: 120, left: 120 });
  const [activeArtifact, setActiveArtifact] = useState<ArtifactRecord | null>(null);
  const [activeDocument, setActiveDocument] = useState<ArtifactRecord | null>(null);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [activeSectionItemId, setActiveSectionItemId] = useState<string | null>(null);
  const [expandedCoreSectionId, setExpandedCoreSectionId] = useState<string | null>('pending_items');
  const [activeUploadKind, setActiveUploadKind] = useState<'text' | 'file' | null>(null);
  const [pendingChatImages, setPendingChatImages] = useState<PendingChatImage[]>([]);
  const pendingChatImagesRef = useRef<PendingChatImage[]>([]);
  const sourceInputRef = useRef<HTMLInputElement | null>(null);
  const chatImageInputRef = useRef<HTMLInputElement | null>(null);
  const chatBottomRef = useRef<HTMLDivElement | null>(null);
  const sourcePreviewRequestRef = useRef(0);
  const lastMessageContent = messages[messages.length - 1]?.content ?? '';
  const lastMessageActionCount = messages[messages.length - 1]?.action_events?.length ?? 0;
  const lastMessageStatus = messages[messages.length - 1]?.status_label ?? '';

  const stageState = useMemo(
    () => deriveStageState(state, recentInsightIds),
    [recentInsightIds, state]
  );
  const overviewSections = useMemo(
    () => deriveStateOverviewSections(state, artifacts, recentInsightIds),
    [artifacts, recentInsightIds, state]
  );
  const artifactSection = useMemo(
    () => overviewSections.find((section) => section.id === 'artifacts') ?? null,
    [overviewSections]
  );
  const coreOverviewSections = useMemo(
    () => overviewSections.filter((section) => section.id !== 'artifacts' && section.id !== 'versions'),
    [overviewSections]
  );
  const activeSection = useMemo(
    () => overviewSections.find((section) => section.id === activeSectionId) ?? null,
    [activeSectionId, overviewSections]
  );
  const activeSectionItem = useMemo(
    () => activeSection?.items.find((item) => item.id === activeSectionItemId) ?? null,
    [activeSection, activeSectionItemId]
  );
  const recentOverviewItems = useMemo(() => getRecentOverviewItems(overviewSections), [overviewSections]);
  const referencedSourceCount = sources.filter(
    (source) => sourceIndexStatus(source).includes('indexed') || sourceIndexStatus(source).includes('ready')
  ).length;
  const pendingSourceCount = sources.filter(
    (source) => {
      const normalizeStatus = sourceNormalizeStatus(source);
      const indexStatus = sourceIndexStatus(source);

      return (
        normalizeStatus === 'processing' ||
        normalizeStatus.includes('pending') ||
        normalizeStatus.includes('queued') ||
        indexStatus === 'indexing' ||
        indexStatus.includes('pending') ||
        indexStatus.includes('queued')
      );
    }
  ).length;
  const totalInsightCount =
    state.current_understanding.length +
    state.pending_items.length +
    state.confirmed_items.length +
    state.conflict_items.length +
    state.mvp_items.length;
  const isUploadingSource = uploading || activeUploadKind !== null;
  const isUploadingTextSource = activeUploadKind === 'text';
  const isUploadingFileSource = activeUploadKind === 'file';

  useEffect(() => {
    const scrollTarget = chatBottomRef.current;
    if (scrollTarget && typeof scrollTarget.scrollIntoView === 'function') {
      scrollTarget.scrollIntoView({ block: 'end' });
    }
  }, [lastMessageActionCount, lastMessageContent, lastMessageStatus, messages.length, notices.length, sending]);

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

  function closeSourcePreview() {
    sourcePreviewRequestRef.current += 1;
    setSelectedSource(null);
    setSelectedSourceContent(null);
    setSelectedSourceContentError(null);
    setLoadingSourceContent(false);
  }

  async function openSourcePreview(source: SourceRecord, rect: DOMRect) {
    const requestId = sourcePreviewRequestRef.current + 1;
    sourcePreviewRequestRef.current = requestId;
    setSourcePreviewPosition({
      top: Math.min(rect.top, window.innerHeight - 300),
      left: Math.min(rect.right + 12, window.innerWidth - 440),
    });
    setSelectedSource(source);
    setSelectedSourceContent(null);
    setSelectedSourceContentError(null);
    setLoadingSourceContent(true);

    try {
      const contentRecord = await onRequestSourceContent(source.id);
      if (sourcePreviewRequestRef.current !== requestId) {
        return;
      }
      setSelectedSourceContent(contentRecord);
    } catch (error) {
      if (sourcePreviewRequestRef.current !== requestId) {
        return;
      }
      setSelectedSourceContentError(error instanceof Error ? error.message : '资料正文加载失败。');
    } finally {
      if (sourcePreviewRequestRef.current === requestId) {
        setLoadingSourceContent(false);
      }
    }
  }

  useEffect(() => {
    pendingChatImagesRef.current = pendingChatImages;
  }, [pendingChatImages]);

  useEffect(
    () => () => {
      pendingChatImagesRef.current.forEach((image) => {
        if (image.previewUrl.startsWith('blob:')) {
          URL.revokeObjectURL(image.previewUrl);
        }
      });
    },
    []
  );

  async function handleSend() {
    const trimmed = composer.trim() || (pendingChatImages.length > 0 ? '请结合我上传的图片继续分析。' : '');
    if (!trimmed) return;
    const imageAttachments = pendingChatImages.map(({ id: _id, previewUrl: _previewUrl, ...attachment }) => attachment);
    pendingChatImages.forEach((image) => {
      if (image.previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(image.previewUrl);
      }
    });
    setPendingChatImages([]);
    setComposer('');
    await onSendMessage(trimmed, imageAttachments);
  }

  async function readChatImageFile(file: File): Promise<PendingChatImage> {
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error ?? new Error('图片读取失败。'));
      reader.readAsDataURL(file);
    });
    return {
      id: `chat-image-${Date.now()}-${file.name}`,
      name: file.name,
      content_type: file.type || 'image/png',
      data_url: dataUrl,
      previewUrl: typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : dataUrl,
    };
  }

  async function handleSelectChatImages(files: File[]) {
    const imageFiles = files
      .filter((file) => file.type.startsWith('image/'))
      .filter((file) => {
        if (file.size > 5 * 1024 * 1024) {
          console.warn(`图片 ${file.name || '(未命名)'} 超过 5MB，已忽略。`);
          return false;
        }
        return true;
      })
      .slice(0, 4);
    if (imageFiles.length === 0) return;
    const nextImages = await Promise.all(imageFiles.map((file) => readChatImageFile(file)));
    setPendingChatImages((current) => {
      const merged = [...current, ...nextImages].slice(0, 4);
      const dropped = [...current, ...nextImages].slice(4);
      dropped.forEach((image) => {
        if (image.previewUrl.startsWith('blob:')) {
          URL.revokeObjectURL(image.previewUrl);
        }
      });
      return merged;
    });
  }

  async function handleComposerPaste(event: ReactClipboardEvent<HTMLTextAreaElement>) {
    const items = event.clipboardData?.items;
    if (!items) return;
    const imageFiles: File[] = [];
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) imageFiles.push(file);
      }
    }
    if (imageFiles.length === 0) return;
    if (sending) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    await handleSelectChatImages(imageFiles);
  }

  function removePendingChatImage(imageId: string) {
    setPendingChatImages((current) => {
      const removed = current.find((image) => image.id === imageId);
      if (removed?.previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return current.filter((image) => image.id !== imageId);
    });
  }

  async function handleUploadText() {
    const name = sourceName.trim();
    const text = sourceText.trim();
    if (!name || !text) return;
    setActiveUploadKind('text');
    try {
      await onUploadTextSource({ name, text });
      setSourceText('');
      setSourceName('访谈纪要');
      setIsImportDialogOpen(false);
    } finally {
      setActiveUploadKind(null);
    }
  }

  async function handleUploadFiles(files: File[]) {
    if (files.length === 0) return;
    setActiveUploadKind('file');
    try {
      await onUploadFileSource(files);
    } finally {
      setActiveUploadKind(null);
    }
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
    <main className="h-screen overflow-hidden px-3 pb-3 pt-3 text-nearBlack md:px-4">
      <div className="mx-auto flex h-full max-w-[1700px] flex-col gap-3">
        <Card className="shrink-0 border-borderCream bg-ivory">
          <CardContent className="relative flex items-center justify-between gap-4 p-3">
            <div className="z-10 flex min-w-0 max-w-[36%] items-center gap-2.5">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-accent text-white shadow-sm">
                <Sparkles className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <h1 className="truncate text-xl font-semibold tracking-tight">{project.name}</h1>
                <div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-muted">
                  <span className="truncate">{project.scenario_type}</span>
                  <span className="h-1 w-1 rounded-full bg-stone/40" />
                  <span className="truncate">{project.status}</span>
                </div>
              </div>
            </div>

            <div className="pointer-events-none absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 justify-center">
              <WorkbenchStageRail
                primaryStage={stageState.primaryStage}
                revisitingStages={stageState.revisitingStages}
              />
            </div>

            <div className="z-10 flex shrink-0 items-center gap-2">
              <Button variant="secondary" size="sm" className="h-9" asChild>
                <Link to="/">
                  <FolderKanban className="mr-1.5 h-4 w-4" />
                  项目列表
                </Link>
              </Button>
              <RuntimeStatusButton
                readiness={readiness}
                initializingKnowledgeBase={initializingKnowledgeBase}
                onClick={() => setIsRuntimeDialogOpen(true)}
              />
            </div>
          </CardContent>
        </Card>

        <section className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_360px] gap-3">
          <Card className="relative flex min-h-0 flex-col overflow-hidden border-borderCream bg-ivory">
            <CardHeader className="shrink-0 p-3 pb-2.5">
              <div className="flex items-center justify-between gap-3">
                <CardTitle className="text-base">项目资料</CardTitle>
                <div className="text-xs text-muted">{`${sources.length} 份 · ${referencedSourceCount} 已索引 · ${pendingSourceCount} 待处理`}</div>
              </div>
            </CardHeader>
            <CardContent
              data-testid="sources-panel-content"
              className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-hidden px-3 pb-3 pt-0"
            >
              <div className="flex gap-2 rounded-[16px] border border-line bg-parchment/70 p-2">
                <Button
                  variant="subtle"
                  size="sm"
                  className="min-w-0 flex-1 whitespace-nowrap px-2.5"
                  onClick={() => setIsImportDialogOpen(true)}
                  disabled={isUploadingSource}
                >
                  <Upload className="mr-1.5 h-4 w-4 shrink-0" />
                  导入文本资料
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  className="min-w-0 flex-1 whitespace-nowrap px-2.5"
                  onClick={() => sourceInputRef.current?.click()}
                  disabled={isUploadingSource}
                >
                  {isUploadingFileSource ? (
                    <Loader2 className="mr-1.5 h-4 w-4 shrink-0 animate-spin" />
                  ) : (
                    <Upload className="mr-1.5 h-4 w-4 shrink-0" />
                  )}
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
                      await handleUploadFiles(files);
                      event.target.value = '';
                    }
                  }}
                />
              </div>

              <div data-testid="sources-scroll-area" className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-1">
                <div className="grid gap-2">
                  {sources.map((source) => (
                    <SourceFileRow
                      key={source.id}
                      source={source}
                      deletingSourceId={deletingSourceId}
                      retryingSourceId={retryingSourceId}
                      onPreview={openSourcePreview}
                      onDeleteSource={onDeleteSource}
                      onReindexSource={onReindexSource}
                    />
                  ))}
                  {sources.length === 0 ? (
                    <div className="rounded-[16px] border border-dashed border-line bg-ivory/85 p-4 text-sm leading-6 text-muted">
                      先导入访谈、需求原话或业务说明，项目资料会在这里形成可检索来源。
                    </div>
                  ) : null}
                </div>
              </div>

              <button
                type="button"
                className="shrink-0 rounded-[16px] border border-dashed border-line bg-ivory/75 px-3 py-2.5 text-center text-xs leading-5 text-muted transition hover:border-accent/30 hover:bg-parchment"
                onClick={() => sourceInputRef.current?.click()}
                disabled={isUploadingSource}
              >
                {isUploadingFileSource ? (
                  <Loader2 className="mx-auto mb-1 h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="mx-auto mb-1 h-4 w-4" />
                )}
                {isUploadingFileSource ? '文件上传中...' : '拖拽文件到此处，或点击上传'}
              </button>
            </CardContent>
          </Card>

          <Card className="flex min-h-0 flex-col overflow-hidden border-borderCream bg-ivory">
            <CardHeader className="shrink-0 border-b border-line/70 px-3 py-2.5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-base">需求分析对话</CardTitle>
                    <span className="flex items-center gap-1 text-xs text-[#3d6b50]">
                      <span className="h-1.5 w-1.5 rounded-full bg-[#e6efe5]0" />
                      AI 在线
                    </span>
                  </div>
                  <div className="text-xs text-muted">{`${messages.length} 轮消息 · 已引用 ${referencedSourceCount} 份资料 · ${totalInsightCount} 条沉淀`}</div>
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
                      data-testid={`chat-message-${message.id}`}
                      className={cn(
                        'flex gap-3',
                        message.role === 'user' ? 'justify-end' : 'justify-start'
                      )}
                    >
                      <div
                        className={cn(
                          'max-w-[78%] rounded-[22px] px-4 py-3.5 shadow-sm',
                          message.role === 'user'
                            ? 'bg-accentSoft text-nearBlack shadow-[0_0_0_1px_rgba(201,100,66,0.18)]'
                            : message.role === 'assistant'
                              ? 'border border-borderCream bg-ivory text-nearBlack'
                              : 'border border-[#e6d3b3] bg-[#f5ead2] text-[#7a5a1d]'
                        )}
                      >
                        <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.16em] opacity-80">
                          {message.role === 'assistant' ? <Bot className="h-3.5 w-3.5" /> : null}
                          {message.role === 'assistant' ? 'AI 助手' : message.role === 'user' ? '你' : message.role}
                        </div>
                        {message.role === 'assistant' && message.status_label ? (
                          <div className="mb-2.5 flex items-center gap-2 rounded-[14px] border border-line/80 bg-ivory/75 px-3 py-2 text-xs font-medium text-muted">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            <span>{message.status_label}</span>
                          </div>
                        ) : null}
                        {message.role === 'assistant' && (message.action_events?.length ?? 0) > 0 ? (
                          <div className="mb-2.5 rounded-[16px] border border-line/80 bg-ivory/80 px-3 py-2.5">
                            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
                              系统行动
                            </div>
                            <div className="mt-2 flex flex-col gap-2">
                              {message.action_events?.map((action) => (
                                <div
                                  key={action.id}
                                  className={cn(
                                    'flex items-start gap-2 rounded-[12px] border px-2.5 py-2 text-xs leading-5',
                                    actionEventTone(action.kind)
                                  )}
                                >
                                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                                  <span>{action.label}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        <MessageMarkdown content={message.content} />
                        {(message.image_results?.length ?? 0) > 0 ? (
                          <div className="mt-3 grid gap-3">
                            {message.image_results?.map((image) => (
                              <figure
                                key={image.id}
                                className="overflow-hidden rounded-[14px] border border-borderCream bg-ivory shadow-whisper"
                              >
                                <img
                                  src={image.url}
                                  alt={image.title}
                                  className="max-h-[420px] w-full object-contain bg-parchment"
                                />
                                <figcaption className="border-t border-line px-3 py-2 text-xs text-muted">
                                  <span className="font-medium text-ink">{image.title}</span>
                                  {image.summary ? <span className="ml-2">{image.summary}</span> : null}
                                </figcaption>
                              </figure>
                            ))}
                          </div>
                        ) : null}
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
                      className="rounded-[20px] border border-[#e6d3b3] bg-[#f5ead2] px-4 py-3 text-sm text-[#7a5a1d]"
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
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" size="sm" onClick={() => setComposer('请总结当前理解，并指出已经明确的目标、范围和约束。')}>
                      <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                      总结当前理解
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setComposer('请列出进入页面方案前还需要确认的问题，并按优先级排序。')}>
                      <span className="mr-1.5 text-accent">?</span>
                      列待确认问题
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => setComposer('请基于当前沉淀生成页面方案，说明页面结构、关键模块和交互入口。')}>
                      <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                      生成页面方案
                    </Button>
                  </div>
                  <div className="relative">
                    {pendingChatImages.length > 0 ? (
                      <div className="mb-2 flex flex-wrap gap-2 rounded-[16px] border border-line bg-ivory/85 p-2">
                        {pendingChatImages.map((image) => (
                          <div
                            key={image.id}
                            className="group relative flex items-center gap-2 rounded-[12px] border border-line bg-parchment px-2 py-1.5"
                          >
                            <img
                              src={image.previewUrl}
                              alt={image.name}
                              className="h-9 w-9 rounded-[10px] object-cover"
                            />
                            <div className="max-w-[132px]">
                              <div className="truncate text-xs font-medium text-ink">{image.name}</div>
                              <div className="text-[11px] text-muted">聊天图片</div>
                            </div>
                            <button
                              type="button"
                              aria-label={`移除图片 ${image.name}`}
                              className="grid h-6 w-6 place-items-center rounded-full text-muted transition hover:bg-ivory hover:text-errorWarm"
                              onClick={() => removePendingChatImage(image.id)}
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    <Textarea
                      id="chat-composer"
                      name="chat-composer"
                      value={composer}
                      onChange={(event) => setComposer(event.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      onPaste={handleComposerPaste}
                      placeholder="继续补充业务背景、目标或限制条件，可直接粘贴截图..."
                      className="min-h-[76px] pr-16"
                    />
                    <div className="absolute bottom-3 right-3 flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted hover:text-terracotta"
                        aria-label="添加图片"
                        onClick={() => chatImageInputRef.current?.click()}
                      >
                        <Paperclip className="h-4 w-4" />
                      </Button>
                      <input
                        ref={chatImageInputRef}
                        type="file"
                        accept="image/*"
                        multiple
                        className="hidden"
                        onChange={async (event) => {
                          const files = Array.from(event.target.files ?? []);
                          if (files.length > 0) {
                            await handleSelectChatImages(files);
                          }
                          event.target.value = '';
                        }}
                      />
                      <Button
                        onClick={handleSend}
                        disabled={sending || (!composer.trim() && pendingChatImages.length === 0)}
                        className="h-9 w-9 p-0"
                        aria-label="继续分析"
                      >
                        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="flex min-h-0 flex-col overflow-hidden border-borderCream bg-ivory">
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
            <CardContent className="flex min-h-0 flex-1 flex-col overflow-hidden px-0 pb-0 pt-0">
              <div className="shrink-0 px-3 pb-2">
                <RecentUpdatesCard
                  items={recentOverviewItems}
                  onOpenItem={(section, item) => {
                    setActiveSectionId(section.id);
                    setActiveSectionItemId(item.id);
                  }}
                />
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 pb-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-ink">核心沉淀</div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setActiveSectionId(coreOverviewSections[0]?.id ?? null)}
                  >
                    查看全部
                  </Button>
                </div>
                <div className="grid gap-1.5">
                  {coreOverviewSections.map((section) => (
                    <StateSectionCard
                      key={section.id}
                      section={section}
                      isExpanded={expandedCoreSectionId === section.id}
                      onToggle={() => setExpandedCoreSectionId((current) => (current === section.id ? null : section.id))}
                      onOpen={() => setActiveSectionId(section.id)}
                      onOpenItem={(item) => {
                        setActiveSectionId(section.id);
                        setActiveSectionItemId(item.id);
                      }}
                    />
                  ))}
                </div>
              </div>

              <ArtifactStickyPanel
                section={artifactSection}
                onOpen={() => setActiveSectionId('artifacts')}
                onOpenItem={(item) => {
                  setActiveSectionId('artifacts');
                  setActiveSectionItemId(item.id);
                }}
                onOpenArtifact={setActiveArtifact}
                onOpenDocument={setActiveDocument}
              />
            </CardContent>
          </Card>
        </section>
      </div>

      {selectedSource ? (
        <SourcePreview
          source={selectedSource}
          position={sourcePreviewPosition}
          contentRecord={selectedSourceContent}
          loading={loadingSourceContent}
          error={selectedSourceContentError}
          onClose={closeSourcePreview}
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
                <DialogTitle>
                  {activeArtifact.title}
                  <span className="ml-2 text-xs font-normal text-muted">
                    v{activeArtifact.revision_number}
                  </span>
                </DialogTitle>
                <DialogDescription>
                  {`${getArtifactDisplayLabel(activeArtifact)} · ${activeArtifact.summary}`}
                </DialogDescription>
              </DialogHeader>
              <ArtifactVersionSwitcher
                projectId={project.id}
                artifact={activeArtifact}
                onSelectRevision={setActiveArtifact}
                onPromoted={(next) => {
                  setActiveArtifact(next);
                  void refreshArtifacts();
                }}
              />
              <div className="min-h-0 flex-1 bg-sand">
                {activeArtifact.preview_url && activeArtifact.content_format === 'image' ? (
                  <div className="flex h-full items-center justify-center bg-sand p-6">
                    <img
                      src={activeArtifact.preview_url}
                      alt={activeArtifact.title}
                      className="max-h-full max-w-full rounded-[20px] object-contain shadow-panel"
                    />
                  </div>
                ) : activeArtifact.preview_url ? (
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
          <DialogContent className="left-auto right-4 top-4 flex h-[calc(100vh-2rem)] w-[520px] max-w-none translate-x-0 translate-y-0 flex-col gap-0 p-0 data-[state=open]:animate-none">
            <div className="flex min-h-0 flex-1 flex-col">
              <DialogHeader className="border-b border-line px-6 py-5">
                <DialogTitle>
                  {activeDocument.title}
                  <span className="ml-2 text-xs font-normal text-muted">
                    v{activeDocument.revision_number}
                  </span>
                </DialogTitle>
                <DialogDescription>
                  {`${getArtifactDisplayLabel(activeDocument)} · ${activeDocument.summary}`}
                </DialogDescription>
              </DialogHeader>
              <ArtifactVersionSwitcher
                projectId={project.id}
                artifact={activeDocument}
                onSelectRevision={setActiveDocument}
                onPromoted={(next) => {
                  setActiveDocument(next);
                  void refreshArtifacts();
                }}
              />
              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
                {activeDocument.body ? (
                  activeDocument.content_format === 'markdown' ? (
                    <DocumentMarkdown content={activeDocument.body} />
                  ) : (
                    <pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-muted">
                      {activeDocument.body}
                    </pre>
                  )
                ) : (
                  <div className="text-sm leading-7 text-muted">当前文档还没有正文。</div>
                )}
              </div>
            </div>
          </DialogContent>
        ) : null}
      </Dialog>

      <Dialog open={isRuntimeDialogOpen} onOpenChange={setIsRuntimeDialogOpen}>
        <DialogContent className="w-[min(640px,92vw)]">
          <DialogHeader>
            <DialogTitle>运行状态</DialogTitle>
            <DialogDescription>这里放运行链路和项目知识库状态，不占用知识库主区域。</DialogDescription>
          </DialogHeader>
          {readiness ? (
            <div className="grid gap-4 py-2">
              <RuntimeProviderCard
                title="Claude Agent SDK"
                summary={readiness.claude.summary}
                detail={readiness.claude.detail}
                status={readiness.claude.status}
              />

              <div className="rounded-[20px] border border-line bg-parchment/70 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium text-ink">项目知识库</div>
                    <p className="mt-1 text-sm leading-6 text-muted">{readiness.evidence?.summary ?? '项目知识库状态未返回。'}</p>
                    {readiness.evidence?.detail ? (
                      <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">
                        {readiness.evidence?.detail}
                      </p>
                    ) : null}
                  </div>
                  <Badge variant={readinessVariant(readiness.evidence?.status ?? 'unknown')}>{readiness.evidence?.status ?? 'unknown'}</Badge>
                </div>
                <div className="mt-4 flex flex-wrap gap-3">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setIsRuntimeDialogOpen(false);
                      void onInitializeKnowledgeBase();
                    }}
                    disabled={initializingKnowledgeBase}
                  >
                    {initializingKnowledgeBase ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    初始化项目知识库
                  </Button>
                </div>
              </div>

              {readiness.object_storage ? (
                <RuntimeProviderCard
                  title="七牛对象存储"
                  summary={readiness.object_storage.summary}
                  detail={readiness.object_storage.detail}
                  status={readiness.object_storage.status}
                />
              ) : null}

              {readiness.audio_transcription ? (
                <RuntimeProviderCard
                  title="阿里云音频转写"
                  summary={readiness.audio_transcription.summary}
                  detail={readiness.audio_transcription.detail}
                  status={readiness.audio_transcription.status}
                />
              ) : null}

              {readiness.wiki ? (
                <div className="rounded-[20px] border border-line bg-parchment/70 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-ink">LLM Wiki 综合层</div>
                      <p className="mt-1 text-sm leading-6 text-muted">{readiness.wiki.summary}</p>
                      {readiness.wiki.detail ? (
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-muted">
                          {readiness.wiki.detail}
                        </p>
                      ) : null}
                      <p className="mt-2 text-xs leading-5 text-muted">
                        wiki 是综合理解层，不是 citation 来源；引用仍以项目知识库 RAG 为准。
                      </p>
                    </div>
                    <Badge variant={readinessVariant(readiness.wiki.status)}>{readiness.wiki.status}</Badge>
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
              <Button onClick={handleUploadText} disabled={isUploadingSource || !sourceName.trim() || !sourceText.trim()}>
                {isUploadingTextSource ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                导入文本资料
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>


    </main>
  );
}
