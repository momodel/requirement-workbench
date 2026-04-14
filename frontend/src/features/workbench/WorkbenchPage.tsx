import type { ProjectState, ProjectSummary, SourceRecord, StateItem } from '../../lib/types';

const stateSections: Array<{
  key: keyof ProjectState;
  label: string;
}> = [
  { key: 'currentUnderstanding', label: '当前理解' },
  { key: 'pendingItems', label: '待确认项' },
  { key: 'confirmedItems', label: '已确认项' },
  { key: 'conflictItems', label: '冲突项' },
  { key: 'mvpItems', label: 'MVP' },
  { key: 'versions', label: '版本' },
  { key: 'artifacts', label: '交付物' }
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
  state
}: {
  project: ProjectSummary;
  sources: SourceRecord[];
  state: ProjectState;
}) {
  return (
    <main className="workbench-shell">
      <header className="workbench-header">
        <div>
          <p className="eyebrow">Project-first Workbench</p>
          <h1>{project.name}</h1>
        </div>
        <span className="status-pill">{project.status}</span>
      </header>

      <section className="workbench-grid">
        <aside className="workspace-panel">
          <div className="panel-header">
            <h2>Sources</h2>
            <span>{sources.length} 份资料</span>
          </div>
          <div className="stack-list">
            {sources.map((source) => (
              <article key={source.id} className="panel-card compact-card">
                <strong>{source.name}</strong>
                <p>{source.sourceKind}</p>
                <div className="meta-row">
                  <span>{`解析：${source.parseStatus}`}</span>
                  <span>{`同步：${source.syncStatus}`}</span>
                </div>
              </article>
            ))}
          </div>
        </aside>

        <section className="workspace-panel">
          <div className="panel-header">
            <h2>Chat</h2>
            <span>下一步接真实 SSE</span>
          </div>
          <div className="panel-card chat-placeholder">
            <strong>这里会承接真实对话流。</strong>
            <p>
              当前只保留新的工作台骨架，后续会把 Claude Agent SDK、NotebookLM grounding
              和结构化 patch 逐步接进来。
            </p>
          </div>
        </section>

        <aside className="workspace-panel">
          <div className="panel-header">
            <h2>Project State</h2>
            <span>聚合状态</span>
          </div>
          {stateSections.map((section) => (
            <section key={section.key} className="state-block">
              <h3>{section.label}</h3>
              {renderItems(state[section.key])}
            </section>
          ))}
        </aside>
      </section>
    </main>
  );
}
