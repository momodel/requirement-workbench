import { useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { ProjectsPage } from './features/projects/ProjectsPage';
import { WorkbenchPage } from './features/workbench/WorkbenchPage';
import {
  createProject,
  createFileSource,
  createTextSource,
  createUrlSource,
  generateArtifact,
  getArtifactContent,
  getProject,
  getProjectState,
  listArtifacts,
  listProjects,
  listSources,
  sendChatRound
} from './lib/api';
import type { ArtifactRecord, ChatEvent, ProjectState, ProjectSummary, SourceRecord } from './lib/types';

type WorkbenchData = {
  project: ProjectSummary | null;
  sources: SourceRecord[];
  state: ProjectState | null;
  artifacts: ArtifactRecord[];
};

function appendStateItems(current: ProjectState, key: keyof ProjectState, items: Array<{ id: string; title: string; body: string }>) {
  if (key === 'artifacts') {
    return {
      ...current,
      artifacts: [...current.artifacts, ...items]
    };
  }

  return {
    ...current,
    [key]: [...current[key], ...items]
  } as ProjectState;
}

function applyChatEvent(
  previous: WorkbenchData,
  event: ChatEvent
): WorkbenchData {
  if (!previous.state) {
    return previous;
  }

  if (event.event === 'current_understanding_patch') {
    return { ...previous, state: appendStateItems(previous.state, 'currentUnderstanding', (event.data.items as Array<{ id: string; title: string; body: string }>) ?? []) };
  }
  if (event.event === 'pending_patch') {
    return { ...previous, state: appendStateItems(previous.state, 'pendingItems', (event.data.items as Array<{ id: string; title: string; body: string }>) ?? []) };
  }
  if (event.event === 'confirmed_patch') {
    return { ...previous, state: appendStateItems(previous.state, 'confirmedItems', (event.data.items as Array<{ id: string; title: string; body: string }>) ?? []) };
  }
  if (event.event === 'conflict_patch') {
    return { ...previous, state: appendStateItems(previous.state, 'conflictItems', (event.data.items as Array<{ id: string; title: string; body: string }>) ?? []) };
  }
  if (event.event === 'mvp_patch') {
    return { ...previous, state: appendStateItems(previous.state, 'mvpItems', (event.data.items as Array<{ id: string; title: string; body: string }>) ?? []) };
  }
  if (event.event === 'version_patch') {
    return { ...previous, state: appendStateItems(previous.state, 'versions', (event.data.items as Array<{ id: string; title: string; body: string }>) ?? []) };
  }
  if (event.event === 'artifact_patch') {
    const artifactItems = (event.data.items as Array<{
      id: string;
      artifact_type: string;
      title: string;
      summary: string;
      status: string;
      content_format: string;
      storage_path?: string;
    }>) ?? [];
    return {
      ...previous,
      state: appendStateItems(
        previous.state,
        'artifacts',
        artifactItems.map((item) => ({
          id: item.id,
          title: item.title,
          body: item.summary
        }))
      ),
      artifacts: [
        ...previous.artifacts,
        ...artifactItems.map((item) => ({
          id: item.id,
          artifactType: item.artifact_type,
          title: item.title,
          summary: item.summary,
          status: item.status,
          contentFormat: item.content_format,
          storagePath: item.storage_path
        }))
      ]
    };
  }

  return previous;
}

function HomeRoute() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);

  async function loadProjects() {
    const loaded = await listProjects();
    setProjects(loaded);
  }

  useEffect(() => {
    void loadProjects();
  }, []);

  async function handleCreateProject(name: string, summary: string, scenarioType: string) {
    await createProject(name, summary, scenarioType);
    await loadProjects();
  }

  return <ProjectsPage projects={projects} onCreateProject={handleCreateProject} />;
}

function WorkbenchRoute() {
  const { projectId = '' } = useParams();
  const [data, setData] = useState<WorkbenchData>({
    project: null,
    sources: [],
    state: null,
    artifacts: []
  });

  async function load() {
    const [project, sources, state, artifacts] = await Promise.all([
      getProject(projectId),
      listSources(projectId),
      getProjectState(projectId),
      listArtifacts(projectId)
    ]);

    setData({ project, sources, state, artifacts });
  }

  useEffect(() => {
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

  async function handleCreateTextSource(name: string, text: string) {
    await createTextSource(projectId, name, text);
    await load();
  }

  async function handleCreateUrlSource(name: string, url: string) {
    await createUrlSource(projectId, name, url);
    await load();
  }

  async function handleCreateFileSource(file: File) {
    await createFileSource(projectId, file);
    await load();
  }

  async function handleSendChat(
    message: string,
    onEvent?: (event: ChatEvent) => void
  ): Promise<ChatEvent[]> {
    const events = await sendChatRound(projectId, message, (event) => {
      setData((current) => applyChatEvent(current, event));
      onEvent?.(event);
    });
    await load();
    return events;
  }

  async function handleGenerateArtifact(artifactType: string) {
    await generateArtifact(projectId, artifactType);
    await load();
  }

  async function handleOpenArtifact(artifact: ArtifactRecord) {
    return getArtifactContent(projectId, artifact.id);
  }

  return (
    <WorkbenchPage
      project={data.project}
      sources={data.sources}
      state={data.state}
      artifacts={data.artifacts}
      onCreateTextSource={handleCreateTextSource}
      onCreateUrlSource={handleCreateUrlSource}
      onCreateFileSource={handleCreateFileSource}
      onSendChat={handleSendChat}
      onGenerateArtifact={handleGenerateArtifact}
      onOpenArtifact={handleOpenArtifact}
    />
  );
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
