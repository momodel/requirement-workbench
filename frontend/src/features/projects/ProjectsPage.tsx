import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { ProjectSummary } from '../../lib/types';

export function ProjectsPage({
  projects,
  onCreateProject
}: {
  projects: ProjectSummary[];
  onCreateProject: (name: string, summary: string, scenarioType: string) => Promise<void>;
}) {
  const [projectName, setProjectName] = useState('');
  const [projectSummary, setProjectSummary] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  async function handleCreateProject() {
    if (!projectName.trim()) {
      return;
    }

    setIsCreating(true);
    try {
      await onCreateProject(
        projectName.trim(),
        projectSummary.trim(),
        'general-requirement'
      );
      setProjectName('');
      setProjectSummary('');
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="hero-card">
        <p className="eyebrow">Full-stack Phase 1</p>
        <h1>客户需求转译台</h1>
        <p className="hero-copy">
          仓库已经从旧 demo 资产切到一期主工程。这里展示项目入口，后续从项目维度进入工作台。
        </p>
        <div className="hero-form">
          <label className="field-label">
            <span>项目名称</span>
            <input
              name="projectName"
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="例如：结算对账分析"
            />
          </label>
          <label className="field-label">
            <span>项目摘要</span>
            <textarea
              name="projectSummary"
              value={projectSummary}
              onChange={(event) => setProjectSummary(event.target.value)}
              rows={3}
              placeholder="输入这次需求分析的项目背景"
            />
          </label>
          <button
            type="button"
            className="primary-link action-button"
            onClick={() => void handleCreateProject()}
            disabled={isCreating}
          >
            {isCreating ? '创建中...' : '新建项目'}
          </button>
        </div>
      </section>

      <section className="project-list">
        {projects.map((project) => (
          <article key={project.id} className="project-card">
            <div className="project-card-head">
              <strong>{project.name}</strong>
              <span className="status-pill">{project.status}</span>
            </div>
            <p>{project.summary}</p>
            <div className="meta-row">
              <span>{project.scenarioType}</span>
              <span>{project.updatedAt}</span>
            </div>
            <Link className="primary-link" to={`/projects/${project.id}/workbench`}>
              进入工作台
            </Link>
          </article>
        ))}
      </section>
    </main>
  );
}
