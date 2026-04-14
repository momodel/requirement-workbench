export type StageId =
  | 'intake'
  | 'understanding'
  | 'convergence'
  | 'solution'
  | 'delivery';

export type FileStatus = '已解析' | '有冲突' | '已引用' | '待确认';
export type InsightCategory =
  | '已确认事实'
  | '待确认项'
  | '范围边界'
  | 'MVP 结论'
  | '页面方案 / 交付物';
export type ChatRole = 'user' | 'assistant' | 'system';
export type ChatKind = 'message' | 'checkpoint';

export type KnowledgeFile = {
  id: string;
  name: string;
  type: string;
  status: FileStatus;
  version: string;
  updatedAt: string;
  owner: string;
  quoteCount: number;
  summary: string;
  tags: string[];
  excerpt: string;
};

export type ChatTurn = {
  id: string;
  role: ChatRole;
  kind: ChatKind;
  content: string;
  timestampLabel: string;
  stage: StageId;
  references?: string[];
  unlockAt: number;
};

export type WorkspaceAction = {
  id: string;
  label: string;
  revealsUpToStep: number;
  resultLabel: string;
};

export type InsightRecord = {
  id: string;
  category: InsightCategory;
  title: string;
  body: string;
  stage: StageId;
  status: '已确认' | '待确认' | '草案';
  fileIds: string[];
  unlockAt: number;
};

export type ArtifactRecord = {
  id: string;
  title: string;
  type: '文档稿' | '页面方案' | '交互稿';
  stage: StageId;
  summary: string;
  fileIds: string[];
  unlockAt: number;
  previewMode: 'document' | 'page-scheme' | 'interaction-flow';
  prototypePath?: string;
  coverTitle: string;
  version: string;
  owner: string;
  updatedAt: string;
  documentSections?: {
    title: string;
    body: string;
    bullets?: string[];
  }[];
  pageFrames?: {
    title: string;
    summary: string;
    regions: string[];
  }[];
  flowSteps?: {
    id: string;
    actor: string;
    title: string;
    summary: string;
    output: string;
  }[];
};

export const project = {
  id: 'reconciliation',
  name: '集团业财逐笔对账需求分析',
  summary:
    '把“核对业务系统里的订单/结算数据，与财务系统对应科目的金额是否一致”这句模糊诉求，转成 AI 逐步分析、用户确认、沉淀更新的工作台演示。',
  industry: '企业财务 / 业财协同',
  primaryUser: '财务 / 对账专员',
  status: '需求分析中'
};

export const stageLabels: { id: StageId; label: string }[] = [
  { id: 'intake', label: '需求接入' },
  { id: 'understanding', label: '业务理解' },
  { id: 'convergence', label: '需求收敛' },
  { id: 'solution', label: '方案定义' },
  { id: 'delivery', label: '设计交付' }
];

export const progressionStages: StageId[] = [
  'intake',
  'understanding',
  'convergence',
  'solution',
  'delivery'
];

export const knowledgeFiles: KnowledgeFile[] = [
  {
    id: 'order-fields',
    name: '订单字段说明.xlsx',
    type: 'XLSX',
    status: '已解析',
    version: 'v1.4',
    updatedAt: '今天 09:32',
    owner: '订单产品',
    quoteCount: 5,
    summary:
      '包含订单号、业务类型、结算金额、税额、组织、币种等字段，是逐笔对账的基础数据来源。',
    tags: ['订单系统', '字段字典'],
    excerpt:
      '订单系统里记录的是业务事件和业务金额，但并没有直接给出对应财务科目，后续必须依赖映射规则才能核到财务侧金额。'
  },
  {
    id: 'settlement-sample',
    name: '结算单样例-0325.csv',
    type: 'CSV',
    status: '已引用',
    version: '0325',
    updatedAt: '今天 10:06',
    owner: '结算运营',
    quoteCount: 6,
    summary:
      '抽样 120 笔结算单，覆盖退款、冲销、跨月结算等特殊场景，可直接用来说明逐笔对账粒度。',
    tags: ['结算系统', '样本'],
    excerpt:
      '样例里同一业务类型在不同组织下的税额口径并不统一，这会直接影响与财务系统对应科目金额的比较方式。'
  },
  {
    id: 'finance-subjects',
    name: '财务科目口径说明.docx',
    type: 'DOCX',
    status: '有冲突',
    version: 'v2.1',
    updatedAt: '昨天 18:40',
    owner: '财务共享中心',
    quoteCount: 8,
    summary:
      '列出了收入、税额、优惠、退款等业务结果应落的财务科目，但没有把业务类型映射优先级写清楚。',
    tags: ['财务系统', '科目规则'],
    excerpt:
      '列出了收入、税额、优惠、退款等对应科目，但没有明确写业务类型与科目挂接优先级，同类业务可能被解释成不同科目组合。'
  },
  {
    id: 'historical-gaps',
    name: '历史差异清单.xlsx',
    type: 'XLSX',
    status: '已解析',
    version: '2025Q4',
    updatedAt: '今天 11:12',
    owner: '财务专员',
    quoteCount: 7,
    summary:
      '记录了 2,146 条历史差异，主要集中在金额不一致、未入账、科目错挂三类异常。',
    tags: ['差异样本', '历史异常'],
    excerpt:
      '科目错挂和退款冲销口径不统一，是人工排查最耗时的两类问题。'
  },
  {
    id: 'mapping-rules',
    name: '业务类型-财务科目映射.xlsx',
    type: 'XLSX',
    status: '待确认',
    version: '试行版',
    updatedAt: '今天 14:20',
    owner: '财务负责人',
    quoteCount: 4,
    summary:
      '37 条业务类型到财务科目的映射规则，其中 9 条存在组织差异和历史差异，不能直接固化。',
    tags: ['映射规则', '待确认'],
    excerpt:
      '同一业务类型在不同组织或历史时期挂到不同财务科目，是当前自动化推进的最大阻碍。'
  }
];

export const chatTurns: ChatTurn[] = [
  {
    id: 'turn-1',
    role: 'user',
    kind: 'message',
    content:
      '我们现在对账还是靠人工，从订单系统和结算系统各自导数据，再去财务系统里查对应科目的金额，一笔一笔核，效率很低。',
    timestampLabel: '09:40',
    stage: 'intake',
    references: ['order-fields', 'settlement-sample'],
    unlockAt: 0
  },
  {
    id: 'turn-2',
    role: 'assistant',
    kind: 'message',
    content:
      '先不急着谈自动化。我先接住你的原始诉求：你们要核的不是泛 ERP 数据，而是业务系统里的订单/结算记录，是否与财务系统中对应科目的金额一致。',
    timestampLabel: '09:41',
    stage: 'intake',
    references: ['finance-subjects'],
    unlockAt: 0
  },
  {
    id: 'turn-3',
    role: 'system',
    kind: 'checkpoint',
    content:
      '初步问题定义：这是一个“逐笔差异定位”场景，不是简单汇总报表核对。当前缺的不是想法，而是业务字段到财务科目的映射口径。',
    timestampLabel: '09:42',
    stage: 'intake',
    references: ['order-fields', 'finance-subjects'],
    unlockAt: 0
  },
  {
    id: 'turn-4',
    role: 'assistant',
    kind: 'message',
    content:
      '先把对账对象、粒度和科目映射摸清。我需要确认三件事：一是逐笔还是汇总优先，二是财务侧以哪些科目组合作为对账基准，三是退款/冲销要不要一起纳入。',
    timestampLabel: '09:46',
    stage: 'understanding',
    references: ['finance-subjects', 'mapping-rules'],
    unlockAt: 1
  },
  {
    id: 'turn-5',
    role: 'user',
    kind: 'message',
    content:
      '我们更关心逐笔定位差异。财务侧看的就是和业务结果对应的那些科目金额，但现在同一类业务挂哪个科目，大家口径不完全一样。',
    timestampLabel: '09:48',
    stage: 'understanding',
    references: ['mapping-rules'],
    unlockAt: 1
  },
  {
    id: 'turn-6',
    role: 'system',
    kind: 'checkpoint',
    content:
      '业务理解摘要：当前流程是订单/结算生成 -> 数据传输 -> 财务入账 -> 人工逐笔核对 -> 异常沟通。核心冲突是业务字段到财务科目映射不稳定。',
    timestampLabel: '09:49',
    stage: 'understanding',
    references: ['settlement-sample', 'mapping-rules'],
    unlockAt: 1
  },
  {
    id: 'turn-7',
    role: 'assistant',
    kind: 'message',
    content:
      '那我先把真实需求收敛一下：一期应该做的是“逐笔差异识别与归因辅助”，而不是自动改账。系统要先帮财务专员看到哪笔有问题、可能为什么有问题、该找谁处理。',
    timestampLabel: '09:55',
    stage: 'convergence',
    references: ['historical-gaps', 'mapping-rules'],
    unlockAt: 2
  },
  {
    id: 'turn-8',
    role: 'user',
    kind: 'message',
    content:
      '对，尤其高金额异常不能自动动账，退款和冲销也不能一上来就让系统自己判，先把识别和归因做出来就很有价值。',
    timestampLabel: '09:56',
    stage: 'convergence',
    references: ['historical-gaps'],
    unlockAt: 2
  },
  {
    id: 'turn-9',
    role: 'system',
    kind: 'checkpoint',
    content:
      '当前真实需求：建设一个服务财务/对账专员的工作台，逐笔比较业务单据与财务系统对应科目金额，输出差异类型、可疑归因和处理流转建议。',
    timestampLabel: '09:57',
    stage: 'convergence',
    references: ['finance-subjects', 'historical-gaps'],
    unlockAt: 2
  },
  {
    id: 'turn-10',
    role: 'assistant',
    kind: 'message',
    content:
      '接下来我会把一期 MVP 边界锁定成五块：数据接入与单据对齐、映射规则管理、差异识别、归因建议、异常处理闭环。自动改账和自动改科目都不做。',
    timestampLabel: '10:03',
    stage: 'solution',
    references: ['mapping-rules'],
    unlockAt: 3
  },
  {
    id: 'turn-11',
    role: 'system',
    kind: 'checkpoint',
    content:
      'MVP 结论：方案可以大胆做识别、分类、提示和协同，但必须保守处理高金额异常、规则未确认场景、退款/冲销类特殊业务。',
    timestampLabel: '10:05',
    stage: 'solution',
    references: ['finance-subjects', 'mapping-rules'],
    unlockAt: 3
  },
  {
    id: 'turn-12',
    role: 'assistant',
    kind: 'message',
    content:
      '最后我把交付物补齐：除了需求摘要和风险边界文档，我会同时给出未来“业财对账系统”的页面方案，包括总览、逐笔差异明细、异常处理、映射规则配置和导出报告。',
    timestampLabel: '10:11',
    stage: 'delivery',
    references: ['order-fields', 'mapping-rules'],
    unlockAt: 4
  },
  {
    id: 'turn-13',
    role: 'system',
    kind: 'checkpoint',
    content:
      '设计交付建议已生成：你现在看到的不是聊天记录，而是一套可继续推进的执行稿，包括页面清单、交互流、字段清单和需求文档摘要。',
    timestampLabel: '10:12',
    stage: 'delivery',
    references: ['order-fields', 'finance-subjects', 'mapping-rules'],
    unlockAt: 4
  }
];

export const actions: WorkspaceAction[] = [
  {
    id: 'step-1',
    label: '继续分析',
    revealsUpToStep: 1,
    resultLabel: '进入业务理解'
  },
  {
    id: 'step-2',
    label: '基于当前资料生成理解',
    revealsUpToStep: 2,
    resultLabel: '收敛真实需求'
  },
  {
    id: 'step-3',
    label: '把本轮结论写入沉淀',
    revealsUpToStep: 3,
    resultLabel: '输出 MVP 结论'
  },
  {
    id: 'step-4',
    label: '查看交付建议',
    revealsUpToStep: 4,
    resultLabel: '补齐设计交付'
  }
];

export const insightRecords: InsightRecord[] = [
  {
    id: 'fact-1',
    category: '已确认事实',
    title: '财务侧核对对象是对应科目金额',
    body: '不是泛泛核 ERP 数据，而是核业务系统结果在财务系统中对应科目的金额。',
    stage: 'intake',
    status: '已确认',
    fileIds: ['finance-subjects'],
    unlockAt: 0
  },
  {
    id: 'fact-2',
    category: '已确认事实',
    title: '对账粒度是逐笔差异定位',
    body: '客户需要看到具体哪笔业务单据与财务侧不一致，而不是只看汇总差异。',
    stage: 'convergence',
    status: '已确认',
    fileIds: ['settlement-sample', 'historical-gaps'],
    unlockAt: 2
  },
  {
    id: 'pending-1',
    category: '待确认项',
    title: '退款 / 冲销是否纳入一期主流程',
    body: '如果口径未统一，一期只能先标记，不做自动判断。',
    stage: 'convergence',
    status: '待确认',
    fileIds: ['historical-gaps', 'mapping-rules'],
    unlockAt: 2
  },
  {
    id: 'pending-2',
    category: '待确认项',
    title: '财务基准科目组合需拍板',
    body: '部分业务场景需要同时比较收入、税额、优惠等科目组合，不能只看单一科目。',
    stage: 'understanding',
    status: '待确认',
    fileIds: ['finance-subjects'],
    unlockAt: 1
  },
  {
    id: 'scope-1',
    category: '范围边界',
    title: '一期不自动改账',
    body: '系统提供识别、分类、提示和处理流转，不做自动改账或自动调科目。',
    stage: 'convergence',
    status: '已确认',
    fileIds: ['finance-subjects'],
    unlockAt: 2
  },
  {
    id: 'scope-2',
    category: '范围边界',
    title: '高金额异常必须人工确认',
    body: '金额越大，越要把风险控制放在人身上，系统只做辅助判断。',
    stage: 'solution',
    status: '已确认',
    fileIds: ['historical-gaps'],
    unlockAt: 3
  },
  {
    id: 'mvp-1',
    category: 'MVP 结论',
    title: '一期能力包',
    body: '数据接入与单据对齐、映射规则管理、差异识别、归因建议、异常处理闭环。',
    stage: 'solution',
    status: '草案',
    fileIds: ['mapping-rules', 'order-fields'],
    unlockAt: 3
  },
  {
    id: 'mvp-2',
    category: 'MVP 结论',
    title: '验收看四个指标',
    body: '对账耗时、差异定位时效、人工核对工作量、规则覆盖率。',
    stage: 'solution',
    status: '草案',
    fileIds: ['historical-gaps'],
    unlockAt: 3
  },
  {
    id: 'artifact-1',
    category: '页面方案 / 交付物',
    title: '业财对账系统页面方案',
    body: '输出总览、逐笔差异明细、异常处理、映射规则配置、导出报告五个页面。',
    stage: 'delivery',
    status: '草案',
    fileIds: ['order-fields', 'mapping-rules'],
    unlockAt: 4
  },
  {
    id: 'artifact-2',
    category: '页面方案 / 交付物',
    title: '需求摘要 / MVP / 风险边界',
    body: '把业务问题定义、MVP 能力和风险边界整理成可以继续评审的文档稿。',
    stage: 'delivery',
    status: '草案',
    fileIds: ['finance-subjects', 'historical-gaps'],
    unlockAt: 4
  }
];

export const artifactRecords: ArtifactRecord[] = [
  {
    id: 'artifact-doc',
    title: '需求摘要 / MVP / 风险边界',
    type: '文档稿',
    stage: 'delivery',
    summary: '给老板、产品、研发看的业务问题定义与一期方案摘要。',
    fileIds: ['finance-subjects', 'historical-gaps'],
    unlockAt: 4,
    previewMode: 'document',
    coverTitle: '业财逐笔对账需求分析与一期方案摘要',
    version: 'v0.9',
    owner: '需求转译台',
    updatedAt: '今天 10:12',
    documentSections: [
      {
        title: '项目背景',
        body:
          '客户目前依赖财务专员从订单系统、结算系统和财务系统分别导数，再人工逐笔核对业务单据与对应科目金额，定位差异效率低且口径高度依赖经验。'
      },
      {
        title: '问题定义',
        body:
          '本项目不是做泛化报表平台，而是建设面向财务 / 对账专员的逐笔差异识别工作台。',
        bullets: [
          '核对对象是业务系统单据与财务系统对应科目金额',
          '核心矛盾是业务字段到财务科目映射口径不一致',
          '历史差异主要集中在科目错挂、退款冲销和未入账场景'
        ]
      },
      {
        title: 'MVP 范围',
        body: '一期先解决识别、归因和处理协同，不碰自动改账。',
        bullets: [
          '数据接入与单据对齐',
          '业务类型到财务科目的映射规则管理',
          '逐笔差异识别与异常归类建议',
          '人工确认与处理闭环'
        ]
      },
      {
        title: '风险边界',
        body: '需要在方案里明确哪些场景只能提示风险，不能默认自动判定。',
        bullets: [
          '高金额异常必须人工确认',
          '退款 / 冲销场景先纳入特殊规则池',
          '规则未拍板时只允许标记风险，不允许直接定责'
        ]
      }
    ]
  },
  {
    id: 'artifact-pages',
    title: '业财对账系统页面方案',
    type: '页面方案',
    stage: 'delivery',
    summary: '未来产品形态的页面清单、主要信息块和线框说明。',
    fileIds: ['order-fields', 'mapping-rules'],
    unlockAt: 4,
    previewMode: 'page-scheme',
    prototypePath: '/prototypes/reconciliation-pages.html',
    coverTitle: '业财对账系统页面结构稿',
    version: 'v0.8',
    owner: '需求转译台',
    updatedAt: '今天 10:13',
    pageFrames: [
      {
        title: '对账总览页',
        summary: '先给财务专员一个今天是否异常、哪里最该先看的一屏判断。',
        regions: ['差异总量看板', '高风险异常列表', '差异原因分布', '处理进度概览']
      },
      {
        title: '逐笔差异明细页',
        summary: '把单据、财务金额、差异类型和建议归因放到一张主工作台里。',
        regions: ['业务单据信息', '对应科目金额', '差异值与差异类型', '建议归因与责任角色']
      },
      {
        title: '映射规则配置页',
        summary: '解决业务类型、组织、税额口径到财务科目的规则维护问题。',
        regions: ['规则检索区', '规则列表', '口径说明侧栏', '规则生效时间与版本']
      },
      {
        title: '异常处理页',
        summary: '承接人工确认、转交处理和处理留痕，避免异常只停留在提示。',
        regions: ['待处理异常池', '处理意见面板', '责任人分派', '处理轨迹记录']
      }
    ]
  },
  {
    id: 'artifact-flow',
    title: '关键交互流',
    type: '交互稿',
    stage: 'delivery',
    summary: '把查看差异、确认归因、提交处理、导出报告串成可交付的交互说明。',
    fileIds: ['mapping-rules', 'historical-gaps'],
    unlockAt: 4,
    previewMode: 'interaction-flow',
    prototypePath: '/prototypes/reconciliation-flow.html',
    coverTitle: '业财对账系统关键交互流',
    version: 'v0.7',
    owner: '需求转译台',
    updatedAt: '今天 10:14',
    flowSteps: [
      {
        id: '01',
        actor: '财务专员',
        title: '查看今日差异与高风险异常',
        summary: '从总览页先锁定最值得优先处理的异常批次和责任域。',
        output: '进入逐笔差异明细页'
      },
      {
        id: '02',
        actor: '财务专员',
        title: '筛选差异原因与业务类型',
        summary: '按组织、业务类型、差异原因筛出同类问题，减少人工逐条翻看。',
        output: '圈定待确认异常集'
      },
      {
        id: '03',
        actor: '财务专员 / 业务运营',
        title: '确认归因或转交责任人',
        summary: '对规则明确的问题直接归类，对口径冲突或疑似错挂的问题转交相关负责人。',
        output: '形成处理意见与责任归属'
      },
      {
        id: '04',
        actor: '财务专员',
        title: '提交处理并导出报告',
        summary: '沉淀处理结果、保留审计痕迹，并导出给财务负责人或项目组评审。',
        output: '输出日报 / 周报或项目评审材料'
      }
    ]
  }
];

export function stageLabel(stageId: StageId) {
  return stageLabels.find((stage) => stage.id === stageId)?.label ?? stageId;
}
