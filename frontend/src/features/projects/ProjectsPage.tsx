import {
  ArrowRight,
  Bot,
  Brain,
  CheckCircle2,
  ClipboardList,
  FileText,
  FolderKanban,
  GitBranch,
  GitCompareArrows,
  Image as ImageIcon,
  Layers,
  Link2,
  ListChecks,
  Loader2,
  Mic,
  MousePointerClick,
  Notebook,
  Paperclip,
  Plus,
  ScrollText,
  Send,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Workflow,
} from 'lucide-react';
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
import { cn } from '../../lib/utils';
import type {
  ArtifactRecord,
  GlobalReadiness,
  ProjectState,
  ProjectSummary,
  ProviderReadiness,
} from '../../lib/types';
import {
  WORKBENCH_STAGE_LABELS,
  WORKBENCH_STAGE_ORDER,
  deriveStageState,
  type WorkbenchStage,
} from '../workbench/workbench-derived';

const SEED_PROJECT_ID = 'seed-reconciliation';

function readinessVariant(status: string) {
  if (status === 'ready') return 'success' as const;
  if (status.includes('required') || status.includes('not_configured')) return 'warning' as const;
  return 'default' as const;
}

function evidenceReadiness(readiness: GlobalReadiness | null) {
  return readiness?.evidence;
}

type ProjectsPageProps = {
  projects: ProjectSummary[];
  readiness: GlobalReadiness | null;
  seedProject: ProjectSummary | null;
  seedState: ProjectState | null;
  seedArtifacts: ArtifactRecord[];
  creating: boolean;
  onCreateProject: (payload: { name: string; scenario_type: string; summary: string }) => Promise<void>;
};

export function ProjectsPage({
  projects,
  readiness,
  seedProject,
  seedState,
  seedArtifacts,
  creating,
  onCreateProject,
}: ProjectsPageProps) {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [scenarioType, setScenarioType] = useState('');
  const [projectSummary, setProjectSummary] = useState('');

  async function handleCreateProject() {
    const name = projectName.trim();
    const scenario = scenarioType.trim();
    const summary = projectSummary.trim();
    if (!name || !scenario || !summary) return;

    await onCreateProject({ name, scenario_type: scenario, summary });
    setProjectName('');
    setScenarioType('');
    setProjectSummary('');
    setIsCreateDialogOpen(false);
  }

  return (
    <main className="min-h-screen px-6 py-12 text-nearBlack md:px-10">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-24">
        <HeroSection
          readiness={readiness}
          onOpenCreateDialog={() => setIsCreateDialogOpen(true)}
        />

        <SkillStackSection />

        <KnowledgeArchitectureSection />

        <MultimodalChatSection />

        <WorkbenchPreviewSection />

        <StageRailSection seedState={seedState} />

        <SedimentGridSection seedState={seedState} seedArtifacts={seedArtifacts} />

        <ArtifactPipelineSection />

        <MobileVoiceSection />

        <SeedFeaturedSection
          seedProject={seedProject}
          seedState={seedState}
          seedArtifacts={seedArtifacts}
        />

        <ProjectListSection
          projects={projects}
          onOpenCreateDialog={() => setIsCreateDialogOpen(true)}
        />

        <ReadinessFooter readiness={readiness} />
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

function SectionHead({
  overline,
  title,
  description,
  align = 'left',
}: {
  overline: string;
  title: string;
  description?: string;
  align?: 'left' | 'center';
}) {
  return (
    <div className={cn('flex flex-col gap-3', align === 'center' && 'items-center text-center')}>
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone">
        <span className="h-px w-6 bg-borderWarm" aria-hidden />
        {overline}
      </div>
      <h2 className="font-display text-balance text-[2rem] font-medium leading-[1.15] tracking-tightish text-nearBlack md:text-[2.4rem]">
        {title}
      </h2>
      {description ? (
        <p className={cn('max-w-2xl text-[15px] leading-[1.7] text-olive', align === 'center' && 'mx-auto')}>
          {description}
        </p>
      ) : null}
    </div>
  );
}

function ReadyPill({ label, status }: { label: string; status: string }) {
  const tone =
    status === 'ready'
      ? 'border-[#cdded0] bg-[#e6efe5] text-[#3d6b50]'
      : status.includes('required') || status.includes('not_configured')
        ? 'border-[#e6d3b3] bg-[#f5ead2] text-[#7a5a1d]'
        : 'border-borderWarm bg-ivory text-olive';
  const dotColor =
    status === 'ready'
      ? 'bg-[#5b8e6f]'
      : status.includes('required') || status.includes('not_configured')
        ? 'bg-[#c79743]'
        : 'bg-stone';
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-[11px] font-medium', tone)}>
      <span className={cn('h-1.5 w-1.5 rounded-full', dotColor)} aria-hidden />
      {label} · {status}
    </span>
  );
}

function HeroSection({
  readiness,
  onOpenCreateDialog,
}: {
  readiness: GlobalReadiness | null;
  onOpenCreateDialog: () => void;
}) {
  return (
    <section className="grid gap-10 md:grid-cols-[1.55fr_0.85fr] md:items-end">
      <div className="space-y-6">
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.22em] text-stone">
          <Sparkles className="h-3.5 w-3.5 text-terracotta" />
          Fullstack Phase 1
        </div>
        <h1 className="font-display text-balance text-[3rem] font-medium leading-[1.05] tracking-tightish text-nearBlack md:text-[3.75rem]">
          客户需求转译台
        </h1>
        <p className="max-w-2xl text-[1.05rem] leading-[1.65] text-olive md:text-[1.15rem]">
          把模糊诉求讲清楚 ·
          <span className="px-1 text-nearBlack">方法论 + 智能体 + 多模态对话</span>
          的需求分析工作台。
        </p>
        <div className="flex flex-wrap gap-2">
          {readiness?.claude ? (
            <ReadyPill label="Claude Agent SDK" status={readiness.claude.status} />
          ) : null}
          {evidenceReadiness(readiness) ? (
            <ReadyPill label="项目知识库 RAG" status={evidenceReadiness(readiness)!.status} />
          ) : null}
          <ReadyPill label="LLM Wiki" status="ready" />
        </div>
        <div className="flex flex-wrap gap-3 pt-2">
          <Button asChild size="lg">
            <Link to={`/projects/${SEED_PROJECT_ID}/workbench`}>
              进入业财对账演示
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button variant="secondary" size="lg" onClick={onOpenCreateDialog}>
            <Plus className="h-4 w-4" />
            新建项目
          </Button>
        </div>
      </div>

      <aside className="rounded-[18px] border border-borderCream bg-ivory p-6 shadow-whisper">
        <div className="mb-3 text-[11px] font-medium uppercase tracking-[0.18em] text-stone">方法论金句</div>
        <blockquote className="font-display text-[1.35rem] italic leading-[1.45] text-nearBlack">
          "分析优先，生成其次；
          <br />
          AI 起草，人确认排版。"
        </blockquote>
        <div className="mt-4 flex items-center gap-2 text-[12px] text-stone">
          <ScrollText className="h-3.5 w-3.5" />
          backend/.claude/skills/requirement-analysis-methodology
        </div>
      </aside>
    </section>
  );
}

const SKILL_CARDS = [
  {
    file: 'requirement-analysis-methodology',
    title: '需求分析方法论',
    badge: 'method skill',
    icon: ListChecks,
    bullets: ['5 阶段推进', '7 类沉淀分桶', 'revisit 触发条件'],
  },
  {
    file: 'rag-evidence-workflow',
    title: 'RAG 证据工作流',
    badge: 'evidence skill',
    icon: ShieldCheck,
    bullets: ['source 入库摘要', 'grounding 检索', 'citation 强约束'],
  },
  {
    file: 'artifact-generation-guidelines',
    title: '交付物生成指南',
    badge: 'artifact skill',
    icon: Layers,
    bullets: ['document / page_solution / interaction_flow', '何时生成 · 何时拒绝', 'grounded-only 输出'],
  },
] as const;

function SkillStackSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="智能体内核"
        title="把方法论写进智能体"
        description="三份 Claude Skill 同时挂载，agent 每轮自动读，方法论不再藏在 prompt 里。"
      />
      <div className="grid gap-4 md:grid-cols-3">
        {SKILL_CARDS.map((skill) => {
          const Icon = skill.icon;
          return (
            <div
              key={skill.file}
              className="group flex h-full flex-col gap-4 rounded-[18px] border border-borderCream bg-ivory p-5 transition-shadow duration-200 hover:shadow-whisper"
            >
              <div className="flex items-start justify-between gap-3">
                <Icon className="h-5 w-5 text-terracotta" />
                <Badge>{skill.badge}</Badge>
              </div>
              <div className="space-y-2">
                <div className="font-mono text-[11px] leading-tight text-stone break-all">{skill.file}</div>
                <h3 className="font-display text-[1.35rem] font-medium leading-tight text-nearBlack">
                  {skill.title}
                </h3>
              </div>
              <ul className="mt-1 space-y-1.5 text-[14px] leading-[1.6] text-olive">
                {skill.bullets.map((bullet) => (
                  <li key={bullet} className="flex items-start gap-2">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-terracotta/70" aria-hidden />
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      <p className="text-center text-[13px] italic leading-[1.6] text-stone">
        三块互锁，agent runtime 在 <span className="font-mono not-italic text-charcoal">backend/.claude/skills/</span> 自动发现。
      </p>
    </section>
  );
}

function KnowledgeArchitectureSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="知识架构"
        title="证据 + 长期理解，双层共存"
        description="项目知识库 RAG 给客观 grounding，LLM Wiki 攒可修订的工作理解 —— 互相补位，不互相替代。"
      />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-[20px] border border-borderCream bg-ivory p-6 shadow-whisper">
          <div className="flex items-start justify-between gap-3">
            <Notebook className="h-6 w-6 text-terracotta" />
            <Badge>证据 grounding 层</Badge>
          </div>
          <h3 className="mt-4 font-display text-[1.5rem] font-medium leading-tight text-nearBlack">
            项目知识库 RAG
          </h3>
          <p className="mt-2 text-[14px] leading-[1.6] text-olive">
            每一条结论都能回到原文 —— 客户改主意时，最容易找到差异点的就是这一层。
          </p>
          <div className="mt-5 grid gap-2 text-[14px] leading-[1.6] text-charcoal">
            <KnowledgeRow label="Docling" value="文档解析（PDF · DOCX · XLSX · MD · 图片 OCR）" />
            <KnowledgeRow label="Qdrant" value="向量化检索 + 项目级隔离" />
            <KnowledgeRow label="LlamaIndex" value="grounding + citation 追溯" />
          </div>
        </div>

        <div className="rounded-[20px] border border-borderCream bg-ivory p-6 shadow-whisper">
          <div className="flex items-start justify-between gap-3">
            <Brain className="h-6 w-6 text-terracotta" />
            <Badge>长期理解层</Badge>
          </div>
          <h3 className="mt-4 font-display text-[1.5rem] font-medium leading-tight text-nearBlack">
            LLM Wiki
          </h3>
          <p className="mt-2 text-[14px] leading-[1.6] text-olive">
            项目内 markdown 知识页，沉淀长期工作理解。Agent 每轮自带，作为"连续记忆"。
          </p>
          <div className="mt-5 grid gap-2 text-[14px] leading-[1.6] text-charcoal">
            <KnowledgeRow label="overview" value="项目背景 · 当前理解" />
            <KnowledgeRow label="intake" value="source 摘要索引" />
            <KnowledgeRow label="rules" value="业务规则 · 冲突 · 待验证口径" />
          </div>
        </div>
      </div>
      <p className="text-center text-[13px] italic leading-[1.6] text-stone">
        互补不替代 —— grounding 不可替代，wiki 提供持续上下文。
      </p>
    </section>
  );
}

function KnowledgeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[100px_minmax(0,1fr)] items-baseline gap-3 border-t border-borderCream pt-2 first:border-t-0 first:pt-0">
      <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">{label}</div>
      <div>{value}</div>
    </div>
  );
}

const MULTIMODAL_INPUTS = [
  { icon: ClipboardList, label: '文本' },
  { icon: Paperclip, label: '文件 PDF · DOCX · XLSX · MD' },
  { icon: ImageIcon, label: '截图' },
  { icon: Link2, label: '链接' },
  { icon: Mic, label: '语音 · realtime' },
] as const;

function MultimodalChatSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="和客户对话的姿态"
        title="让客户不抗拒地把上下文丢进来"
        description="智能体不止回答，会主动引导分析、归档沉淀；客户的会议纪要、PDF、截图、链接、语音都直接喂进来就行。"
      />
      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <div className="rounded-[20px] border border-borderCream bg-ivory p-5 shadow-whisper">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone">客户输入</div>
          <div className="mt-4 rounded-[14px] border border-borderWarm bg-parchment/60 p-4">
            <div className="text-[13px] leading-[1.6] text-charcoal">
              "我们订单系统和财务系统对账，两边总有几毛钱差。下个月 PPT 要给老板看…"
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {MULTIMODAL_INPUTS.map((input) => {
                const Icon = input.icon;
                return (
                  <span
                    key={input.label}
                    className="inline-flex items-center gap-1.5 rounded-full border border-borderWarm bg-ivory px-2.5 py-[3px] text-[11px] text-charcoal"
                  >
                    <Icon className="h-3 w-3 text-terracotta" />
                    {input.label}
                  </span>
                );
              })}
            </div>
          </div>
          <p className="mt-4 text-[13px] leading-[1.6] text-stone">
            客户怎么舒服怎么来 —— 文本、附件、截图、链接、随手语音。
          </p>
        </div>

        <div className="rounded-[20px] border border-borderCream bg-ivory p-5 shadow-whisper">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone">智能体行动</div>
          <div className="mt-4 space-y-3">
            <div className="flex items-start gap-2 rounded-[14px] border border-borderCream bg-parchment/60 p-3">
              <Bot className="mt-0.5 h-4 w-4 shrink-0 text-terracotta" />
              <div className="text-[14px] leading-[1.6] text-charcoal">
                <strong className="font-medium">先确认范围：</strong>
                差异是单笔级还是日终汇总？是金额、笔数、还是科目？两边的数据是定时拉取还是实时？
              </div>
            </div>
            <div className="flex items-start gap-2 rounded-[10px] border border-[#cdded0] bg-[#e6efe5] px-2.5 py-2 text-[12px] leading-[1.55] text-[#3d6b50]">
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-80" />
              <span>
                自动写入 <strong>关键待确认</strong>：差异口径（单笔 vs 日终）· 取数时点 · 科目映射
              </span>
            </div>
          </div>
          <p className="mt-4 text-[13px] leading-[1.6] text-stone">
            主动追问 + 自动归档沉淀 —— 客户不需要会用产品，只需要能聊。
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-[14px] border border-dashed border-borderWarm bg-parchment/40 px-4 py-3 text-[13px] leading-[1.6] text-charcoal">
        <Smartphone className="h-4 w-4 shrink-0 text-terracotta" />
        <div className="flex-1">
          <span className="font-medium text-nearBlack">移动端 + 实时语音</span>
          <span className="ml-2 text-stone">客户在路上、会议间隙也能讲，语音直接落入项目沉淀。</span>
        </div>
        <Badge variant="warning">Coming soon</Badge>
      </div>
    </section>
  );
}

const WORKBENCH_PANES = [
  {
    icon: FolderKanban,
    title: 'Sources',
    desc: '资料导入 → Docling 解析 → Qdrant 索引；多格式、多文件、失败可重试。',
  },
  {
    icon: Send,
    title: 'Chat',
    desc: 'SSE 流式对话 + citation；助手主动追问，每轮把结论自动归档到右栏。',
  },
  {
    icon: GitBranch,
    title: 'Project State',
    desc: '7 类沉淀总集 + 5 阶段 rail，新信息回流时自动 revisit 对应阶段。',
  },
] as const;

function WorkbenchPreviewSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="工作台"
        title="Sources · Chat · Project State"
        description="不是 chatbot —— 三栏一体的需求分析工作台，资料、对话、沉淀同步推进。"
      />
      <div className="grid gap-4 md:grid-cols-3">
        {WORKBENCH_PANES.map((pane) => {
          const Icon = pane.icon;
          return (
            <div key={pane.title} className="rounded-[18px] border border-borderCream bg-ivory p-5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-accentSoft">
                  <Icon className="h-4 w-4 text-terracotta" />
                </span>
                <h3 className="font-display text-[1.15rem] font-medium leading-tight text-nearBlack">
                  {pane.title}
                </h3>
              </div>
              <p className="mt-3 text-[14px] leading-[1.65] text-olive">{pane.desc}</p>
            </div>
          );
        })}
      </div>
      <p className="text-center text-[13px] text-stone">
        想直接看？跳到下面的 <span className="font-medium text-terracotta">业财对账 demo →</span>
      </p>
    </section>
  );
}

function StageRailSection({ seedState }: { seedState: ProjectState | null }) {
  const { primaryStage, revisitingStages } = seedState
    ? deriveStageState(seedState)
    : { primaryStage: 'requirement_alignment' as WorkbenchStage, revisitingStages: [] as WorkbenchStage[] };
  const primaryIndex = WORKBENCH_STAGE_ORDER.indexOf(primaryStage);

  return (
    <section className="space-y-8">
      <SectionHead
        overline="工作流"
        title="5 阶段推进，可 revisit"
        description="从需求接入一路推到设计交付。新信息回流时，rail 自动重回对应阶段，不强制线性。"
      />
      <div className="rounded-[20px] border border-borderCream bg-ivory p-6 shadow-whisper">
        <div className="grid grid-cols-5 gap-2">
          {WORKBENCH_STAGE_ORDER.map((stage, index) => {
            const isActive = stage === primaryStage;
            const isDone = index < primaryIndex;
            const isRevisit = revisitingStages.includes(stage);
            return (
              <div key={stage} className="flex flex-col items-center gap-2 text-center">
                <div
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-full border text-[13px] font-semibold',
                    isActive && 'border-terracotta bg-terracotta text-ivory shadow-[0_0_0_4px_rgba(201,100,66,0.18)]',
                    !isActive && isDone && 'border-[#cdded0] bg-[#e6efe5] text-[#3d6b50]',
                    !isActive && !isDone && isRevisit && 'border-[#e6d3b3] bg-[#f5ead2] text-[#7a5a1d]',
                    !isActive && !isDone && !isRevisit && 'border-borderWarm bg-parchment text-stone'
                  )}
                >
                  {index + 1}
                </div>
                <div
                  className={cn(
                    'font-display text-[14px] leading-tight',
                    isActive ? 'text-nearBlack' : 'text-charcoal'
                  )}
                >
                  {WORKBENCH_STAGE_LABELS[stage]}
                </div>
                {isActive ? (
                  <Badge variant="accent">当前重点</Badge>
                ) : isRevisit ? (
                  <Badge variant="warning">补充中</Badge>
                ) : isDone ? (
                  <Badge variant="success">已形成</Badge>
                ) : (
                  <span className="text-[11px] text-stone">待进入</span>
                )}
              </div>
            );
          })}
        </div>
        <div className="mt-5 flex items-center gap-2 border-t border-borderCream pt-4 text-[13px] leading-[1.6] text-olive">
          <Workflow className="h-4 w-4 shrink-0 text-terracotta" />
          不是线性流水线 —— 新信息回流时自动重回对应阶段。
        </div>
      </div>
    </section>
  );
}

const SEDIMENT_TILES = [
  {
    key: 'current_understanding',
    title: '当前需求定义',
    desc: '主线理解与问题定义。',
    pick: (s: ProjectState) => s.current_understanding.length,
  },
  {
    key: 'pending_items',
    title: '关键待确认',
    desc: '边界、口径、规则的 open question。',
    pick: (s: ProjectState) => s.pending_items.length,
  },
  {
    key: 'confirmed_items',
    title: '已确认项',
    desc: '客户拍板锁定的事实。',
    pick: (s: ProjectState) => s.confirmed_items.length,
  },
  {
    key: 'conflict_items',
    title: '风险与冲突',
    desc: '识别出的不一致与风险。',
    pick: (s: ProjectState) => s.conflict_items.length,
  },
  {
    key: 'mvp_items',
    title: 'MVP 结论',
    desc: '收敛后的方案方向。',
    pick: (s: ProjectState) => s.mvp_items.length,
  },
  {
    key: 'versions',
    title: '版本快照',
    desc: '关键轮次的状态归档。',
    pick: (s: ProjectState) => s.versions.length,
  },
  {
    key: 'artifacts',
    title: '交付物',
    desc: '文档稿 / 页面方案 / 交互稿。',
    pick: (s: ProjectState) => s.artifacts.length,
  },
] as const;

function SedimentGridSection({
  seedState,
  seedArtifacts,
}: {
  seedState: ProjectState | null;
  seedArtifacts: ArtifactRecord[];
}) {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="项目状态总集"
        title="7 类沉淀，每条都能回到资料"
        description="一次对话，多类归档。每个桶都有自己的语义，combine 起来就是项目当前状态的全貌。"
      />
      <div className="grid gap-3 md:grid-cols-4">
        {SEDIMENT_TILES.map((tile) => {
          const count = seedState
            ? tile.key === 'artifacts'
              ? seedArtifacts.length
              : tile.pick(seedState)
            : null;
          return (
            <div key={tile.key} className="rounded-[14px] border border-borderCream bg-ivory p-4">
              <h3 className="font-display text-[1.05rem] font-medium leading-tight text-nearBlack">
                {tile.title}
              </h3>
              <p className="mt-2 text-[13px] leading-[1.6] text-olive">{tile.desc}</p>
              <div className="mt-3 flex items-center justify-between text-[11px] uppercase tracking-[0.12em] text-stone">
                <span>业财对账 seed</span>
                <span className="font-mono text-[13px] normal-case tracking-normal text-charcoal">
                  {count ?? '—'} 条
                </span>
              </div>
            </div>
          );
        })}
        <Link
          to={`/projects/${SEED_PROJECT_ID}/workbench`}
          className="group flex items-center justify-between gap-2 rounded-[14px] border border-dashed border-borderWarm bg-parchment/50 p-4 text-[13px] leading-[1.6] text-charcoal transition hover:border-terracotta/40 hover:bg-accentSoft/40"
        >
          <span className="font-medium text-nearBlack">进入 seed workbench</span>
          <ArrowRight className="h-4 w-4 text-terracotta transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </section>
  );
}

const ARTIFACT_CARDS = [
  {
    title: '需求文档',
    type: 'document',
    icon: FileText,
    tag: 'Markdown · Word',
    desc: '正式可交付的需求说明，章节、来源引用、评审建议齐全。',
  },
  {
    title: '页面方案',
    type: 'page_solution',
    icon: ImageIcon,
    tag: 'gpt-image-2 → HTML',
    desc: '极快预览精美设计稿；agent 把视觉稿生成为可嵌入的 HTML。',
  },
  {
    title: '交互稿',
    type: 'interaction_flow',
    icon: MousePointerClick,
    tag: 'HTML 可点',
    desc: '可点开真用的小原型，客户摸一摸就能消除对功能的歧义。',
  },
] as const;

function ArtifactPipelineSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="交付物"
        title="从精美静态稿到可点击 demo，一次生成"
        description="文档、页面、交互三件套，全部 grounded 在已经入库的 source 上 —— 不靠想象。"
      />
      <div className="grid gap-4 md:grid-cols-3">
        {ARTIFACT_CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.type}
              className="flex h-full flex-col gap-4 rounded-[18px] border border-borderCream bg-ivory p-5 shadow-whisper"
            >
              <div className="flex items-start justify-between gap-3">
                <Icon className="h-5 w-5 text-terracotta" />
                <Badge variant="accent">{card.tag}</Badge>
              </div>
              <div>
                <h3 className="font-display text-[1.35rem] font-medium leading-tight text-nearBlack">
                  {card.title}
                </h3>
                <div className="mt-1 font-mono text-[11px] text-stone">{card.type}</div>
              </div>
              <p className="text-[14px] leading-[1.65] text-olive">{card.desc}</p>
            </div>
          );
        })}
      </div>
      <p className="text-center text-[13px] italic leading-[1.6] text-stone">
        客户能直接点的 demo，比一千句需求描述都管用。
      </p>
    </section>
  );
}

function MobileVoiceSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="下一步"
        title="移动端 · 实时语音 · 随手沉淀"
        description="客户在路上、在会议间隙也能讲；语音直接落入项目沉淀，不丢一个想法。"
      />
      <div className="grid gap-6 lg:grid-cols-[0.7fr_1fr] lg:items-center">
        <div className="flex justify-center">
          <div className="relative w-[220px] rounded-[34px] border border-borderCream bg-ivory p-4 shadow-whisper">
            <div className="absolute left-1/2 top-2 h-1 w-12 -translate-x-1/2 rounded-full bg-borderWarm" />
            <div className="mt-6 space-y-3">
              <div className="rounded-[14px] border border-borderCream bg-parchment/60 px-3 py-2 text-[12px] leading-[1.55] text-charcoal">
                客户：你看我刚才说的那个发货单 …
              </div>
              <div className="rounded-[14px] bg-accentSoft px-3 py-2 text-[12px] leading-[1.55] text-nearBlack shadow-[0_0_0_1px_rgba(201,100,66,0.18)]">
                <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.16em] text-[#7a3a22]">
                  <Mic className="h-3 w-3" /> 实时音频 · 0:32
                </div>
                <div className="flex items-end gap-0.5">
                  {Array.from({ length: 22 }).map((_, idx) => (
                    <span
                      key={idx}
                      className="block w-[3px] rounded-full bg-terracotta/70"
                      style={{ height: `${6 + ((idx * 7) % 18)}px` }}
                    />
                  ))}
                </div>
              </div>
              <div className="rounded-[10px] border border-[#cdded0] bg-[#e6efe5] px-3 py-2 text-[11px] leading-[1.5] text-[#3d6b50]">
                ✓ 转写已写入 当前需求定义
              </div>
            </div>
          </div>
        </div>
        <div className="space-y-4">
          <Badge variant="warning">Coming soon</Badge>
          <h3 className="font-display text-[1.5rem] font-medium leading-tight text-nearBlack">
            把客户的"随口一说"也接进来
          </h3>
          <p className="text-[15px] leading-[1.7] text-olive">
            移动端常驻、实时音频转写，客户在车上、电梯里、会议间隙的灵感不再靠"等回去再补一段"。
            语音直接落入项目沉淀，agent 当轮就能根据它追问。
          </p>
          <ul className="space-y-2 text-[14px] leading-[1.6] text-charcoal">
            <li className="flex items-start gap-2">
              <Mic className="mt-1 h-3.5 w-3.5 shrink-0 text-terracotta" />
              <span>实时音频对话，断断续续也能拼接</span>
            </li>
            <li className="flex items-start gap-2">
              <Smartphone className="mt-1 h-3.5 w-3.5 shrink-0 text-terracotta" />
              <span>移动端 PWA，扫码就能跳进同一个 project</span>
            </li>
            <li className="flex items-start gap-2">
              <GitCompareArrows className="mt-1 h-3.5 w-3.5 shrink-0 text-terracotta" />
              <span>desktop / mobile 同一份沉淀，差异自动 merge</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}

function SeedFeaturedSection({
  seedProject,
  seedState,
  seedArtifacts,
}: {
  seedProject: ProjectSummary | null;
  seedState: ProjectState | null;
  seedArtifacts: ArtifactRecord[];
}) {
  if (!seedProject) {
    return (
      <section className="space-y-6">
        <SectionHead overline="Seed Demo" title="业财对账 · 演示项目" />
        <div className="rounded-[20px] border border-dashed border-borderWarm bg-ivory/60 p-8 text-center text-[14px] leading-[1.6] text-stone">
          演示数据加载中…后端 ready 后会自动展示业财对账 seed 项目。
        </div>
      </section>
    );
  }

  const { primaryStage } = seedState
    ? deriveStageState(seedState)
    : { primaryStage: 'requirement_alignment' as WorkbenchStage };
  const primaryIndex = WORKBENCH_STAGE_ORDER.indexOf(primaryStage);

  const sedimentCount = seedState
    ? seedState.current_understanding.length +
      seedState.pending_items.length +
      seedState.confirmed_items.length +
      seedState.conflict_items.length +
      seedState.mvp_items.length
    : 0;
  const sourceCount = seedState ? new Set(
    [
      ...seedState.current_understanding,
      ...seedState.pending_items,
      ...seedState.confirmed_items,
      ...seedState.conflict_items,
      ...seedState.mvp_items,
    ].flatMap((item) => item.source_ids)
  ).size : 0;

  return (
    <section className="space-y-6">
      <SectionHead
        overline="Seed Demo"
        title="一个真案子在跑：业财对账"
        description="点进去就能看到沉淀总集、阶段 rail 和真实生成的交付物 —— 别只看截图。"
      />
      <div className="overflow-hidden rounded-[24px] border border-borderCream bg-ivory shadow-whisper">
        <div className="grid gap-0 md:grid-cols-[1fr_auto]">
          <div className="border-l-[6px] border-terracotta p-7">
            <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-stone">
              <FolderKanban className="h-3.5 w-3.5" />
              {seedProject.scenario_type}
              <span className="text-borderWarm">·</span>
              <span>最近更新 {new Date(seedProject.updated_at).toLocaleDateString('zh-CN')}</span>
            </div>
            <h3 className="mt-3 font-display text-[1.85rem] font-medium leading-[1.2] text-nearBlack">
              {seedProject.name}
            </h3>
            <p className="mt-3 max-w-xl text-[15px] leading-[1.7] text-olive">{seedProject.summary}</p>

            <div className="mt-6 flex items-center gap-2">
              {WORKBENCH_STAGE_ORDER.map((stage, index) => {
                const isActive = stage === primaryStage;
                const isDone = index < primaryIndex;
                return (
                  <div key={stage} className="flex items-center gap-2">
                    <span
                      className={cn(
                        'flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-semibold',
                        isActive && 'border-terracotta bg-terracotta text-ivory',
                        !isActive && isDone && 'border-[#cdded0] bg-[#e6efe5] text-[#3d6b50]',
                        !isActive && !isDone && 'border-borderWarm bg-parchment text-stone'
                      )}
                    >
                      {index + 1}
                    </span>
                    {index < WORKBENCH_STAGE_ORDER.length - 1 ? (
                      <span className="h-px w-5 bg-borderWarm" />
                    ) : null}
                  </div>
                );
              })}
              <span className="ml-2 text-[12px] text-charcoal">
                当前 · <span className="font-medium text-nearBlack">{WORKBENCH_STAGE_LABELS[primaryStage]}</span>
              </span>
            </div>

            <div className="mt-6 flex flex-wrap gap-3 text-[13px] leading-[1.6] text-charcoal">
              <Stat label="沉淀" value={`${sedimentCount} 条`} />
              <Stat label="交付物" value={`${seedArtifacts.length} 份`} />
              <Stat label="引用资料" value={`${sourceCount} 份`} />
            </div>
          </div>
          <div className="flex items-center justify-end p-7 md:border-l md:border-borderCream">
            <Button asChild size="lg">
              <Link to={`/projects/${seedProject.id}/workbench`}>
                进入演示工作台
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[10px] border border-borderCream bg-parchment/60 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.18em] text-stone">{label}</div>
      <div className="mt-0.5 font-mono text-[13px] text-nearBlack">{value}</div>
    </div>
  );
}

function ProjectListSection({
  projects,
  onOpenCreateDialog,
}: {
  projects: ProjectSummary[];
  onOpenCreateDialog: () => void;
}) {
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone">你的项目</div>
          <h2 className="mt-2 font-display text-[1.85rem] font-medium leading-tight tracking-tightish text-nearBlack">
            选择一个项目进入工作台
          </h2>
        </div>
        <Button variant="secondary" onClick={onOpenCreateDialog}>
          <Plus className="h-4 w-4" />
          再开一个
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {projects.map((project) => (
          <Card
            key={project.id}
            className="group border-borderCream bg-ivory transition-shadow duration-150 hover:shadow-[0_8px_32px_-18px_rgba(20,20,19,0.18)]"
          >
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
                <CardDescription className="text-[15px] leading-[1.6]">{project.summary}</CardDescription>
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
    </section>
  );
}

function ReadinessFooter({ readiness }: { readiness: GlobalReadiness | null }) {
  const wikiReadiness: ProviderReadiness = {
    provider: 'LLM_WIKI',
    status: 'ready',
    summary: 'LLM Wiki 项目内 markdown 知识页层已就绪。',
    detail: null,
    action_label: null,
  };

  const providers: Array<{ icon: typeof Sparkles; label: string; data: ProviderReadiness | null }> = [
    { icon: Sparkles, label: 'Claude Agent SDK', data: readiness?.claude ?? null },
    { icon: Notebook, label: '项目知识库 RAG', data: evidenceReadiness(readiness) ?? null },
    { icon: Brain, label: 'LLM Wiki', data: wikiReadiness },
  ];

  return (
    <section className="space-y-5 border-t border-borderCream pt-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-stone">Provider Readiness</div>
          <h2 className="mt-2 font-display text-[1.5rem] font-medium leading-tight text-nearBlack">
            真 provider · 真状态
          </h2>
        </div>
        <p className="max-w-xl text-[13px] leading-[1.6] text-stone">
          这里直接显示后端 readiness 接口的状态。失败就报失败，未配置就报未配置 —— 没有静默 fallback。
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {providers.map((provider) => {
          const Icon = provider.icon;
          const data = provider.data;
          return (
            <div key={provider.label} className="rounded-[14px] border border-borderCream bg-ivory p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-terracotta" />
                  <span className="font-medium text-nearBlack">{provider.label}</span>
                </div>
                {data ? (
                  <Badge variant={readinessVariant(data.status)}>{data.status}</Badge>
                ) : (
                  <Badge>—</Badge>
                )}
              </div>
              <p className="mt-2 text-[13px] leading-[1.6] text-olive">
                {data?.summary ?? '状态加载中…'}
              </p>
            </div>
          );
        })}
      </div>
      <p className="text-center text-[12px] italic text-stone">
        失败就报失败，未配置就报未配置 —— 没有静默 fallback。
      </p>
    </section>
  );
}

