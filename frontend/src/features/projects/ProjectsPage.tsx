import { Link } from 'react-router-dom';
import type { ProjectSummary } from '../../lib/types';

export function ProjectsPage({ projects }: { projects: ProjectSummary[] }) {
  return (
    <main className="page-shell">
      <section className="hero-card">
        <p className="eyebrow">Full-stack Phase 1</p>
        <h1>客户需求转译台</h1>
        <p className="hero-copy">
          仓库已经从旧 demo 资产切到一期主工程。这里展示项目入口，后续从项目维度进入工作台。
        </p>
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
