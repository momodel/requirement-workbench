import { ArrowRight, FolderKanban, Loader2, Plus, Sparkles } from 'lucide-react';
import { useState } from 'react';
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
import type { GlobalReadiness, ProjectSummary } from '../../lib/types';

function readinessVariant(status: string) {
  if (status === 'ready') return 'success' as const;
  if (status.includes('required') || status.includes('not_configured')) return 'warning' as const;
  return 'default' as const;
}

function evidenceReadiness(readiness: GlobalReadiness) {
  return readiness.evidence;
}

export function ProjectsPage({
  projects,
  readiness,
  creating,
  onCreateProject,
}: {
  projects: ProjectSummary[];
  readiness: GlobalReadiness | null;
  creating: boolean;
  onCreateProject: (payload: {
    name: string;
    scenario_type: string;
    summary: string;
  }) => Promise<void>;
}) {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [scenarioType, setScenarioType] = useState('');
  const [projectSummary, setProjectSummary] = useState('');

  async function handleCreateProject() {
    const name = projectName.trim();
    const scenario = scenarioType.trim();
    const summary = projectSummary.trim();
    if (!name || !scenario || !summary) return;

    await onCreateProject({
      name,
      scenario_type: scenario,
      summary,
    });
    setProjectName('');
    setScenarioType('');
    setProjectSummary('');
    setIsCreateDialogOpen(false);
  }

  return (
    <main className="min-h-screen px-6 py-10 text-nearBlack">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10">
        <Card className="overflow-hidden border-borderCream bg-ivory">
          <CardContent className="grid gap-10 p-9 md:grid-cols-[1.35fr_0.65fr]">
            <div className="space-y-6">
              <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone">
                <Sparkles className="h-3.5 w-3.5 text-terracotta" />
                Fullstack Phase 1
              </div>
              <div className="space-y-4">
                <h1 className="font-display text-balance text-[3rem] font-medium leading-[1.1] tracking-tightish md:text-[3.6rem]">
                  客户需求转译台
                </h1>
                <p className="max-w-2xl text-[1.05rem] leading-[1.6] text-olive">
                  这里不是对账系统本体，而是需求分析工作台。项目、资料、聊天、沉淀和交付物都围绕
                  <strong className="px-1 font-medium text-nearBlack">Project</strong>
                  组织，而不是靠阶段页面硬切流程。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="accent">Project-first</Badge>
                <Badge>FastAPI · SQLite · SSE</Badge>
                <Badge>Claude Agent SDK · 项目内 RAG</Badge>
              </div>
            </div>

            <div className="grid gap-4 rounded-[18px] border border-borderWarm bg-parchment/70 p-5">
              <div className="space-y-2">
                <div className="text-[11px] font-medium uppercase tracking-[0.2em] text-stone">
                  当前范围
                </div>
                <p className="text-sm leading-[1.6] text-olive">
                  一期先把真实资料接入、项目状态沉淀、SSE 聊天链路和交付物预览跑通，默认案例为
                  <span className="px-1 text-nearBlack">业财逐笔对账</span>。
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-[14px] border border-borderCream bg-ivory p-4">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-stone">项目数</div>
                  <div className="mt-2 font-display text-[2rem] font-medium leading-none text-nearBlack">{projects.length}</div>
                </div>
                <div className="rounded-[14px] border border-borderCream bg-ivory p-4">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-stone">默认案例</div>
                  <div className="mt-2 font-display text-[1.05rem] font-medium leading-tight text-nearBlack">业财逐笔对账</div>
                </div>
              </div>
              {readiness ? (
                <div className="grid gap-3 rounded-[14px] border border-borderCream bg-ivory p-4 text-sm">
                  <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone">
                    Provider Readiness
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-nearBlack">Claude Agent SDK</div>
                      <div className="mt-1 leading-6 text-olive">{readiness.claude.summary}</div>
                    </div>
                    <Badge variant={readinessVariant(readiness.claude.status)}>{readiness.claude.status}</Badge>
                  </div>
                  <div className="h-px bg-borderCream" />
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-nearBlack">Evidence Runtime</div>
                      <div className="mt-1 leading-6 text-olive">{evidenceReadiness(readiness)?.summary ?? '证据运行时状态未返回。'}</div>
                    </div>
                    <Badge variant={readinessVariant(evidenceReadiness(readiness)?.status ?? 'unknown')}>{evidenceReadiness(readiness)?.status ?? 'unknown'}</Badge>
                  </div>
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-5">
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-[11px] font-medium uppercase tracking-[0.2em] text-stone">
                项目列表
              </div>
              <h2 className="mt-2 font-display text-[1.75rem] font-medium leading-tight tracking-tightish text-nearBlack">
                选择一个项目进入工作台
              </h2>
            </div>
            <Button onClick={() => setIsCreateDialogOpen(true)}>
              <Plus className="h-4 w-4" />
              新建项目
            </Button>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {projects.map((project) => (
              <Card key={project.id} className="group border-borderCream bg-ivory transition-shadow duration-150 hover:shadow-[0_8px_32px_-18px_rgba(20,20,19,0.18)]">
                <CardHeader className="pb-2">
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-[12px] uppercase tracking-[0.16em] text-stone">
                          <FolderKanban className="h-3.5 w-3.5" />
                          {project.scenario_type}
                        </div>
                        <CardTitle className="text-[1.5rem] leading-[1.2]">{project.name}</CardTitle>
                      </div>
                      <Badge variant="accent">{project.status}</Badge>
                    </div>
                    <CardDescription className="text-[15px] leading-[1.6]">
                      {project.summary}
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="flex items-center justify-between gap-4 pt-2">
                  <div className="text-xs text-stone">
                    最近更新 · {new Date(project.updated_at).toLocaleString('zh-CN')}
                  </div>
                  <Button asChild size="sm">
                    <Link to={`/projects/${project.id}/workbench`}>
                      进入工作台
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>

      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="w-[min(620px,92vw)]">
          <DialogHeader>
            <DialogTitle>新建项目</DialogTitle>
            <DialogDescription>
              新项目从 Project 开始。先填项目名、场景类型和一句话摘要，创建后直接进入工作台。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone">项目名</span>
              <Input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                placeholder="例如：集团业财逐笔对账需求分析"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone">场景类型</span>
              <Input
                value={scenarioType}
                onChange={(event) => setScenarioType(event.target.value)}
                placeholder="例如：financial-reconciliation"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone">一句话摘要</span>
              <Textarea
                value={projectSummary}
                onChange={(event) => setProjectSummary(event.target.value)}
                placeholder="用一句话说明这个项目想解决什么问题。"
                className="min-h-[140px]"
              />
            </label>
            <div className="mt-1 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setIsCreateDialogOpen(false)} disabled={creating}>
                取消
              </Button>
              <Button
                onClick={() => void handleCreateProject()}
                disabled={creating || !projectName.trim() || !scenarioType.trim() || !projectSummary.trim()}
              >
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                创建并进入工作台
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
