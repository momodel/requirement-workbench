# 仓库协作指南

> 英文版：[AGENTS.md](AGENTS.md)

这份文件是给人类贡献者和编码智能体（包括 CI 中运行的 OpenAI Codex 评审）看的，是双方的工作约定。改动之前请先阅读。

## 必读文档

任何实现任务，先从这三份开始读：

- `docs/product/fullstack-phase1-spec.md`
- `docs/planning/fullstack-phase1-todo.md`
- `archive/legacy-demo/README.md`

如果文档和现有代码说法不一致，以文档为准。

后端运行规则，请读：

- `backend/CLAUDE.md`
- `backend/.claude/skills/**/SKILL.md`

如果你的任务涉及到这些后端领域，请再读对应 skill：

- `requirement-analysis-methodology` —— 需求分析流程、状态聚合、版本快照、产物触发
- `rag-evidence-workflow` —— 源文件接入、项目知识库索引、接地、引用
- `llm-wiki-knowledge-workflow` —— LLM Wiki 合成层（实体页、术语表、规则、冲突、开放问题），由 WikiMaintainer 子智能体维护
- `artifact-generation-guidelines` —— 生成文档稿、页面方案、交互稿的边界约束

这些后端 skill 是后端运行时的参考资料，它们存在不代表功能已经接入。

对于项目级贡献，还有：
- `.claude/skills/agentic-code-review` —— 使用项目自身 LLM 做自动化本地预推送代码评审

## 项目基线

- 仓库已经有一些探索性的前后端代码，但默认都不视为权威实现
- 只有匹配当前 spec 和 todo 的代码才值得保留
- 产品感和交互基线在 `archive/legacy-demo/`
- 新工作可以重写样式和实现，但不能退步回后台表单或者设置页

## 技术方向

- 主智能体：LangChain 集成，兼容 Anthropic / OpenAI 协议 LLM
- 证据层：Docling + Qdrant + LlamaIndex + 仓库内 `EvidenceRuntime`
- 合成层：LLM Wiki（项目本地 markdown，由 WikiMaintainer 子智能体通过 LLM 维护）

不允许：

- 用本地规则拼结果就叫它 `ClaudeAgentRuntime`
- 跑一个本地摘要就叫它 `EvidenceRuntime`
- 用 Python 模板渲染 markdown 就叫它 `LLMWikiService` / `WikiRuntime`
- 在文档、注释或者 UI 里把 stub 说成“已接入的 provider”
- 未配置时静默 fallback

未配置就说未配置，失败就报告失败。

### Wiki 与 RAG 边界

- **RAG 是证据层**：块级引用可溯源到源文件行号。`confirmed_items` 和产物 `source_refs` 只能来自真实 `query_project_evidence` 返回
- **Wiki 是合成层**：跨源合成、术语表、规则、冲突、开放问题。wiki 页面上每个断言都必须在 front matter 带 `source_ids`，查询仍然走 RAG 拉取原文
- 绝对不能把 wiki 段落当引用传给前端，也不能在 RAG 不可用时用 wiki 顶替证据层
- 接入成功后，wiki 维护是后台即发即忘任务，wiki 失败不回滚 RAG

## 依赖边界

- 优先用仓库内的运行时、脚本、数据目录，而不是依赖开发者个人目录里装的东西
- “我机器上刚好有”不是项目能力
- 确认 provider、CLI、skill、认证状态、数据目录都能解析到仓库内路径
- 如果某一步仍然需要手动登录授权，必须明确说出来，告诉人类这是他们必须做的一步

## 后端 CAS 作用域

- 后端服务默认从 `backend/` 启动
- 智能体的项目 cwd 也固定到 `backend/`
- `backend/CLAUDE.md` 和 `backend/.claude/**` 只给后端运行时使用
- 根目录项目文档和开发规则不是运行时 prompt 来源
- 如果任何代码、文档、脚本仍然把运行时作用域当成仓库根，视为未对齐

## 开发原则

### 宿主与智能体责任划分

- 后端采用“瘦宿主 + 单智能体循环”架构，不搞重型 `ChatService` 编排
- 宿主负责：HTTP / SSE、工具 / MCP 注册、持久化、超时错误处理、事件转发
- 宿主绝对不能替模型做业务判断，比如：
  - 总是在聊天前先查知识库
  - 从关键词猜是否要写状态
  - 从助手文本反推是否要生成产物
  - 用长 if/else 链模拟分析流程

### Skill / 工具 / MCP 原则

- Skill 是长效方法论参考，不存项目动态状态
- 工具是模型能调用的真实动作，不是宿主侧 `if/else` 的别名
- MCP 给外部能力或者值得复用的能力开口，不要过度拆分
- 不要把同一个大策略重复写在 `backend/CLAUDE.md`、运行时 prompt、skill、工具描述四个地方

### 前端/后端事件原则

- 前端显示真实的智能体循环事件，不是宿主编造的步骤
- `assistant_status`、工具运行/完成、patch、产物、版本事件都来自真实运行结果
- 右侧状态、版本、交付物都是真实 patch 驱动，不是从消息文本猜出来的

## 本地环境

- Python 命令走 `backend/.venv/bin/...`
- 前端命令从 `frontend/` 执行
- 在跑测试、启服务、验证端点前，先确认当前工作树本地环境没问题
- 命令失败时，先区分：路径错了、环境没装、还是真缺依赖

## 起飞检查

实现或接受工作前，先跑这些检查：

1. 和文档对齐：`docs/product/fullstack-phase1-spec.md`、`docs/planning/fullstack-phase1-todo.md`、`AGENTS.md`
2. 如果碰后端运行时，再和 `backend/CLAUDE.md` 以及相关后端 skill 对齐
3. 先验证 provider 就绪，不要做完功能再补检查

只有全部满足这些，才能说主路已经接通：

- 兼容 LLM 可调用
- `LLM_MODEL`（旧环境变量名：`CLAUDE_MODEL`）已配置
- 仓库内 `Docling + Qdrant + LlamaIndex` provider 可调用
- 项目知识库已认证
- 当前项目已经初始化自己的知识库
- LLM Wiki 维护路径可调用：WikiMaintainer 已注入、LLM 就绪，且 `POST /wiki/maintain?probe=true` 能在 `wiki/.health` 写入并验证标记

## 持续检查

- 路径存在、类名看起来真实、接口壳启动了，不代表 provider 已经接通
- 不用真实 provider 的名字命名 stub、mock、fallback
- 不要把你个人环境里的现成状态当成项目能力
- 前端不能只检查功能能用，还要和 `archive/legacy-demo/` 对比，确保产品感没有退步成后台表单
- 你加的每条主路径，也要把失败路径加上，不要只留开心通道

## 验收

收工时至少检查每一项：

- 文档对齐
- provider 真实性
- UI 对齐
- 失败路径
- Chrome DevTools 集成
- 需要的地方做聚焦评审

如果起飞检查或者关键验收项不通过，不要包装成“基本能用”

## 默认工作顺序

除非用户改顺序，否则跟着这个走：

1. 对齐文档和规则
2. 删掉误导性的旧实现
3. 重造前端工作台
4. 接通真实 provider
5. 集成验收
