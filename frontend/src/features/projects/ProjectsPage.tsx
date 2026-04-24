import { AlertTriangle, ArrowRight, FolderKanban, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react';
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

type PageNotice = {
  kind: 'error' | 'info';
  title: string;
  body: string;
};

function readinessVariant(status: string) {
  if (status === 'ready') return 'success' as const;
  if (status.includes('failed') || status.includes('error')) return 'danger' as const;
  if (
    status.includes('required') ||
    status.includes('not_configured') ||
    status.includes('missing') ||
    status.includes('binding') ||
    status.includes('auth')
  ) {
    return 'warning' as const;
  }
  return 'default' as const;
}

function readinessStatusLabel(status: string) {
  if (status === 'ready') return '已就绪';
  if (status === 'knowledge_base_missing') return '待初始化';
  if (status === 'auth_required') return '待认证';
  if (status === 'not_configured') return '未配置';
  if (status.includes('failed') || status.includes('error')) return '异常';
  return status;
}

export function ProjectsPage({
  projects,
  readiness,
  notice,
  creating,
  deletingProjectId,
  onCreateProject,
  onDeleteProject,
}: {
  projects: ProjectSummary[];
  readiness: GlobalReadiness | null;
  notice: PageNotice | null;
  creating: boolean;
  deletingProjectId: string | null;
  onCreateProject: (payload: {
    name: string;
    scenario_type: string;
    summary: string;
  }) => Promise<void>;
  onDeleteProject: (project: ProjectSummary) => Promise<void>;
}) {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [projectPendingDelete, setProjectPendingDelete] = useState<ProjectSummary | null>(null);
  const [projectName, setProjectName] = useState('');
  const [scenarioType, setScenarioType] = useState('');
  const [projectSummary, setProjectSummary] = useState('');
  const evidenceReadiness = readiness?.evidence ?? null;

  async function handleCreateProject() {
    const name = projectName.trim();
    const scenario = scenarioType.trim();
    const summary = projectSummary.trim();
    if (!name || !scenario || !summary) return;

    try {
      await onCreateProject({
        name,
        scenario_type: scenario,
        summary,
      });
      setProjectName('');
      setScenarioType('');
      setProjectSummary('');
      setIsCreateDialogOpen(false);
    } catch {
      // 页面级错误提示由上层路由负责，弹窗保持打开便于用户调整输入后重试。
    }
  }

  async function handleDeleteProject() {
    if (!projectPendingDelete) {
      return;
    }

    try {
      await onDeleteProject(projectPendingDelete);
      setProjectPendingDelete(null);
    } catch {
      // 删除失败时保留确认弹窗，让用户直接看到错误并决定是否重试。
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(23,71,111,0.10),_transparent_28%),linear-gradient(180deg,_#eef4f9_0%,_#f6f8fb_55%,_#eef2f7_100%)] px-6 py-8 text-ink">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <Card className="overflow-hidden border-white/60 bg-white/90">
          <CardContent className="grid gap-8 p-8 md:grid-cols-[1.35fr_0.65fr]">
            <div className="space-y-5">
              <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-[0.22em] text-muted">
                <Sparkles className="h-4 w-4" />
                Fullstack Phase 1
              </div>
              <div className="space-y-3">
                <h1 className="max-w-3xl text-4xl font-semibold tracking-tight md:text-5xl">
                  客户需求转译台
                </h1>
                <p className="max-w-3xl text-base leading-8 text-muted md:text-lg">
                  这里不是对账系统本体，而是需求分析工作台。项目、资料、聊天、沉淀和交付物都围绕
                  <strong className="px-1 text-ink">Project</strong>
                  组织，而不是靠阶段页面硬切流程。
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Badge variant="accent">Project-first</Badge>
                <Badge>FastAPI + SQLite + SSE</Badge>
                <Badge>Claude Agent SDK / Evidence Runtime</Badge>
              </div>
            </div>

            <div className="grid gap-4 rounded-[28px] border border-line bg-sand/70 p-5">
              <div className="space-y-2">
                <div className="text-xs font-medium uppercase tracking-[0.2em] text-muted">
                  当前范围
                </div>
                <p className="text-sm leading-7 text-muted">
                  一期先把真实资料接入、项目状态沉淀、SSE 聊天链路和交付物预览跑通，默认案例为
                  “业财逐笔对账”。
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Card className="rounded-[22px] border-line bg-white/90 shadow-none">
                  <CardContent className="p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-muted">项目数</div>
                    <div className="mt-2 text-3xl font-semibold text-ink">{projects.length}</div>
                  </CardContent>
                </Card>
                <Card className="rounded-[22px] border-line bg-white/90 shadow-none">
                  <CardContent className="p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-muted">默认案例</div>
                    <div className="mt-2 text-lg font-semibold text-ink">业财逐笔对账</div>
                  </CardContent>
                </Card>
              </div>
              {readiness ? (
                <div className="grid gap-3 rounded-[22px] border border-line bg-white/80 p-4 text-sm">
                  <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted">
                    Runtime Readiness
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium text-ink">Claude Agent SDK</div>
                      <div className="mt-1 leading-6 text-muted">{readiness.claude.summary}</div>
                    </div>
                    <Badge variant={readinessVariant(readiness.claude.status)}>
                      {readinessStatusLabel(readiness.claude.status)}
                    </Badge>
                  </div>
                  {evidenceReadiness ? (
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-medium text-ink">Evidence Runtime</div>
                        <div className="mt-1 leading-6 text-muted">{evidenceReadiness.summary}</div>
                      </div>
                      <Badge variant={readinessVariant(evidenceReadiness.status)}>
                        {readinessStatusLabel(evidenceReadiness.status)}
                      </Badge>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {notice ? (
          <Card
            className={
              notice.kind === 'error'
                ? 'border-rose-200 bg-rose-50/90'
                : 'border-amber-200 bg-amber-50/90'
            }
          >
            <CardContent className="flex items-start gap-3 p-5">
              <AlertTriangle
                className={
                  notice.kind === 'error'
                    ? 'mt-0.5 h-5 w-5 text-rose-700'
                    : 'mt-0.5 h-5 w-5 text-amber-700'
                }
              />
              <div className="space-y-1">
                <div className="text-sm font-semibold text-ink">{notice.title}</div>
                <p className="text-sm leading-7 text-muted">{notice.body}</p>
              </div>
            </CardContent>
          </Card>
        ) : null}

        <div className="grid gap-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.2em] text-muted">
                项目列表
              </div>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight">选择一个项目进入工作台</h2>
            </div>
            <Button onClick={() => setIsCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              新建项目
            </Button>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {projects.map((project) => (
              <Card key={project.id} className="border-white/80 bg-white/95">
                <CardHeader className="pb-2">
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-sm text-muted">
                          <FolderKanban className="h-4 w-4" />
                          {project.scenario_type}
                        </div>
                        <CardTitle className="text-2xl">{project.name}</CardTitle>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2">
                        {project.seed_key ? <Badge variant="warning">默认演示项目</Badge> : null}
                        <Badge variant="accent">{project.status}</Badge>
                      </div>
                    </div>
                    <CardDescription className="text-sm leading-7">
                      {project.summary}
                    </CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-2">
                  <div className="space-y-1 text-sm text-muted">
                    <div>最近更新时间：{new Date(project.updated_at).toLocaleString('zh-CN')}</div>
                    {project.seed_key ? (
                      <div>默认案例作为一期演示基线保留，不提供删除。</div>
                    ) : (
                      <div>删除会同时清理项目资料、聊天沉淀和本地交付物。</div>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {!project.seed_key ? (
                      <Button
                        variant="secondary"
                        onClick={() => setProjectPendingDelete(project)}
                        disabled={deletingProjectId === project.id}
                        aria-label={`删除项目：${project.name}`}
                      >
                        {deletingProjectId === project.id ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="mr-2 h-4 w-4" />
                        )}
                        删除项目
                      </Button>
                    ) : null}
                    <Button asChild>
                      <Link to={`/projects/${project.id}/workbench`}>
                        进入工作台
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </Link>
                    </Button>
                  </div>
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
          <div className="grid gap-4 py-2">
            <Input
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="例如：集团业财逐笔对账需求分析"
            />
            <Input
              value={scenarioType}
              onChange={(event) => setScenarioType(event.target.value)}
              placeholder="例如：financial-reconciliation"
            />
            <Textarea
              value={projectSummary}
              onChange={(event) => setProjectSummary(event.target.value)}
              placeholder="用一句话说明这个项目想解决什么问题。"
              className="min-h-[160px]"
            />
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setIsCreateDialogOpen(false)} disabled={creating}>
                取消
              </Button>
              <Button
                onClick={() => void handleCreateProject()}
                disabled={creating || !projectName.trim() || !scenarioType.trim() || !projectSummary.trim()}
              >
                {creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                创建并进入工作台
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={projectPendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && deletingProjectId !== projectPendingDelete?.id) {
            setProjectPendingDelete(null);
          }
        }}
      >
        <DialogContent className="w-[min(560px,92vw)]">
          <DialogHeader>
            <DialogTitle>删除项目</DialogTitle>
            <DialogDescription>
              删除后会移除项目资料、聊天记录、状态沉淀和交付物文件。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="rounded-[20px] border border-rose-200 bg-rose-50 p-4 text-sm leading-7 text-rose-900">
              <div className="font-medium">即将删除：{projectPendingDelete?.name ?? '未选择项目'}</div>
              <div className="mt-2">
                这个操作不可撤销。如果证据层 collection 清理失败，系统会照常删除本地项目，并额外提示残留风险。
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <Button
                variant="secondary"
                onClick={() => setProjectPendingDelete(null)}
                disabled={deletingProjectId === projectPendingDelete?.id}
              >
                取消
              </Button>
              <Button
                variant="danger"
                onClick={() => void handleDeleteProject()}
                disabled={!projectPendingDelete || deletingProjectId === projectPendingDelete.id}
              >
                {deletingProjectId === projectPendingDelete?.id ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="mr-2 h-4 w-4" />
                )}
                确认删除项目
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
