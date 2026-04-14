import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';
import {
  actions,
  artifactRecords,
  chatTurns,
  insightRecords,
  knowledgeFiles,
  project,
  progressionStages,
  stageLabel,
  stageLabels,
  type ArtifactRecord,
  type ChatTurn,
  type InsightCategory,
  type InsightRecord,
  type KnowledgeFile
} from './demoData';

export default function App() {
  return (
    <BrowserRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/project/:projectId/workbench" element={<WorkbenchPage />} />
        <Route path="/project/:projectId/overview" element={<Navigate to="/project/reconciliation/workbench" replace />} />
        <Route path="/project/:projectId/export" element={<Navigate to="/project/reconciliation/workbench" replace />} />
        <Route path="/project/:projectId/stage/:stageId" element={<Navigate to="/project/reconciliation/workbench" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

const KNOWLEDGE_PREVIEW_WIDTH = 360;
const KNOWLEDGE_PREVIEW_HEIGHT = 320;
const KNOWLEDGE_PREVIEW_OFFSET = 12;
const KNOWLEDGE_PREVIEW_GAP = 16;
const COMPACT_LAYOUT_BREAKPOINT = 1360;

type KnowledgePreviewPlacement = 'right' | 'bottom';

function getKnowledgePreviewPosition(anchorRect: Pick<DOMRect, 'top' | 'right'>) {
  const maxLeft =
    window.innerWidth - KNOWLEDGE_PREVIEW_WIDTH - KNOWLEDGE_PREVIEW_GAP;
  const maxTop =
    window.innerHeight - KNOWLEDGE_PREVIEW_HEIGHT - KNOWLEDGE_PREVIEW_GAP;

  return {
    left: Math.round(
      Math.max(
        KNOWLEDGE_PREVIEW_GAP,
        Math.min(anchorRect.right + KNOWLEDGE_PREVIEW_OFFSET, maxLeft)
      )
    ),
    top: Math.round(
      Math.max(KNOWLEDGE_PREVIEW_GAP, Math.min(anchorRect.top, maxTop))
    )
  };
}

function KnowledgePreviewDialog({
  selectedFile,
  previewPlacement,
  previewStyle,
  referencedFileIds,
  upcomingFileIds,
  onClosePreview
}: {
  selectedFile: KnowledgeFile;
  previewPlacement: KnowledgePreviewPlacement;
  previewStyle: CSSProperties;
  referencedFileIds: string[];
  upcomingFileIds: string[];
  onClosePreview: () => void;
}) {
  const previewScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (previewScrollRef.current) {
      previewScrollRef.current.scrollTop = 0;
    }
  }, [selectedFile.id]);

  return createPortal(
    <aside
      className={[
        'knowledge-preview-float',
        previewPlacement === 'right'
          ? 'knowledge-preview-float-right'
          : 'knowledge-preview-float-bottom'
      ].join(' ')}
      role="dialog"
      aria-label={`文件摘要：${selectedFile.name}`}
      style={previewStyle}
    >
      <div
        ref={previewScrollRef}
        className="preview-card preview-card-floating preview-card-solid preview-card-framed"
        style={{ overflowY: 'auto' }}
      >
        <div className="panel-header preview-floating-header">
          <div>
            <div className="eyebrow">File Preview</div>
            <h3>文件摘要</h3>
          </div>
          <button
            type="button"
            className="secondary-button preview-close"
            onClick={onClosePreview}
          >
            关闭
          </button>
        </div>
        <div className="preview-card-body">
          <strong>{`当前查看：${selectedFile.name}`}</strong>
          <p>{selectedFile.summary}</p>
          <div className="tag-row">
            {selectedFile.tags.map((tag) => (
              <span key={tag} className="tag-chip subtle-chip">
                {tag}
              </span>
            ))}
          </div>
          <div className="preview-block">
            <span className="preview-label">关键摘录</span>
            <p>{selectedFile.excerpt}</p>
          </div>
          <div className="preview-block">
            <span className="preview-label">引用状态</span>
            <p>
              {referencedFileIds.includes(selectedFile.id)
                ? '本轮对话已经引用这份资料，聊天区和沉淀区都在用它支撑当前判断。'
                : upcomingFileIds.includes(selectedFile.id)
                  ? '这份资料会在下一轮分析里被重点引用，用来推进口径确认或方案定义。'
                  : '这份资料已入库，但当前轮次还没有成为主要判断依据。'}
            </p>
          </div>
        </div>
      </div>
    </aside>,
    document.body
  );
}

function HomePage() {
  return (
    <div className="app-shell">
      <header className="global-bar">
        <div>
          <div className="eyebrow">Internal Demo</div>
          <strong>{project.name}</strong>
        </div>
        <div className="bar-pills">
          <span className="pill">{project.industry}</span>
          <span className="pill">{project.primaryUser}</span>
          <span className="pill pill-strong">{project.status}</span>
        </div>
      </header>

      <section className="landing-card">
        <div className="eyebrow">Requirement Workbench</div>
        <h1>客户需求转译台</h1>
        <p className="hero-copy">
          这次 demo 不再靠分阶段翻页，而是直接进入单工作台，展示 AI 如何一边聊天、一边引用知识库、一边把业财逐笔对账需求沉淀成执行稿。
        </p>

        <div className="landing-actions">
          <Link className="primary-link" to="/project/reconciliation/workbench">
            进入案例工作台
          </Link>
        </div>
      </section>
    </div>
  );
}

function WorkbenchPage() {
  const [progressStep, setProgressStep] = useState(0);
  const [selectedFileId, setSelectedFileId] = useState(knowledgeFiles[0].id);
  const [isKnowledgePreviewOpen, setIsKnowledgePreviewOpen] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState<InsightCategory[]>([]);
  const [detailItem, setDetailItem] = useState<DetailItem | null>(null);

  const visibleTurns = useMemo(
    () => chatTurns.filter((turn) => turn.unlockAt <= progressStep),
    [progressStep]
  );
  const currentStageId = progressionStages[progressStep] ?? progressionStages[0];
  const currentStageIndex = stageLabels.findIndex((stage) => stage.id === currentStageId);
  const selectedFile =
    knowledgeFiles.find((file) => file.id === selectedFileId) ?? knowledgeFiles[0];
  const visibleInsights = insightRecords.filter((record) => record.unlockAt <= progressStep);
  const visibleArtifacts = artifactRecords.filter((record) => record.unlockAt <= progressStep);
  const nextAction = actions[progressStep] ?? null;
  const referencedFileIds = Array.from(
    new Set(visibleTurns.flatMap((turn) => turn.references ?? []))
  );
  const upcomingFileIds = Array.from(
    new Set(
      chatTurns
        .filter((turn) => turn.unlockAt === progressStep + 1)
        .flatMap((turn) => turn.references ?? [])
    )
  );

  return (
    <div className="app-shell workbench-shell workbench-shell-fixed" data-testid="workbench-shell">
      <header className="global-bar">
        <div>
          <div className="eyebrow">Notebook-style Demo</div>
          <strong>{project.name}</strong>
        </div>
        <div className="bar-pills">
          <span className="pill">{project.industry}</span>
          <span className="pill">{project.primaryUser}</span>
          <span className="pill pill-strong">{`当前阶段：${stageLabel(currentStageId)}`}</span>
        </div>
      </header>

      <section className="stage-strip stage-strip-sticky" aria-label="阶段进度" data-testid="stage-strip">
        {stageLabels.map((stage, index) => {
          const stateClass =
            index < currentStageIndex
              ? 'is-complete'
              : index === currentStageIndex
                ? 'is-active'
                : '';

          return (
            <div key={stage.id} className={`stage-pill ${stateClass}`}>
              <small>{`Stage 0${index + 1}`}</small>
              <strong>{stage.label}</strong>
            </div>
          );
        })}
      </section>

      <section className="workbench-grid">
        <KnowledgeSidebar
          selectedFile={selectedFile}
          isPreviewOpen={isKnowledgePreviewOpen}
          progressStep={progressStep}
          referencedFileIds={referencedFileIds}
          upcomingFileIds={upcomingFileIds}
          onSelectFile={(fileId) => {
            setSelectedFileId(fileId);
            setIsKnowledgePreviewOpen(true);
          }}
          onClosePreview={() => setIsKnowledgePreviewOpen(false)}
        />

        <ChatWorkspace
          turns={visibleTurns}
          nextAction={nextAction}
          onAdvance={(revealsUpToStep) => setProgressStep(revealsUpToStep)}
        />

        <InsightSidebar
          insights={visibleInsights}
          artifacts={visibleArtifacts}
          expandedCategories={expandedCategories}
          onToggleCategory={(category) =>
            setExpandedCategories((current) =>
              current.includes(category)
                ? current.filter((item) => item !== category)
                : [...current, category]
            )
          }
          onOpenDetail={setDetailItem}
        />
      </section>

      {detailItem
        ? isPrototypeArtifact(detailItem)
          ? (
              <PrototypeOverlay
                item={detailItem}
                onClose={() => setDetailItem(null)}
              />
            )
          : (
              <DetailDrawer
                item={detailItem}
                onClose={() => setDetailItem(null)}
              />
            )
        : null}
    </div>
  );
}

function KnowledgeSidebar({
  selectedFile,
  isPreviewOpen,
  progressStep,
  referencedFileIds,
  upcomingFileIds,
  onSelectFile,
  onClosePreview
}: {
  selectedFile: KnowledgeFile;
  isPreviewOpen: boolean;
  progressStep: number;
  referencedFileIds: string[];
  upcomingFileIds: string[];
  onSelectFile: (fileId: string) => void;
  onClosePreview: () => void;
}) {
  const scrollableRef = useRef<HTMLDivElement | null>(null);
  const activeTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [previewPlacement, setPreviewPlacement] =
    useState<KnowledgePreviewPlacement>('right');
  const [previewPosition, setPreviewPosition] = useState({
    top: KNOWLEDGE_PREVIEW_GAP,
    left: KNOWLEDGE_PREVIEW_GAP
  });

  const syncPreviewPosition = (element: HTMLButtonElement | null) => {
    if (!element) return;

    if (window.innerWidth <= COMPACT_LAYOUT_BREAKPOINT) {
      setPreviewPlacement('bottom');
      return;
    }

    setPreviewPlacement('right');
    setPreviewPosition(getKnowledgePreviewPosition(element.getBoundingClientRect()));
  };

  const handleSelectFile = (fileId: string, element: HTMLButtonElement) => {
    activeTriggerRef.current = element;
    syncPreviewPosition(element);
    onSelectFile(fileId);
  };

  useEffect(() => {
    if (!isPreviewOpen) return;

    const resyncPreview = () => syncPreviewPosition(activeTriggerRef.current);
    const scrollElement = scrollableRef.current;

    resyncPreview();
    window.addEventListener('resize', resyncPreview);
    scrollElement?.addEventListener('scroll', resyncPreview, { passive: true });

    return () => {
      window.removeEventListener('resize', resyncPreview);
      scrollElement?.removeEventListener('scroll', resyncPreview);
    };
  }, [isPreviewOpen, selectedFile.id]);

  const previewStyle: CSSProperties =
    previewPlacement === 'right'
      ? {
          position: 'fixed',
          top: `${previewPosition.top}px`,
          left: `${previewPosition.left}px`
        }
      : {
          position: 'fixed',
          left: '14px',
          right: '14px',
          bottom: '14px'
        };

  return (
    <aside className="workspace-panel knowledge-panel">
      <div className="panel-header">
        <div>
          <div className="eyebrow">Knowledge Base</div>
          <h2>项目知识库</h2>
        </div>
        <span className="count-pill">{knowledgeFiles.length}</span>
      </div>

      <div
        ref={scrollableRef}
        className="panel-scrollable"
        data-testid="knowledge-scroll"
      >
        <div className="fake-search">搜索文件、标签、字段...</div>

        <div className="tag-row">
          <span className="tag-chip">订单系统</span>
          <span className="tag-chip">财务系统</span>
          <span className="tag-chip">映射规则</span>
          <span className="tag-chip">{`已推进 ${progressStep + 1} / 5`}</span>
        </div>

        <div className="file-list">
          {knowledgeFiles.map((file) => (
            <button
              key={file.id}
              type="button"
              className={[
                'file-item',
                selectedFile.id === file.id ? 'is-active' : '',
                referencedFileIds.includes(file.id) ? 'is-referenced' : '',
                !referencedFileIds.includes(file.id) && upcomingFileIds.includes(file.id)
                  ? 'is-upcoming'
                  : ''
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={(event) =>
                handleSelectFile(file.id, event.currentTarget as HTMLButtonElement)
              }
            >
              <div className="file-head">
                <span className="file-type">{file.type}</span>
                <span className={`status-pill status-${statusClassName(file.status)}`}>
                  {file.status}
                </span>
              </div>
              <strong>{file.name}</strong>
              <div className="file-meta">
                <span>{file.version}</span>
                <span>{file.updatedAt}</span>
              </div>
              <div className="file-meta">
                <span>{file.owner}</span>
                <span>{`引用 ${file.quoteCount}`}</span>
              </div>
              <div className="tag-row">
                {referencedFileIds.includes(file.id) ? (
                  <span className="tag-chip subtle-chip">当前已引用</span>
                ) : null}
                {!referencedFileIds.includes(file.id) && upcomingFileIds.includes(file.id) ? (
                  <span className="tag-chip subtle-chip">下一轮关注</span>
                ) : null}
              </div>
            </button>
          ))}
        </div>
      </div>

      {isPreviewOpen ? (
        <KnowledgePreviewDialog
          selectedFile={selectedFile}
          previewPlacement={previewPlacement}
          previewStyle={previewStyle}
          referencedFileIds={referencedFileIds}
          upcomingFileIds={upcomingFileIds}
          onClosePreview={() => {
            activeTriggerRef.current = null;
            onClosePreview();
          }}
        />
      ) : null}
    </aside>
  );
}

function ChatWorkspace({
  turns,
  nextAction,
  onAdvance
}: {
  turns: ChatTurn[];
  nextAction: typeof actions[number] | null;
  onAdvance: (step: number) => void;
}) {
  const chatStreamRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!chatStreamRef.current) return;
    chatStreamRef.current.scrollTop = chatStreamRef.current.scrollHeight;
  }, [turns]);

  return (
    <main className="workspace-panel chat-panel">
      <div className="panel-header">
        <div>
          <div className="eyebrow">Conversation</div>
          <h2>需求分析对话</h2>
        </div>
      </div>

      <div
        ref={chatStreamRef}
        className="chat-stream chat-stream-scrollable"
        data-testid="chat-stream"
      >
        {turns.map((turn) =>
          turn.kind === 'checkpoint' ? (
            <article key={turn.id} className="checkpoint-card">
              <div className="bubble-meta">
                <span>系统生成</span>
                <span>{turn.timestampLabel}</span>
              </div>
              <p>{turn.content}</p>
            </article>
          ) : (
            <article
              key={turn.id}
              className={`chat-bubble role-${turn.role}`}
            >
              <div className="bubble-meta">
                <span>{roleLabel(turn.role)}</span>
                <span>{turn.timestampLabel}</span>
              </div>
              <p>{turn.content}</p>
              {turn.references && turn.references.length > 0 ? (
                <div className="bubble-reference-list">
                  {turn.references.map((reference) => (
                    <span key={reference} className="reference-chip">
                      {`引用资料：${
                        knowledgeFiles.find((file) => file.id === reference)?.name ?? reference
                      }`}
                    </span>
                  ))}
                </div>
              ) : null}
            </article>
          )
        )}
      </div>

      <div className="composer-card">
        <div className="composer-input">
          <span>继续补充客户原话、会议纪要或规则文档...</span>
        </div>
        <div className="composer-actions">
          {nextAction ? (
            <button
              type="button"
              className="action-button"
              onClick={() => onAdvance(nextAction.revealsUpToStep)}
            >
              {nextAction.label}
            </button>
          ) : (
            <span className="ghost-link">已完成本轮分析</span>
          )}
          <button type="button" className="secondary-button">
            客户补充
          </button>
          <button type="button" className="secondary-button">
            AI 生成当前理解
          </button>
          <button type="button" className="secondary-button">
            查看沉淀草稿
          </button>
        </div>
      </div>
    </main>
  );
}

function InsightSidebar({
  insights,
  artifacts,
  expandedCategories,
  onToggleCategory,
  onOpenDetail
}: {
  insights: InsightRecord[];
  artifacts: ArtifactRecord[];
  expandedCategories: InsightCategory[];
  onToggleCategory: (category: InsightCategory) => void;
  onOpenDetail: (item: DetailItem) => void;
}) {
  const categories: InsightCategory[] = [
    '已确认事实',
    '待确认项',
    '范围边界',
    'MVP 结论',
    '页面方案 / 交付物'
  ];

  return (
    <aside className="workspace-panel insights-panel">
      <div className="panel-header">
        <div>
          <div className="eyebrow">Insights</div>
          <h2>沉淀总集</h2>
        </div>
      </div>

      <div className="panel-scrollable" data-testid="insight-scroll">
        <div className="accordion-stack">
          {categories.map((category) => {
            const groupInsights =
              category === '页面方案 / 交付物'
                ? []
                : insights.filter((item) => item.category === category);
            const groupArtifacts =
              category === '页面方案 / 交付物' ? artifacts : [];
            const count =
              category === '页面方案 / 交付物'
                ? groupArtifacts.length + groupInsights.length
                : groupInsights.length;
            const latest =
              groupInsights[groupInsights.length - 1]?.title ??
              groupArtifacts[groupArtifacts.length - 1]?.title ??
              '等待生成';
            const isExpanded = expandedCategories.includes(category);

            return (
              <section key={category} className={`accordion-card ${isExpanded ? 'is-open' : ''}`}>
                <button
                  type="button"
                  className="accordion-trigger"
                  aria-expanded={isExpanded}
                  aria-label={`${isExpanded ? '收起' : '展开'}${category}`}
                  onClick={() => onToggleCategory(category)}
                >
                  <div className="group-head">
                    <strong>{category}</strong>
                    <span className="count-pill">{count}</span>
                  </div>
                  <p>{latest}</p>
                  <span className="detail-meta">
                    {isExpanded ? '已展开条目' : '展开查看条目'}
                  </span>
                </button>

                {isExpanded ? (
                  <div
                    className="accordion-content"
                    data-testid={`insight-drawer-${categoryTestId(category)}`}
                  >
                    {groupInsights.length === 0 && groupArtifacts.length === 0 ? (
                      <div className="insight-item-row is-empty">
                        <strong>等待生成</strong>
                        <p>当前阶段还没有沉淀到这个分类。</p>
                      </div>
                    ) : null}

                    {groupInsights.map((record) => (
                      <article key={record.id} className="insight-item-row">
                        <div className="drawer-card-head">
                          <strong>{record.title}</strong>
                          <span className={`status-pill status-${statusClassName(record.status)}`}>
                            {record.status}
                          </span>
                        </div>
                        <p>{record.body}</p>
                        <span className="detail-meta">{`来源阶段：${stageLabel(record.stage)}`}</span>
                      </article>
                    ))}

                    {groupArtifacts.map((artifact) => (
                      <button
                        key={artifact.id}
                        type="button"
                        className="insight-item-button"
                        aria-label={`查看${artifact.title}详情`}
                        onClick={() => onOpenDetail(artifact)}
                      >
                        <div className="drawer-card-head">
                          <strong>{artifact.title}</strong>
                          <span className="status-pill status-confirmed">{artifact.type}</span>
                        </div>
                        <p>{artifact.summary}</p>
                        <span className="detail-meta">点击查看详情</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

type DetailItem = ArtifactRecord;

function isPrototypeArtifact(item: DetailItem) {
  return item.previewMode === 'page-scheme' || item.previewMode === 'interaction-flow';
}

function DetailDrawer({
  item,
  onClose
}: {
  item: DetailItem;
  onClose: () => void;
}) {
  return (
    <aside className="drawer" role="complementary" aria-label={`${item.title}详情`}>
      <div className="drawer-header">
        <div>
          <div className="eyebrow">Detail</div>
          <h3>{item.title}</h3>
        </div>
        <button type="button" className="secondary-button" onClick={onClose}>
          关闭
        </button>
      </div>

      <div className="drawer-content">
        <section className="drawer-section">
          <div className="drawer-card artifact-card">
            <div className="drawer-card-head">
              <strong>{item.title}</strong>
              <span className="status-pill status-confirmed">{item.type}</span>
            </div>
            <p>{item.summary}</p>
            <div className="drawer-meta">
              <span className="detail-meta">{`来源阶段：${stageLabel(item.stage)}`}</span>
              <span className="detail-meta">{`版本：${item.version}`}</span>
              <span className="detail-meta">{`更新：${item.updatedAt}`}</span>
              <span className="detail-meta">{`责任方：${item.owner}`}</span>
              <span className="detail-meta">
                {`关联文件：${item.fileIds
                  .map((fileId) => knowledgeFiles.find((file) => file.id === fileId)?.name ?? fileId)
                  .join(' / ')}`}
              </span>
            </div>
          </div>
        </section>

        {item.previewMode === 'document' ? <DocumentPreview artifact={item} /> : null}
      </div>
    </aside>
  );
}

function DocumentPreview({ artifact }: { artifact: ArtifactRecord }) {
  return (
    <section className="drawer-section">
      <h4>文档摘要</h4>
      <article className="document-sheet">
        <header className="document-sheet-header">
          <div className="eyebrow">Requirement Brief</div>
          <h5>{artifact.coverTitle}</h5>
          <p>{artifact.summary}</p>
        </header>

        <div className="document-meta-row">
          <span>{`版本 ${artifact.version}`}</span>
          <span>{artifact.updatedAt}</span>
          <span>{artifact.owner}</span>
        </div>

        <div className="document-section-list">
          {(artifact.documentSections ?? []).map((section) => (
            <section key={section.title} className="document-section">
              <h6>{section.title}</h6>
              <p>{section.body}</p>
              {section.bullets && section.bullets.length > 0 ? (
                <ul className="plain-list">
                  {section.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ))}
        </div>
      </article>
    </section>
  );
}

function PrototypeOverlay({
  item,
  onClose
}: {
  item: ArtifactRecord;
  onClose: () => void;
}) {
  if (!item.prototypePath) return null;

  return createPortal(
    <div className="prototype-overlay-backdrop">
      <section
        className="prototype-overlay"
        role="dialog"
        aria-label={`${item.title}预览`}
      >
        <div className="prototype-overlay-header">
          <div>
            <div className="eyebrow">Large Preview</div>
            <h3>{item.title}</h3>
            <p>{item.summary}</p>
          </div>
          <button type="button" className="secondary-button" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="prototype-overlay-meta">
          <span className="detail-meta">{`来源阶段：${stageLabel(item.stage)}`}</span>
          <span className="detail-meta">{`版本：${item.version}`}</span>
          <span className="detail-meta">{`更新：${item.updatedAt}`}</span>
          <span className="detail-meta">{`责任方：${item.owner}`}</span>
        </div>

        <section className="prototype-overlay-body">
          <h4>大图预览</h4>
          <div className="prototype-shell prototype-shell-expanded">
            <iframe
              className="prototype-frame prototype-frame-expanded"
              title={`${item.title}原型`}
              src={item.prototypePath}
            />
          </div>
        </section>
      </section>
    </div>,
    document.body
  );
}

function categoryTestId(category: InsightCategory) {
  return category.replace(/\s*\/\s*/g, '-');
}

function roleLabel(role: ChatTurn['role']) {
  if (role === 'user') return '客户补充';
  if (role === 'assistant') return 'AI 分析';
  return '系统生成';
}

function statusClassName(status: string) {
  if (status === '有冲突' || status === '待确认') return 'warn';
  if (status === '已确认' || status === '已解析' || status === '已引用') return 'confirmed';
  return 'default';
}
