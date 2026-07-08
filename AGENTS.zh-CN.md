# 仓库开发规则（中文）

> English version: [AGENTS.md](AGENTS.md)

## 开工前先看什么

所有实现任务先看这三份：

- `docs/product/fullstack-phase1-spec.md`
- `docs/planning/fullstack-phase1-todo.md`
- `archive/legacy-demo/README.md`

如果文档和现有代码冲突，以文档为准。

后端 CAS 的运行时规则看：

- `backend/CLAUDE.md`
- `backend/.claude/skills/**/SKILL.md`

如果当前任务会改这些领域，再按需补看对应 skill：

- `backend/.claude/skills/requirement-analysis-methodology/SKILL.md`
  - 适用：需求分析链路、状态沉淀、版本快照、artifact 触发
- `backend/.claude/skills/rag-evidence-workflow/SKILL.md`
  - 适用：source ingestion、项目知识库索引、grounding、citation
- `backend/.claude/skills/llm-wiki-knowledge-workflow/SKILL.md`
  - 适用：LLM Wiki 综合层（实体页、术语、规则、冲突、待确认问题），由 WikiMaintainer 子 agent 维护
- `backend/.claude/skills/artifact-generation-guidelines/SKILL.md`
  - 适用：文档稿、页面方案、交互稿的生成边界

这些 skill 只服务后端 CAS 运行时，不等于“功能已经接通”。

**项目根目录 skill（适用于整个仓库）：**

- `agentic-code-review`（`.claude/skills/agentic-code-review/`）- 分层风险的
  代码审查工作流，用于 agent 生成的变更；爆炸半径分级、多视角 AI 审查、
  失败模式清单。不属于后端运行时 skill。

## 当前项目基线

- 当前仓库里已有一批前后端探索代码，但它们不是天然正确的正式基线。
- 是否保留某段代码，以它是否符合当前 `spec` 和 `todo` 为准。
- 新版产品感和交互基线看 `archive/legacy-demo/`。
- 新版可以重写样式和实现，但不能退化成后台表单页或配置页。

## 正式技术路线

- 主智能体：`Claude Agent SDK`
- 证据层：`Docling + Qdrant + LlamaIndex + 项目内 EvidenceRuntime`
- 综合层：`LLM Wiki`（项目内 markdown 页面，由 `WikiMaintainer` 子 agent 通过 Claude Agent SDK 维护）

不要做这些事：

- 用本地规则拼接结果，却命名成 `ClaudeAgentRuntime`
- 用本地摘要服务，却命名成 `EvidenceRuntime`
- 用 Python 模板渲染 markdown，却命名成 `LLMWikiService` / `WikiRuntime`
- 在文档、注释、UI 里把 stub 写成“已接入正式 provider”
- 未配置时做静默 fallback

未配置就报未配置，失败就报失败。

### Wiki 与 RAG 的边界

- **RAG = 证据层**：chunk 级、可追到原文行号的 citation。`confirmed_items` 与 artifact 的 `source_refs` 必须只来自 `query_project_evidence` 的真实返回。
- **Wiki = 综合层**：跨多源的合成、术语、规则、冲突、待确认问题。Wiki 页面里的每条断言必须 front-matter 带 `source_ids`，回查时仍走 RAG 取原文。
- 不允许把 wiki 段落当作 citation 给前端；不允许在 RAG 不可用时让 wiki 顶替证据层。
- ingest 成功后 wiki 维护是 fire-and-forget 后台任务；wiki 失败不回滚 RAG。

## 项目内依赖边界

- 运行依赖、脚本、数据目录优先放项目内，不默认吃用户家目录里的安装
- 不能把“我电脑上刚好有”当成项目能力
- provider、CLI、skill、认证态、数据目录都要先确认是不是项目内路径
- 如果还必须依赖用户手工登录或授权，要明确指出“只差这一步必须人工完成”

## Backend CAS 边界

- 后端服务启动目录默认是 `backend/`
- CAS 在这个项目里的 project cwd 也固定为 `backend/`
- `backend/CLAUDE.md` 和 `backend/.claude/**` 只服务于后端 CAS
- 根目录的项目文档和开发规则，不是 CAS 的运行时提示词来源
- 如果代码、文档、脚本仍把 CAS 作用域写成仓库根目录，视为未对齐

## 开发原则

### 宿主和 CAS 的分工

- 后端默认采用“薄宿主 + 单 Agent loop”思路，不走厚 `ChatService` 编排
- 宿主负责：
  - HTTP / SSE
  - tool / MCP 注册
  - 持久化
  - 超时与错误处理
  - 事件转发
- 宿主不应该替模型做大量业务判断，例如：
  - 先固定查 项目知识库 再聊天
  - 根据关键词猜要不要写沉淀
  - 根据 assistant 文本二次推断要不要生成 artifact
  - 用一长串 if / else 模拟需求分析流程

### Skill / Tool / MCP 原则

- skill 提供长期稳定的方法参考，不保存当前项目的动态状态
- tool 是模型可调用的真实动作能力，不是宿主内部 if / else 的别名
- MCP 适合承载外部能力或值得独立复用的能力面，不要滥拆
- 不要把同一大段策略同时塞进 `backend/CLAUDE.md`、runtime prompt、skill、tool description

### 前后端事件原则

- 前端应展示真实 agent loop 事件，不展示宿主虚构步骤
- `assistant_status`、tool running/completed、patch、artifact、version 应来自真实运行结果
- 右侧沉淀、版本、交付物应由真实 patch 驱动，不靠正文关键词猜

## 本地环境规则

- Python 相关命令默认走 `backend/.venv/bin/...`
- 前端命令默认在 `frontend/` 目录执行
- 跑测试、起服务、做接口验证前，先确认当前 worktree 的本地环境可用
- 如果命令失败，先区分：
  - 路径用错
  - 当前 worktree 环境没装
  - 项目依赖确实缺失


### Pre-push AI 审查

pre-push hook 会在每次 push 前用项目配置的 LLM 运行 `agentic-code-review`
skill。审查是传感器，不是裁决：它打印发现并请求确认，由人决定是否合并。

每个 clone 启用一次：

```
git config core.hooksPath .githooks
```

hook 脚本（`scripts/pre-push-review.py`）使用 `backend/.venv/bin/python`，
从 `backend/.env.local` 加载 LLM 凭据。如果 LLM 未配置，它会警告并放行 push。
无需外部 API key。

## Preflight

开始实现或验收前，默认先做这些检查：

1. 对齐文档：
   - `docs/product/fullstack-phase1-spec.md`
   - `docs/planning/fullstack-phase1-todo.md`
   - `AGENTS.md`
2. 如果当前任务涉及后端 CAS，再对齐：
   - `backend/CLAUDE.md`
   - 必要的 backend skills
3. 先验证 provider readiness，不要先写功能再补检查

以下任一项没过，都不能把主链路说成“已打通”：

- `Claude Agent SDK` 可调用
- `CLAUDE_MODEL` 已配置
- 项目内 `Docling + Qdrant + LlamaIndex` provider 可调用
- 项目内 项目知识库 认证已完成
- 当前项目已初始化自己的 knowledge base
- LLM Wiki 维护链路可调用：WikiMaintainer 注入、Claude SDK 就绪、`POST /wiki/maintain?probe=true` 能在 `wiki/.health` 写入并验证标记

## 实现中持续检查

- 不允许把“路径存在”“类名像真的”“接口壳子跑起来”当成“provider 已接通”
- 不允许把 stub、mock、fallback 命名成正式 provider
- 不允许把本机个人环境中的现成状态，当成项目正式能力
- 做前端时，不能只看功能通不通，还要对照 `archive/legacy-demo/` 检查产品感有没有退步成后台表单页
- 每补一条主链路，都要同步补失败路径，而不是只补成功路径

## 收尾验收

收尾时至少逐项检查这些：

- 文档对齐检查
- provider 真伪检查
- UI 对齐检查
- 失败路径检查
- Chrome DevTools 联调检查
- 必要时的专项 review

只要 preflight 没过，或关键验收项没过，就不能包装成“基本可用”。

## 默认实现顺序

如果用户没有明确改顺序，就按这个来：

1. 先对齐文档和规则
2. 再清理误导性的旧实现
3. 再重建前端工作台
4. 再接真实 provider
5. 最后做联调和验收
