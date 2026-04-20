# 客户需求转译台 Demo

这是一个基于 React + Vite 的单页演示项目，用来展示“客户需求转译台”如何把模糊诉求逐步收敛成可执行的需求分析结果。

当前主案例是“集团业财逐笔对账需求分析”。演示重点不是做一个真正的对账系统，而是展示 AI 工作台如何接收资料、理解业务、推进对话、沉淀结论，并最终产出页面方案和交付稿。

## 在线地址

- 正式演示地址：[https://requirementnyl.vercel.app](https://requirementnyl.vercel.app)
- GitHub 仓库：[https://github.com/lzfxxx/requirement-workbench-demo](https://github.com/lzfxxx/requirement-workbench-demo)

说明：

- `requirementnyl.vercel.app` 是当前项目绑定的正式别名域名，后续重新部署会继续覆盖这个地址
- GitHub 仓库当前为私有仓库，只有有权限的账号才能访问

## 项目目标

这个 Demo 主要想说明三件事：

1. AI 不是只会聊天，而是可以在工作台里持续引用资料、推进分析和沉淀结果
2. “自动对账”这类宽泛诉求，需要先拆成业务对象、口径、边界、优先级和待确认项
3. 在需求分析阶段，最终交付物不只是文字结论，还包括页面方案、交互流和文档稿

## 当前演示内容

项目采用单工作台结构，核心区域包括：

- 项目知识库：展示订单字段、结算样例、财务科目口径、历史差异、映射规则等资料
- 需求分析对话：模拟用户与 AI 的逐轮分析过程
- 沉淀总集：按“已确认事实、待确认项、范围边界、MVP 结论、页面方案 / 交付物”归档结论
- 阶段进度条：覆盖需求接入、业务理解、需求收敛、方案定义、设计交付五个阶段
- 交付详情抽屉：支持查看文档稿、页面方案和关键交互流的详情与原型

核心案例信息：

- 项目名称：集团业财逐笔对账需求分析
- 行业方向：企业财务 / 业财协同
- 主要使用人：财务 / 对账专员
- 当前状态：需求分析中

## 演示建议

推荐按下面的顺序演示：

1. 首页
说明这不是对账系统本体，而是需求转译台在分析一个业财对账项目。

2. 五阶段总览
讲清需求接入、业务理解、需求收敛、方案定义、设计交付的推进过程。

3. 阶段 1：需求接入
演示系统如何接住原始诉求和零散资料。

4. 阶段 2：业务理解
强调流程、字段映射、财务科目和系统边界。

5. 阶段 3：需求收敛
重点讲“自动对账”如何被拆成真实需求、边界和待确认项。

6. 阶段 4：方案定义
强调一期只做差异识别、归因建议和人工确认，不做自动改账。

7. 阶段 5：设计交付
展示未来业财对账系统的页面方案和文档交付。

8. 交付预览
用文档稿和页面方案收尾。

## 核心业务口径

- 上游业务系统：订单系统或结算系统
- 财务侧：财务系统中与业务系统对应科目的金额
- 对账粒度：逐笔对账
- 核心矛盾：业务字段到财务科目映射口径不一致

## 技术栈

- React 18
- React Router 6
- Vite 5
- TypeScript 5
- Vitest + Testing Library

## 本地开发

### 安装依赖

```bash
npm install
```

### 启动开发环境

```bash
npm run dev
```

启动后访问终端输出中的本地地址。

### 运行测试

```bash
npm test
```

### 构建生产包

```bash
npm run build
```

### 本地预览生产构建

```bash
npm run preview
```

## 路由说明

项目使用 `BrowserRouter`，主要路由包括：

- `/`
- `/project/reconciliation/workbench`

另外几个历史路由会自动重定向回工作台：

- `/project/:projectId/overview`
- `/project/:projectId/export`
- `/project/:projectId/stage/:stageId`

为了保证 Vercel 上刷新子路由不出现 404，项目额外配置了 `vercel.json` 做 SPA 回退。

## 部署到 Vercel

当前项目已经完成 Vercel 绑定，后续更新可以直接在项目根目录执行：

```bash
vercel --prod
```

如果是首次在新环境部署，也可以走完整流程：

```bash
npm install
npm run build
vercel
```

部署说明：

- 项目会自动识别为 Vite 应用
- 正式环境会发布到当前绑定的 Vercel 项目
- `requirementnyl.vercel.app` 会始终指向当前生产版本
- 如果后面新增环境变量，需要先在 Vercel 项目里配置，再重新部署

## 已合并的项目资产

为了把之前 `projects/requirement-workbench/` 里的产物并进这个交互 demo 仓库，当前仓库除了 React/Vite 应用本身，也保留了项目资产目录。

典型资产包括：

- `docs/`
  - 历史 PRD、可视化 PRD、最新 PRD
- `prototypes/`
  - 早期单页工作台和五阶段 HTML 原型
- `deliverables/`
  - 已导出的 PDF 交付件
- `archive/`
  - 历史归档包

可以把当前仓库理解成两部分：

- React/Vite 交互 demo：用于 mock 数据演示和交互流程展示
- 项目资产目录：用于保存 PRD、静态原型、PDF 和历史归档

## 仓库结构

```text
.
├── archive/
├── deliverables/
├── docs/
├── prototypes/
├── public/
│   └── prototypes/
├── src/
│   ├── App.tsx
│   ├── App.test.tsx
│   ├── demoData.ts
│   ├── main.tsx
│   ├── styles.css
│   └── test/
├── index.html
├── package.json
├── vercel.json
└── README.md
```

## 备注

- `.vercel` 已加入 `.gitignore`，不会提交到仓库
- `node_modules`、`dist` 和构建缓存已忽略
- 当前仓库已经推送到 GitHub 私有仓库，可继续在此基础上迭代
