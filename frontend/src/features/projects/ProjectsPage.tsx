import {
  ArrowRight,
  Bot,
  Brain,
  CheckCircle2,
  ClipboardList,
  FileText,
  FolderKanban,
  GitBranch,
  HelpCircle,
  Image as ImageIcon,
  Layers,
  Link2,
  ListChecks,
  Loader2,
  MessageSquare,
  Mic,
  MousePointerClick,
  Package,
  Paperclip,
  Plus,
  Send,
  ShieldAlert,
  Smartphone,
  Sparkles,
  Users,
  Workflow,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
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

        <PainPointsSection />

        <WorkbenchPreviewSection />

        <MultimodalChatSection />

        <StageRailSection seedState={seedState} />

        <SedimentGridSection seedState={seedState} seedArtifacts={seedArtifacts} />

        <ArtifactPipelineSection />

        <SeedFeaturedSection
          seedProject={seedProject}
          seedState={seedState}
          seedArtifacts={seedArtifacts}
        />

        <ArchitectureSection />

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
                placeholder="例如：智慧园区平台需求转译"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-stone">场景类型</span>
              <Input
                value={scenarioType}
                onChange={(event) => setScenarioType(event.target.value)}
                placeholder="例如：smart-park-platform"
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
  readiness: _readiness,
  onOpenCreateDialog: _onOpenCreateDialog,
}: {
  readiness: GlobalReadiness | null;
  onOpenCreateDialog: () => void;
}) {
  const heroRef = useRef<HTMLElement>(null);
  const [parallaxY, setParallaxY] = useState(0);
  const [tilt, setTilt] = useState<{ x: number; y: number; engaged: boolean }>({ x: 0, y: 0, engaged: false });
  const reducedMotionRef = useRef(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    reducedMotionRef.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotionRef.current) return;

    const heroEl = heroRef.current;
    if (!heroEl) return;

    let visible = true;
    let rafId: number | null = null;

    const io = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
      },
      { threshold: 0 }
    );
    io.observe(heroEl);

    const update = () => {
      rafId = null;
      if (!visible) return;
      // Cap displacement at 16px so the screenshot drifts up subtly only.
      const next = Math.max(-16, window.scrollY * -0.08);
      setParallaxY(next);
    };
    const onScroll = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(update);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    update();

    return () => {
      window.removeEventListener('scroll', onScroll);
      io.disconnect();
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, []);

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (reducedMotionRef.current) return;
    if (event.pointerType === 'touch') return;
    const rect = event.currentTarget.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width - 0.5;
    const py = (event.clientY - rect.top) / rect.height - 0.5;
    // Up to ±3 degrees, inverted on X so cursor toward top tips card forward.
    setTilt({ x: -py * 6, y: px * 6, engaged: true });
  };

  const handlePointerLeave = () => {
    setTilt({ x: 0, y: 0, engaged: false });
  };

  const cardStyle: React.CSSProperties = {
    transform: `perspective(1200px) translateY(${parallaxY}px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
    transition: tilt.engaged ? 'transform 120ms ease-out' : 'transform 500ms ease-out',
  };

  return (
    <section ref={heroRef} className="grid gap-12 md:grid-cols-[1.1fr_1fr] md:items-center">
      <div className="space-y-7">
        <div className="inline-flex items-center gap-2 rounded-full border border-borderWarm bg-parchment/60 px-3 py-1 text-[11px] font-medium tracking-[0.16em] text-charcoal">
          <Sparkles className="h-3.5 w-3.5 text-terracotta" />
          AI 需求分析工作台
        </div>
        <h1 className="font-display text-balance text-[2.6rem] font-medium leading-[1.08] tracking-tightish text-nearBlack md:text-[3.4rem]">
          把模糊诉求，转成
          <span className="text-terracotta">可追溯、可确认、可交付</span>
          的需求结论
        </h1>
        <p className="max-w-xl text-[1.02rem] leading-[1.7] text-olive md:text-[1.1rem]">
          面向产品经理、需求分析师、售前 ——
          导入散乱的客户资料（纪要 / PDF / 截图 / 群聊），
          通过和 AI 持续对话，让客户那句"我们想做个系统"
          变成工程团队能直接接的需求结论。
        </p>
        <div className="flex flex-wrap gap-3 pt-1">
          <Button asChild size="lg">
            <a href="#seed-demo">
              进入演示工作台
              <ArrowRight className="h-4 w-4" />
            </a>
          </Button>
          <Button asChild variant="ghost" size="lg">
            <a href="#project-list">
              <ListChecks className="h-4 w-4" />
              查看全部项目
            </a>
          </Button>
        </div>
      </div>

      <div className="relative" style={{ perspective: '1200px' }}>
        <div className="absolute -inset-2 rounded-[24px] bg-accentSoft/40 blur-2xl" aria-hidden />
        <div
          className="relative overflow-hidden rounded-[18px] border border-borderCream bg-ivory shadow-[0_30px_70px_-32px_rgba(20,20,19,0.28)] will-change-transform"
          style={cardStyle}
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
        >
          <img
            src="/images/landing/workbench-overview.png"
            alt="客户需求转译台 · 三栏工作台总览：左侧资料区、中间 AI 对话、右侧沉淀总集"
            className="block w-full"
            loading="eager"
            draggable={false}
          />
        </div>
        <div className="mt-3 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.18em] text-stone">
          <span className="h-px w-6 bg-borderWarm" aria-hidden />
          真实工作台 · 资料 / 对话 / 沉淀 同步推进
        </div>
      </div>
    </section>
  );
}

const PAIN_INPUTS = [
  { icon: MessageSquare, title: '一句话诉求', desc: '"我们想做个对账系统"——除此之外什么都没说' },
  { icon: FileText, title: '零散资料', desc: '会议纪要、PDF、表格、群聊截图，混在一起发过来' },
  { icon: Users, title: '多方口径', desc: '业务、财务、技术对同一个事的理解都不太一样' },
  { icon: MousePointerClick, title: '临时想法', desc: '突然想加的页面、报表、自动化，散落在不同对话里' },
] as const;

const PAIN_CONSEQUENCES = [
  { icon: HelpCircle, title: '结论不可追溯', desc: '评审会被反复追问"这个结论从哪儿来的"' },
  { icon: Layers, title: '范围说不清', desc: '一期必做和未来想法混成一团，工程没法估时' },
  { icon: MousePointerClick, title: '设计难落地', desc: '页面目标和交互边界都模糊，UI 反复返工' },
  { icon: Package, title: '方案难交付', desc: '售前讲得清，工程团队接到手却落不下去' },
  { icon: ShieldAlert, title: 'AI 输出没证据', desc: '答案完整但没引用，没人敢直接用' },
] as const;

function PainPointsSection() {
  return (
    <section className="space-y-10">
      <SectionHead
        overline="为什么需要它"
        title="客户从来不直接给你 PRD"
        description="需求分析真正难的地方，不是写文档——是把一句话和一堆散资料，转译成所有人都认账的结论。"
        align="center"
      />
      <div className="grid gap-5 md:grid-cols-2">
        <div className="rounded-[20px] border border-borderCream bg-ivory p-6 shadow-whisper">
          <h3 className="flex items-center gap-2 text-[15px] font-medium text-terracotta">
            <span className="font-display text-[1.6rem] leading-none">"</span>
            客户给的，其实长这样
          </h3>
          <div className="mt-5 space-y-4">
            {PAIN_INPUTS.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.title} className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-accentSoft">
                    <Icon className="h-4 w-4 text-terracotta" />
                  </span>
                  <div>
                    <div className="text-[14px] font-medium text-nearBlack">{item.title}</div>
                    <p className="mt-0.5 text-[13px] leading-[1.6] text-olive">{item.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="rounded-[20px] border border-borderCream bg-ivory p-6 shadow-whisper">
          <h3 className="text-[15px] font-medium text-[#a14834]">
            如果不被结构化，会发生什么
          </h3>
          <div className="mt-5 space-y-4">
            {PAIN_CONSEQUENCES.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.title} className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-[#fbeeec]">
                    <Icon className="h-4 w-4 text-[#a14834]" />
                  </span>
                  <div>
                    <div className="text-[14px] font-medium text-nearBlack">{item.title}</div>
                    <p className="mt-0.5 text-[13px] leading-[1.6] text-olive">{item.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

const ARCHITECTURE_LAYERS = [
  {
    num: '01',
    icon: FileText,
    title: '资料层',
    modules: ['文本粘贴', '文件上传（PDF / DOCX / XLSX / MD）', '截图与图片 OCR', '链接导入', '语音转写（实时）'],
  },
  {
    num: '02',
    icon: FolderKanban,
    title: '证据层',
    modules: ['解析与标准化', '向量化检索', '引用追溯', '项目级隔离', '增量索引'],
  },
  {
    num: '03',
    icon: Brain,
    title: '智能分析层',
    modules: ['主智能体', '覆盖度检查', 'job-to-be-done 追问', '流程重建', '冲突识别', 'MVP 收敛'],
  },
  {
    num: '04',
    icon: Layers,
    title: '状态沉淀层',
    modules: ['当前理解', '待确认项', '已确认项', '冲突项', 'MVP 方向', '版本快照'],
  },
  {
    num: '05',
    icon: Send,
    title: '交付物层',
    modules: ['需求文档', '页面方案', '可点击交互稿', '生成预览与回滚'],
  },
] as const;

const ARCHITECTURE_MECHANISMS = [
  {
    icon: GitBranch,
    title: '可追溯',
    desc: '每一条结论都能回到原始资料。',
  },
  {
    icon: CheckCircle2,
    title: '可确认',
    desc: '关键项主动追问，推动客户拍板。',
  },
  {
    icon: Package,
    title: '可交付',
    desc: '从理解到 HTML demo，一次生成。',
  },
] as const;

// Maps each layer index → which mechanism it activates.
// 01 资料层 / 02 证据层 → 可追溯；03 分析 / 04 沉淀 → 可确认；05 交付物 → 可交付。
const LAYER_TO_MECHANISM = [0, 0, 1, 1, 2] as const;

function ArchitectureSection() {
  const layerRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [activeLayerIdx, setActiveLayerIdx] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const els = layerRefs.current.filter((el): el is HTMLDivElement => el !== null);
    if (els.length === 0) return;

    let rafId: number | null = null;
    const update = () => {
      rafId = null;
      const targetY = window.innerHeight * 0.4;
      let bestIdx = 0;
      let bestDistance = Infinity;
      let anyEligible = false;
      for (let i = 0; i < els.length; i += 1) {
        const top = els[i].getBoundingClientRect().top;
        if (top <= targetY) {
          const distance = targetY - top;
          if (distance < bestDistance) {
            bestDistance = distance;
            bestIdx = i;
            anyEligible = true;
          }
        }
      }
      if (anyEligible) setActiveLayerIdx(bestIdx);
    };
    const onScroll = () => {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(update);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    update();
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, []);

  const activeMechanismIdx = LAYER_TO_MECHANISM[activeLayerIdx] ?? 0;

  return (
    <section className="space-y-10">
      <SectionHead
        overline="完整闭环"
        title="从输入到交付，五层一条闭环"
        description="每一层都有自己的语义和归档方式 —— 这是 chatbot 替代不了的部分。"
        align="center"
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <div className="space-y-3">
          {ARCHITECTURE_LAYERS.map((layer, idx) => {
            const Icon = layer.icon;
            const isActive = idx === activeLayerIdx;
            return (
              <div
                key={layer.num}
                ref={(el) => {
                  layerRefs.current[idx] = el;
                }}
                className={cn(
                  'rounded-[16px] border bg-ivory p-5 transition-all duration-300 ease-out motion-reduce:transition-none',
                  isActive
                    ? 'border-terracotta/60 shadow-[0_22px_48px_-20px_rgba(201,100,66,0.45)] scale-[1.015]'
                    : 'border-borderCream shadow-whisper opacity-90'
                )}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold transition-colors duration-300 motion-reduce:transition-none',
                      isActive ? 'bg-terracotta text-ivory' : 'bg-terracotta/85 text-ivory'
                    )}
                  >
                    {layer.num}
                  </span>
                  <Icon className="h-4 w-4 text-terracotta" />
                  <h3 className="font-display text-[1.1rem] font-medium leading-tight text-nearBlack">
                    {layer.title}
                  </h3>
                </div>
                <div className="mt-3 flex flex-wrap gap-2 pl-11">
                  {layer.modules.map((mod) => (
                    <span
                      key={mod}
                      className="rounded-[10px] border border-borderCream bg-parchment/60 px-2.5 py-1 text-[12.5px] leading-[1.5] text-charcoal"
                    >
                      {mod}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <aside className="h-fit rounded-[20px] border border-borderCream bg-ivory p-5 shadow-whisper lg:sticky lg:top-6">
          <div className="border-b border-borderCream pb-3 text-center text-[11px] font-medium uppercase tracking-[0.18em] text-stone">
            核心机制
          </div>
          <div className="mt-5 space-y-2">
            {ARCHITECTURE_MECHANISMS.map((m, idx) => {
              const Icon = m.icon;
              const isActive = idx === activeMechanismIdx;
              return (
                <div
                  key={m.title}
                  className={cn(
                    'rounded-[14px] p-3 text-center transition-all duration-300 ease-out motion-reduce:transition-none',
                    isActive
                      ? 'bg-accentSoft/55 ring-1 ring-terracotta/30'
                      : 'opacity-70'
                  )}
                >
                  <span
                    className={cn(
                      'mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-[12px] transition-colors duration-300 motion-reduce:transition-none',
                      isActive ? 'bg-terracotta' : 'bg-accentSoft'
                    )}
                  >
                    <Icon
                      className={cn(
                        'h-4 w-4 transition-colors duration-300 motion-reduce:transition-none',
                        isActive ? 'text-ivory' : 'text-terracotta'
                      )}
                    />
                  </span>
                  <div className="font-display text-[1rem] font-medium text-nearBlack">{m.title}</div>
                  <p className="mt-1 text-[12.5px] leading-[1.6] text-olive">{m.desc}</p>
                </div>
              );
            })}
          </div>
        </aside>
      </div>

      <p className="text-center text-[12px] leading-[1.7] text-stone">
        基于 <span className="text-charcoal">LLM</span> · <span className="text-charcoal">Docling</span> · <span className="text-charcoal">Qdrant</span> · <span className="text-charcoal">LlamaIndex</span> 等开源能力构建；
        分析视角内化了 <span className="text-charcoal">BABOK</span> · <span className="text-charcoal">JTBD</span> · <span className="text-charcoal">Event Storming</span> 三套成熟方法论。
      </p>
    </section>
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
              "客户给我发了 5 份会议纪要、几个微信群截图、一份补充说明 PDF，让我下周给方向。我读得头都大了…"
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
    image: '/images/landing/pane-sources.png',
    title: '资料区',
    caption: '混杂资料一键导入，自动解析、索引、版本化，原文随时可回看。',
  },
  {
    image: '/images/landing/pane-chat.png',
    title: '对话区',
    caption: 'AI 主动追问、引用原文、流式输出；客户像聊天一样把上下文喂进来。',
  },
  {
    image: '/images/landing/pane-state.png',
    title: '沉淀区',
    caption: '每一轮的结论自动归档到 7 类沉淀，结论不再埋在长对话里。',
  },
] as const;

function WorkbenchPreviewSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="核心工作台"
        title="资料 · 对话 · 沉淀，同时推进"
        description="不是 chatbot —— 聊天负责推进，右栏负责沉淀，每条结论都能回到原始资料。"
        align="center"
      />
      <div className="grid gap-5 md:grid-cols-3">
        {WORKBENCH_PANES.map((pane, index) => (
          <div key={pane.title} className="space-y-3">
            <div className="overflow-hidden rounded-[16px] border border-borderCream bg-ivory shadow-whisper">
              <img
                src={pane.image}
                alt={`工作台 ${pane.title}：${pane.caption}`}
                className="block aspect-[3/4] w-full object-cover object-top"
                loading={index === 0 ? 'eager' : 'lazy'}
              />
            </div>
            <div className="px-1">
              <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-stone">
                {String(index + 1).padStart(2, '0')} · {pane.title}
              </div>
              <p className="mt-1 text-[13.5px] leading-[1.6] text-charcoal">{pane.caption}</p>
            </div>
          </div>
        ))}
      </div>
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
                <span>产品自我分析 seed</span>
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
    key: 'document',
    title: '需求文档',
    icon: FileText,
    tag: '可交付',
    desc: '正式的需求说明，章节、引用、评审建议齐全；可直接进入工程评审。',
  },
  {
    key: 'page_solution',
    title: '页面方案',
    icon: ImageIcon,
    tag: '精美静态稿',
    desc: '客户能感受到的视觉稿；和文档配套，让"长什么样"不再靠口说。',
  },
  {
    key: 'interaction_flow',
    title: '可点击交互稿',
    icon: MousePointerClick,
    tag: '可点真用',
    desc: '小原型，客户摸一摸就能消除对功能的歧义，比一千句描述都管用。',
  },
] as const;

function ArtifactPipelineSection() {
  return (
    <section className="space-y-8">
      <SectionHead
        overline="交付物"
        title="从需求文档到可点击 demo，一次生成"
        description="文档、页面、交互三件套，全部基于已经入库的资料生成 —— 每一句都有出处。"
        align="center"
      />
      <div className="grid gap-4 md:grid-cols-3">
        {ARTIFACT_CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.key}
              className="flex h-full flex-col gap-4 rounded-[18px] border border-borderCream bg-ivory p-5 shadow-whisper"
            >
              <div className="flex items-start justify-between gap-3">
                <Icon className="h-5 w-5 text-terracotta" />
                <Badge variant="accent">{card.tag}</Badge>
              </div>
              <h3 className="font-display text-[1.35rem] font-medium leading-tight text-nearBlack">
                {card.title}
              </h3>
              <p className="text-[14px] leading-[1.65] text-olive">{card.desc}</p>
            </div>
          );
        })}
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
      <section id="seed-demo" className="scroll-mt-12 space-y-6">
        <SectionHead overline="递归实证" title="我们用这个产品分析了它自己" align="center" />
        <div className="rounded-[20px] border border-dashed border-borderWarm bg-ivory/60 p-8 text-center text-[14px] leading-[1.6] text-stone">
          演示数据加载中…后端 ready 后会自动展示递归 seed 项目。
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
    <section id="seed-demo" className="scroll-mt-12 space-y-6">
      <SectionHead
        overline="递归实证"
        title="我们用这个产品分析了它自己"
        description="左侧资料就是这个产品最早的会议纪要、群聊、补充说明；中间是 agent 引导的 15 轮分析；右侧是 7 类沉淀与三件套交付物 —— 全部是你现在正在看的这套系统的真实数据。"
        align="center"
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
    <section id="project-list" className="scroll-mt-12 space-y-6">
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
  return (
    <footer className="border-t border-borderCream pt-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {readiness?.llm ? (
            <ReadyPill label="LLM" status={readiness.llm.status} />
          ) : null}
          {evidenceReadiness(readiness) ? (
            <ReadyPill label="项目知识库" status={evidenceReadiness(readiness)!.status} />
          ) : null}
          <ReadyPill label="LLM Wiki" status="ready" />
        </div>
        <p className="text-[12px] leading-[1.6] text-stone">
          实时显示后端 provider 状态 —— 失败就报失败，没有静默 fallback。
        </p>
      </div>
    </footer>
  );
}

