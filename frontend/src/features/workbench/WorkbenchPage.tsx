import { useState } from 'react';
import type { ChangeEvent } from 'react';
import type {
  ArtifactRecord,
  ChatEvent,
  ProjectState,
  ProjectSummary,
  SourceRecord,
  StateItem
} from '../../lib/types';

const stateSections: Array<{
  key: keyof ProjectState;
  label: string;
}> = [
  { key: 'currentUnderstanding', label: '当前理解' },
  { key: 'pendingItems', label: '待确认项' },
  { key: 'confirmedItems', label: '已确认项' },
  { key: 'conflictItems', label: '冲突项' },
  { key: 'mvpItems', label: 'MVP' },
  { key: 'versions', label: '版本' }
];

function renderItems(items: StateItem[]) {
  if (items.length === 0) {
    return <p className="empty-copy">当前还没有内容。</p>;
  }

  return (
    <div className="stack-list">
      {items.map((item) => (
        <article key={item.id} className="panel-card compact-card">
          <strong>{item.title}</strong>
          <p>{item.body}</p>
        </article>
      ))}
    </div>
  );
}

export function WorkbenchPage({
  project,
  sources,
  state,
  artifacts,
  onCreateTextSource,
  onCreateUrlSource,
  onCreateFileSource,
  onSendChat,
  onGenerateArtifact,
  onOpenArtifact
}: {
  project: ProjectSummary;
  sources: SourceRecord[];
  state: ProjectState;
  artifacts: ArtifactRecord[];
  onCreateTextSource: (name: string, text: string) => Promise<void>;
  onCreateUrlSource: (name: string, url: string) => Promise<void>;
  onCreateFileSource: (file: File) => Promise<void>;
  onSendChat: (message: string, onEvent?: (event: ChatEvent) => void) => Promise<ChatEvent[]>;
  onGenerateArtifact: (artifactType: string) => Promise<void>;
  onOpenArtifact: (artifact: ArtifactRecord) => Promise<string>;
}) {
  const [sourceName, setSourceName] = useState('');
  const [sourceText, setSourceText] = useState('');
  const [urlName, setUrlName] = useState('');
  const [urlValue, setUrlValue] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [chatEvents, setChatEvents] = useState<ChatEvent[]>([]);
  const [isSubmittingSource, setIsSubmittingSource] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [isGeneratingArtifact, setIsGeneratingArtifact] = useState(false);
  const [activeSource, setActiveSource] = useState<SourceRecord | null>(null);
  const [activeArtifact, setActiveArtifact] = useState<{
    record: ArtifactRecord;
    content: string;
  } | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  async function handleCreateTextSource() {
    if (!sourceName.trim() || !sourceText.trim()) {
      return;
    }

    setIsSubmittingSource(true);
    try {
      await onCreateTextSource(sourceName.trim(), sourceText.trim());
      setSourceName('');
      setSourceText('');
    } finally {
      setIsSubmittingSource(false);
    }
  }

  async function handleCreateUrlSource() {
    if (!urlName.trim() || !urlValue.trim()) {
      return;
    }

    setIsSubmittingSource(true);
    try {
      await onCreateUrlSource(urlName.trim(), urlValue.trim());
      setUrlName('');
      setUrlValue('');
    } finally {
      setIsSubmittingSource(false);
    }
  }

  async function handleSelectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setIsSubmittingSource(true);
    try {
      await onCreateFileSource(file);
      event.target.value = '';
    } finally {
      setIsSubmittingSource(false);
    }
  }

  async function handleSendChat() {
    if (!chatInput.trim()) {
      return;
    }

    setIsSendingChat(true);
    try {
      setChatEvents([]);
      const events = await onSendChat(chatInput.trim(), (event) => {
        setChatEvents((current) => [...current, event]);
      });
      setChatEvents((current) => (current.length > 0 ? current : events));
      setChatInput('');
    } finally {
      setIsSendingChat(false);
    }
  }

  async function handleGenerateArtifact(artifactType: string) {
    setIsGeneratingArtifact(true);
    try {
      await onGenerateArtifact(artifactType);
    } finally {
      setIsGeneratingArtifact(false);
    }
  }

  async function handleOpenArtifact(artifact: ArtifactRecord) {
    setArtifactError(null);
    try {
      const content = await onOpenArtifact(artifact);
      setActiveArtifact({ record: artifact, content });
    } catch (error) {
      setArtifactError(error instanceof Error ? error.message : '打开交付物失败。');
    }
  }

  const documentArtifacts = artifacts.filter((artifact) => artifact.contentFormat === 'json');
  const htmlArtifacts = artifacts.filter((artifact) => artifact.contentFormat === 'html');

  return (
    <main className="workbench-shell">
      <header className="workbench-header">
        <div>
          <p className="eyebrow">Full-stack Phase 1 Workbench</p>
          <h1>{project.name}</h1>
          <p className="hero-copy">{project.summary}</p>
        </div>
        <span className="status-pill">{project.status}</span>
      </header>

      <section className="workbench-grid">
        <aside className="workspace-panel sources-panel">
          <div className="panel-header">
            <h2>Sources</h2>
            <span>{sources.length} 份资料</span>
          </div>

          <div className="stack-list">
            <div className="panel-card compact-card input-card">
              <label className="field-label">
                <span>资料名称</span>
                <input
                  name="sourceName"
                  value={sourceName}
                  onChange={(event) => setSourceName(event.target.value)}
                  placeholder="例如：补充纪要.txt"
                />
              </label>
              <label className="field-label">
                <span>资料正文</span>
                <textarea
                  name="sourceText"
                  value={sourceText}
                  onChange={(event) => setSourceText(event.target.value)}
                  rows={4}
                  placeholder="粘贴本轮新拿到的补充资料"
                />
              </label>
              <button
                type="button"
                className="primary-link action-button"
                onClick={() => void handleCreateTextSource()}
                disabled={isSubmittingSource}
              >
                {isSubmittingSource ? '导入中...' : '导入文本资料'}
              </button>
            </div>

            <div className="panel-card compact-card input-card">
              <label className="field-label">
                <span>链接名称</span>
                <input
                  name="urlName"
                  value={urlName}
                  onChange={(event) => setUrlName(event.target.value)}
                  placeholder="例如：业务系统说明"
                />
              </label>
              <label className="field-label">
                <span>资料链接</span>
                <input
                  name="urlValue"
                  value={urlValue}
                  onChange={(event) => setUrlValue(event.target.value)}
                  placeholder="https://example.com/spec"
                />
              </label>
              <button
                type="button"
                className="primary-link action-button secondary-action"
                onClick={() => void handleCreateUrlSource()}
                disabled={isSubmittingSource}
              >
                导入链接资料
              </button>
            </div>

            <div className="panel-card compact-card input-card">
              <label className="field-label">
                <span>上传文件</span>
                <input type="file" onChange={(event) => void handleSelectFile(event)} />
              </label>
            </div>
          </div>

          <div className="stack-list source-list">
            {sources.map((source) => (
              <article key={source.id} className="panel-card compact-card source-card">
                <div className="source-card-head">
                  <div>
                    <strong>{source.name}</strong>
                    <p>{source.sourceKind}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => setActiveSource(source)}
                    aria-label={`查看${source.name}摘要`}
                  >
                    查看摘要
                  </button>
                </div>
                <div className="meta-row">
                  <span>{`解析：${source.parseStatus}`}</span>
                  <span>{`同步：${source.syncStatus}`}</span>
                </div>
                <p className="summary-copy">{source.parseSummary ?? '当前暂无摘要。'}</p>
              </article>
            ))}
          </div>
        </aside>

        <section className="workspace-panel chat-column">
          <div className="panel-header">
            <h2>Chat</h2>
            <span>{chatEvents.length > 0 ? `${chatEvents.length} 个事件` : '已接到真实事件流'}</span>
          </div>
          <div className="panel-card chat-panel">
            <div className="chat-events">
              {chatEvents.length === 0 ? (
                <article className="chat-bubble assistant-bubble">
                  <strong>系统就绪</strong>
                  <p>这里会显示本轮 assistant 输出、资料引用和状态 patch 事件。</p>
                </article>
              ) : (
                chatEvents.map((event, index) => (
                  <article
                    key={`${event.event}-${index}`}
                    className={`chat-bubble ${event.event === 'message_chunk' ? 'assistant-bubble' : 'system-bubble'}`}
                  >
                    <strong>{event.event}</strong>
                    <p>{String(event.data.text ?? JSON.stringify(event.data))}</p>
                  </article>
                ))
              )}
            </div>
            <div className="chat-composer">
              <label className="field-label">
                <span>聊天输入</span>
                <textarea
                  name="chatInput"
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  rows={4}
                  placeholder="输入本轮想继续推进的问题"
                />
              </label>
              <button
                type="button"
                className="primary-link action-button"
                onClick={() => void handleSendChat()}
                disabled={isSendingChat}
              >
                {isSendingChat ? '分析中...' : '发送分析请求'}
              </button>
            </div>
          </div>
        </section>

        <aside className="workspace-panel state-panel">
          <div className="panel-header">
            <h2>Project State</h2>
            <div className="inline-actions">
              <button
                type="button"
                className="primary-link action-button secondary-action"
                onClick={() => void handleGenerateArtifact('document')}
                disabled={isGeneratingArtifact}
              >
                文档稿
              </button>
              <button
                type="button"
                className="primary-link action-button secondary-action"
                onClick={() => void handleGenerateArtifact('page_solution')}
                disabled={isGeneratingArtifact}
              >
                页面方案
              </button>
              <button
                type="button"
                className="primary-link action-button secondary-action"
                onClick={() => void handleGenerateArtifact('interaction_flow')}
                disabled={isGeneratingArtifact}
              >
                交互稿
              </button>
            </div>
          </div>

          {stateSections.map((section) => (
            <section key={section.key} className="state-block">
              <h3>{section.label}</h3>
              {renderItems(state[section.key])}
            </section>
          ))}

          <section className="state-block">
            <h3>交付物</h3>
            {artifacts.length === 0 ? (
              <p className="empty-copy">当前还没有交付物。</p>
            ) : (
              <div className="stack-list">
                {documentArtifacts.map((artifact) => (
                  <article key={artifact.id} className="panel-card compact-card artifact-card">
                    <strong>{artifact.title}</strong>
                    <p>{artifact.summary}</p>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => void handleOpenArtifact(artifact)}
                    >
                      {`查看${artifact.title}`}
                    </button>
                  </article>
                ))}
                {htmlArtifacts.map((artifact) => (
                  <article key={artifact.id} className="panel-card compact-card artifact-card">
                    <strong>{artifact.title}</strong>
                    <p>{artifact.summary}</p>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => void handleOpenArtifact(artifact)}
                    >
                      {`查看${artifact.title}`}
                    </button>
                  </article>
                ))}
              </div>
            )}
            {artifactError ? <p className="error-copy">{artifactError}</p> : null}
          </section>
        </aside>
      </section>

      {activeSource ? (
        <div className="floating-preview">
          <div className="floating-preview-card">
            <div className="panel-header">
              <h3>{activeSource.name}</h3>
              <button type="button" className="ghost-button" onClick={() => setActiveSource(null)}>
                关闭
              </button>
            </div>
            <p>{activeSource.parseSummary ?? '当前没有可展示的摘要。'}</p>
            <div className="meta-row">
              <span>{activeSource.sourceKind}</span>
              <span>{activeSource.syncStatus}</span>
            </div>
          </div>
        </div>
      ) : null}

      {activeArtifact ? (
        <div className="artifact-overlay">
          <div className={`artifact-overlay-card artifact-${activeArtifact.record.contentFormat}`}>
            <div className="panel-header">
              <h3>{activeArtifact.record.title}</h3>
              <button type="button" className="ghost-button" onClick={() => setActiveArtifact(null)}>
                关闭
              </button>
            </div>
            {activeArtifact.record.contentFormat === 'html' ? (
              <iframe title={activeArtifact.record.title} srcDoc={activeArtifact.content} className="artifact-frame" />
            ) : (
              <pre className="artifact-document">{activeArtifact.content}</pre>
            )}
          </div>
        </div>
      ) : null}
    </main>
  );
}
