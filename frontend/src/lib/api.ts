import type { ProjectState, ProjectSummary, SourceRecord } from './types';

const seedProject: ProjectSummary = {
  id: 'seed-reconciliation',
  name: '业财逐笔对账',
  summary: '默认 seed project，用来验证全栈一期的项目、资料、聊天和沉淀链路。',
  status: 'seed',
  scenarioType: 'financial-reconciliation',
  updatedAt: '刚刚'
};

const seedSources: SourceRecord[] = [
  {
    id: 'src-order-fields',
    name: '订单字段说明.md',
    sourceKind: 'markdown',
    parseStatus: 'parsed',
    syncStatus: 'pending'
  },
  {
    id: 'src-finance-rules',
    name: '财务科目口径.pdf',
    sourceKind: 'pdf',
    parseStatus: 'parsed',
    syncStatus: 'pending'
  }
];

const seedState: ProjectState = {
  currentUnderstanding: [
    {
      id: 'understanding-1',
      title: '当前工作台骨架已切到 project-first',
      body: '后续状态不再挂在 stage 页面上，而是围绕项目对象持续维护。'
    }
  ],
  pendingItems: [
    {
      id: 'pending-1',
      title: '接入真实 SSE 聊天流',
      body: '当前前端先用 fallback seed 渲染，后续替换为真实 API。'
    }
  ],
  confirmedItems: [],
  conflictItems: [],
  mvpItems: [],
  versions: [
    {
      id: 'version-1',
      title: '初始化版本',
      body: '仓库已完成旧 demo 归档与一期主工程骨架创建。'
    }
  ],
  artifacts: []
};

export async function listProjects(): Promise<ProjectSummary[]> {
  return [seedProject];
}

export async function getProject(projectId: string): Promise<ProjectSummary> {
  if (projectId === seedProject.id) {
    return seedProject;
  }

  throw new Error(`Unknown project: ${projectId}`);
}

export async function listSources(projectId: string): Promise<SourceRecord[]> {
  if (projectId === seedProject.id) {
    return seedSources;
  }

  return [];
}

export async function getProjectState(projectId: string): Promise<ProjectState> {
  if (projectId === seedProject.id) {
    return seedState;
  }

  return {
    currentUnderstanding: [],
    pendingItems: [],
    confirmedItems: [],
    conflictItems: [],
    mvpItems: [],
    versions: [],
    artifacts: []
  };
}
