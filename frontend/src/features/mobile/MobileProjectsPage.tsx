import { ArrowRight, Laptop2, Loader2, Plus, Radio, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import {
  createProject,
  getGlobalReadiness,
  initProjectKnowledgeBase,
  listProjects,
} from '../../lib/api';
import type { GlobalReadiness, ProjectSummary } from '../../lib/types';

function readinessVariant(status: string) {
  if (status === 'ready') return 'success' as const;
  if (status.includes('required') || status.includes('not_configured')) return 'warning' as const;
  return 'default' as const;
}

export function MobileProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [readiness, setReadiness] = useState<GlobalReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [scenarioType, setScenarioType] = useState('');
  const [projectSummary, setProjectSummary] = useState('');

  useEffect(() => {
    void loadPage();
  }, []);

  async function loadPage() {
    setLoading(true);
    setError(null);
    try {
      const [nextProjects, nextReadiness] = await Promise.all([listProjects(), getGlobalReadiness()]);
      setProjects(nextProjects);
      setReadiness(nextReadiness);
    } catch (err) {
      setError(err instanceof Error ? err.message : '手机端项目列表加载失败。');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateProject() {
    const name = projectName.trim();
    const scenario = scenarioType.trim();
    const summary = projectSummary.trim();
    if (!name || !scenario || !summary) return;

    setCreating(true);
    setError(null);
    try {
      const project = await createProject({
        name,
        scenario_type: scenario,
        summary,
      });
      if (readiness?.evidence.status === 'ready') {
        await initProjectKnowledgeBase(project.id);
      }
      setProjects((current) => [project, ...current]);
      setProjectName('');
      setScenarioType('');
      setProjectSummary('');
      setIsCreateDialogOpen(false);
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建项目失败。');
    } finally {
      setCreating(false);
    }
  }

  const projectCountLabel = useMemo(() => `${projects.length} 个项目`, [projects.length]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[radial-gradient(circle_at_top,#ffe5d5,transparent_40%),linear-gradient(180deg,#f7efe8_0%,#efe3d8_100%)] px-4 py-5 text-nearBlack">
        <div className="mx-auto flex min-h-[78vh] max-w-md items-center justify-center rounded-[30px] border border-[#ead9cd] bg-ivory shadow-[0_24px_80px_-42px_rgba(45,25,13,0.45)]">
          <Loader2 className="h-5 w-5 animate-spin text-terracotta" />
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,#ffe6d8,transparent_40%),linear-gradient(180deg,#f8f0e9_0%,#efe3d8_100%)] px-4 py-5 text-nearBlack">
      <div className="mx-auto flex w-full max-w-md flex-col gap-4">
        <section className="overflow-hidden rounded-[30px] border border-[#ead9cd] bg-[linear-gradient(165deg,#fffaf6_0%,#f8eee5_58%,#ffe2d1_100%)] p-5 shadow-[0_24px_80px_-42px_rgba(45,25,13,0.45)]">
          <div className="flex items-center justify-between gap-3">
            <Badge variant="accent">手机端工作台</Badge>
            <Button asChild variant="ghost" size="sm" className="h-9 rounded-full px-3">
              <Link to="/desktop">
                <Laptop2 className="h-4 w-4" />
                桌面版
              </Link>
            </Button>
          </div>

          <div className="mt-4">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-stone">
              <Sparkles className="h-3.5 w-3.5 text-terracotta" />
              客户需求转译台
            </div>
            <h1 className="mt-2 font-display text-[2rem] leading-[1.06] text-nearBlack">
              手机端项目列表
            </h1>
            <p className="mt-3 text-[14px] leading-6 text-olive">
              这里只保留最短路径：选项目、建项目、直接进入实时语音访谈。
            </p>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {readiness?.evidence ? (
              <Badge variant={readinessVariant(readiness.evidence.status)}>
                项目知识库 · {readiness.evidence.status}
              </Badge>
            ) : null}
            {readiness?.claude ? (
              <Badge variant={readinessVariant(readiness.claude.status)}>
                智能体 · {readiness.claude.status}
              </Badge>
            ) : null}
          </div>

          <div className="mt-5 grid grid-cols-[1fr_auto] gap-3 rounded-[24px] border border-[#eddcd0] bg-white/70 p-4">
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-stone">当前项目</div>
              <div className="mt-1 text-lg font-medium text-nearBlack">{projectCountLabel}</div>
              <div className="mt-2 text-sm leading-6 text-stone">
                创建后会直接进入该项目的语音访谈页。
              </div>
            </div>
            <Button
              className="h-auto rounded-[20px] px-4 py-3"
              onClick={() => setIsCreateDialogOpen(true)}
            >
              <Plus className="h-4 w-4" />
              创建项目
            </Button>
          </div>
        </section>

        {error ? (
          <section className="rounded-[24px] border border-[#e7c9c2] bg-[#fbeeec] px-4 py-3 text-sm leading-6 text-errorWarm">
            {error}
          </section>
        ) : null}

        <section className="rounded-[28px] border border-[#ead9cd] bg-ivory p-4 shadow-[0_20px_60px_-42px_rgba(45,25,13,0.35)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-stone">项目列表</div>
              <div className="mt-1 text-base font-medium text-nearBlack">打开一个项目继续聊</div>
            </div>
            <Radio className="h-4 w-4 text-terracotta" />
          </div>

          <div className="grid gap-3">
            {projects.map((project) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className="group rounded-[22px] border border-[#eadcd1] bg-[linear-gradient(180deg,#fffdf9_0%,#faf2e9_100%)] px-4 py-4 transition hover:border-[#d9b7a1]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[11px] uppercase tracking-[0.16em] text-stone">
                      {project.scenario_type}
                    </div>
                    <div className="mt-1 text-[16px] font-medium leading-6 text-nearBlack">
                      {project.name}
                    </div>
                  </div>
                  <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-terracotta transition group-hover:translate-x-0.5" />
                </div>
                <p className="mt-2 text-[13px] leading-6 text-olive">{project.summary}</p>
                <div className="mt-3 text-[11px] uppercase tracking-[0.16em] text-stone">
                  最近更新 · {new Date(project.updated_at).toLocaleString('zh-CN')}
                </div>
              </Link>
            ))}

            {projects.length === 0 ? (
              <div className="rounded-[20px] border border-dashed border-[#dfc6b6] bg-white px-4 py-6 text-center text-sm leading-6 text-stone">
                还没有项目，先创建一个，就能直接开始手机端语音访谈。
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="w-[min(92vw,520px)]">
          <DialogHeader>
            <DialogTitle>创建项目</DialogTitle>
            <DialogDescription>
              这里依旧通过弹窗填写信息。创建完成后直接进入这个项目的语音访谈页。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone">项目名</span>
              <Input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                placeholder="例如：门店巡检需求澄清"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone">场景类型</span>
              <Input
                value={scenarioType}
                onChange={(event) => setScenarioType(event.target.value)}
                placeholder="例如：retail-inspection"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone">一句话摘要</span>
              <Textarea
                value={projectSummary}
                onChange={(event) => setProjectSummary(event.target.value)}
                placeholder="用一句话说明这个项目现在最想澄清什么。"
                className="min-h-[132px]"
              />
            </label>
            <div className="mt-1 flex justify-end gap-2">
              <Button
                variant="ghost"
                onClick={() => setIsCreateDialogOpen(false)}
                disabled={creating}
              >
                取消
              </Button>
              <Button
                onClick={() => void handleCreateProject()}
                disabled={
                  creating ||
                  !projectName.trim() ||
                  !scenarioType.trim() ||
                  !projectSummary.trim()
                }
              >
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                创建并进入
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
