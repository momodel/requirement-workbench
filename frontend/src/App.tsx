import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { ProjectsPage } from './features/projects/ProjectsPage';
import { WorkbenchPage } from './features/workbench/WorkbenchPage';
import { getProject, getProjectState, listProjects, listSources } from './lib/api';
import type { ProjectState, ProjectSummary, SourceRecord } from './lib/types';

type WorkbenchData = {
  project: ProjectSummary | null;
  sources: SourceRecord[];
  state: ProjectState | null;
};

function HomeRoute() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);

  useEffect(() => {
    listProjects().then(setProjects);
  }, []);

  return <ProjectsPage projects={projects} />;
}

function WorkbenchRoute() {
  const { projectId = '' } = useParams();
  const [data, setData] = useState<WorkbenchData>({
    project: null,
    sources: [],
    state: null
  });

  useEffect(() => {
    async function load() {
      const [project, sources, state] = await Promise.all([
        getProject(projectId),
        listSources(projectId),
        getProjectState(projectId)
      ]);

      setData({ project, sources, state });
    }

    void load();
  }, [projectId]);

  if (!data.project || !data.state) {
    return (
      <main className="page-shell">
        <section className="hero-card">
          <p className="eyebrow">Loading</p>
          <h1>正在加载项目</h1>
        </section>
      </main>
    );
  }

  return <WorkbenchPage project={data.project} sources={data.sources} state={data.state} />;
}

export default function App() {
  return (
    <BrowserRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/projects/:projectId/workbench" element={<WorkbenchRoute />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
