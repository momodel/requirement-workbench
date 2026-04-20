# Repository Guidelines

## 先看什么

在这个项目里开始实现前，先读这几份文档：

- `docs/product/fullstack-phase1-spec.md`
- `docs/planning/fullstack-phase1-todo.md`
- `backend/.claude/skills/requirement-analysis-methodology/SKILL.md`
- `backend/.claude/skills/notebooklm-evidence-workflow/SKILL.md`
- `archive/legacy-demo/README.md`

如果文档和现有代码冲突，以文档为准。

## 当前项目状态

这个仓库里已经有一批前后端探索代码，但它们不是当前一期的实现基线。

处理原则：

- 不把当前 `frontend/`、`backend/` 里的半成品直接当成既定事实
- 不把类名像真实 provider 的 stub 当成正式接入
- 是否保留某段代码，以它是否符合当前 spec 为准

## 产品和交互基线

新版工作台的产品感和交互基线看 `archive/legacy-demo/`。

意思是：

- 可以重写样式和实现
- 但整体体验至少要恢复到 legacy demo 的工作台水准
- 不要把新版做成后台表单页或配置页

## Provider 约定

一期当前确认的正式路线是：

- 主智能体：`Claude Agent SDK`
- 证据层：`notebooklm-py`

不要做这些事：

- 用本地规则拼接结果，却命名成 `ClaudeAgentRuntime`
- 用本地摘要服务，却命名成 `NotebookLMService`
- 在文档、注释、UI 里把 stub 写成“已接入正式 provider”

未配置就报未配置，失败就报失败，不做伪装 fallback。

## 项目内依赖边界

这个项目后面要封装成服务部署，所以默认原则是：

- 运行依赖、脚本、数据目录优先放项目内，不默认吃用户家目录里的安装
- 不能把“我电脑上刚好有”当成项目能力
- 凡是 provider、CLI、skill、认证态、数据目录，都要先确认是不是项目内路径
- 如果还必须依赖用户侧手工登录或授权，要明确指出“只差这一步必须人工完成”

## Skill 放置规则

- 后端运行时使用的 Claude 相关 skill，统一维护在 `backend/.claude/skills/**/SKILL.md`
- `Claude Agent SDK` 在本项目里不依赖“自动扫描 skill 目录”来运行，后端代码会显式读取 `backend/.claude/...`
- 根目录 `.claude/` 不作为后端运行时的正式来源
- `tools/` 里的内容默认只是 vendored 代码、脚本或 provider runtime，不算 Claude 自动发现 skill
- 不要把放在 `tools/` 里的外部仓库写成“Claude 会自动读取的 skill”

## 本地环境与验证

- Python 相关命令默认走项目内 `backend/.venv/bin/...`
- 前端命令默认在 `frontend/` 目录执行，不用全局 Node 环境代替项目依赖检查
- 跑测试、起服务、做接口验证前，先确认当前 worktree 里的本地环境可用
- 不能因为系统 Python / 全局包缺东西，就直接判断“项目没配环境”
- 如果命令失败，要先区分是：
  - 路径用错
  - 当前 worktree 环境没装
  - 项目依赖确实缺失

## 提前检查，不要等用户撞错

- 进入实现或验收前，先主动检查 `Claude Agent SDK`、`CLAUDE_MODEL`、`NotebookLM` runtime、认证态、项目 notebook 绑定状态
- 这些状态要优先在后端 readiness 和前端界面里展示
- 不要等用户点到聊天、上传、生成交付物时报错了，才说“还没配”

## Preflight 和验收规则

下面这些不是“建议”，而是默认硬门槛。

### 开工前必须先过的 preflight

- 先核对当前实现是否仍然符合：
  - `docs/product/fullstack-phase1-spec.md`
  - `docs/planning/fullstack-phase1-todo.md`
  - `AGENTS.md`
  - `backend/.claude/skills/requirement-analysis-methodology/SKILL.md`
  - `backend/.claude/skills/notebooklm-evidence-workflow/SKILL.md`
- 如果文档、skill、代码三者不一致，先对齐再继续实现
- 先验证 provider readiness，不要先写功能再补检查
- 以下任一项没过，都不能把主链路说成“已打通”：
  - `Claude Agent SDK` 可调用
  - `CLAUDE_MODEL` 已配置
  - 项目内 `notebooklm-py` provider 可调用
  - 项目内 NotebookLM 认证已完成
  - 当前项目已绑定自己的 notebook
- 如果某一项必须人工完成，要明确指出“只差这一步需要用户操作”，不要把其他未完成项混在一起

### 实现中必须持续检查的项

- 不允许把“路径存在”“类名像真的”“接口壳子跑起来”当成“provider 已接通”
- 不允许把 stub、mock、fallback 命名成正式 provider
- 不允许把本机个人环境中的现成状态，当成项目正式能力
- 做前端时，不能只看功能通不通，还要对照 `archive/legacy-demo/` 检查产品感有没有退步成后台表单页
- 每补一条主链路，都要同步补失败路径，而不是只补成功路径

### 收尾前必须逐项验收

- 文档对齐检查
  - `spec / todo / AGENTS / skills` 是否一致
  - 是否还残留旧路线、旧假设、误导性命名
- provider 真伪检查
  - 是否真的调用 `Claude Agent SDK`
  - 是否真的调用项目内 NotebookLM runtime
  - 是否还残留“看起来像真的”的本地替代实现
- UI 对齐检查
  - 是否仍然是分析工作台，而不是后台配置页
  - 是否至少恢复到 `archive/legacy-demo/` 的产品感基线
- 失败路径检查
  - 未配置、未认证、未绑定、provider 失败时，是否提前且明确提示
- Chrome DevTools 联调检查
  - 真实启动后检查页面、控制台、关键请求和交互
- 必要时专项 review
  - provider review
  - UI review
  - 失败路径 review

### 明确禁止

- 不做“我觉得差不多可以了”式收尾
- 不做“测试过了一部分，所以整体算完成”式判断
- 不做“先继续往后写，最后再统一检查”式推进
- 只要 preflight 没过，或关键验收项没过，就必须直接说明没完成，不能包装成“基本可用”

## Project Skills

- `requirement-analysis-methodology`
  - 用在需求 intake、结构化分析、澄清问题、状态沉淀、MVP 收敛、artifact 触发判断
  - Path: `backend/.claude/skills/requirement-analysis-methodology/SKILL.md`

- `notebooklm-evidence-workflow`
  - 用在 source 标准化、NotebookLM 导入、grounded summary、citation 获取、失败回写
  - Path: `backend/.claude/skills/notebooklm-evidence-workflow/SKILL.md`

## 实现顺序

当前默认顺序是：

1. 先对齐文档和规则
2. 再清理误导性的旧实现
3. 再重建前端工作台
4. 再接真实 provider
5. 最后做联调和验收

如果用户没有明确改顺序，就按这个来。
