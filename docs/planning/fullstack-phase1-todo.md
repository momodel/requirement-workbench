# 客户需求转译台 全栈一期 Todo

## 1. 文档用途

这份 todo 只做两件事：

- 记录当前一期真实进度
- 收敛接下来还要完成什么

它不是历史流水账，也不再沿用“全部推倒重来”的旧口径。

配套规格见：

- [客户需求转译台 全栈一期 Spec](../product/fullstack-phase1-spec.md)

## 2. 当前状态快照

当前仓库已经不是单纯 demo 壳，主路径已经切成：

- `frontend/`：项目列表 + 三栏工作台
- `backend/`：FastAPI + SQLite + SSE + provider 接入
- `data/`：项目文件、artifact、NotebookLM 本地数据

当前这版的真实基线是：

- 前端工作台已经接真实 API，不再靠纯前端阶段页驱动
- NotebookLM 正式 provider 已切到 `notebooklm-py`
- Claude 正式运行时已接 `claude-agent-sdk` 和 `claude` CLI
- 后端 CAS skills 收口在 `backend/.claude/skills/`
- 后端 CAS project cwd 已固定为 `backend/`
- `archive/legacy-demo/` 只作为视觉、交互和叙事基线

## 3. 已完成

### 3.1 文档和规则

- [x] 主规格重写到“全栈一期”口径
- [x] `AGENTS.md` 补充项目级基本规则
- [x] 项目级方法论 skill 已建立并纳入项目级运行时
- [x] NotebookLM 工作流 skill 已迁到 `backend/.claude/skills/`
- [x] 交付物生成约束 skill 已建立
- [x] 后端 CAS 全局规则已迁到 `backend/CLAUDE.md`
- [x] 旧 demo、旧文档、旧 HTML 原型已归档到 `archive/legacy-demo/`

### 3.2 前端主路径

- [x] 首页改成项目列表页
- [x] 工作台主路由切到 `/projects/:projectId/workbench`
- [x] 三栏结构已经接通真实后端数据
- [x] 左栏 source 支持文本导入
- [x] 左栏 source 支持文件上传
- [x] 左栏 source 支持多文件上传
- [x] 左栏 source 支持删除
- [x] 左栏 source 支持 `sync_failed` 后重试同步
- [x] source 文件卡片改成更紧凑的两行信息布局
- [x] source 摘要改成悬浮浮卡，不再塞到滚动区底部
- [x] 中栏聊天支持回车发送、`Shift + Enter` 换行
- [x] 中栏 assistant 内容支持 Markdown 渲染
- [x] 右栏沉淀总集已接通真实 state API
- [x] 文档稿保留在抽屉查看
- [x] 页面方案 / 交互稿走大预览层，不再挤在窄抽屉里
- [x] 工作台已补返回项目列表入口

### 3.3 后端主路径

- [x] FastAPI 应用入口已建立
- [x] SQLite 初始化和 seed project 初始化已建立
- [x] 项目、source、state、version、artifact 基础路由已建立
- [x] `GET /api/health` 已建立
- [x] SSE 聊天主路由已建立
- [x] source 标准化、入库、落盘主路径已建立
- [x] source 删除时已补本地与 notebook 侧删除联动
- [x] source 同步失败状态已统一为 `sync_failed`
- [x] 项目级 notebook binding、create-and-bind、library 查询 API 已建立

### 3.4 Provider 接入

- [x] `claude-agent-sdk` Python 依赖已进入 `backend/requirements.txt`
- [x] Claude 运行时已显式依赖 `claude` CLI 或 `CLAUDE_CODE_CLI_PATH`
- [x] `notebooklm-py` 已作为正式 NotebookLM provider 接入
- [x] NotebookLM 认证路径已改为项目内 `data/notebooklm/`
- [x] source 自动同步 notebook 的文本和文件主路径已接通
- [x] Notebook query 结果已映射回本地 source 引用
- [x] 新项目和 seed project 都有项目级 notebook binding 模型

### 3.5 CAS 风格主链路

- [x] 后端聊天主链路已收成单 Agent SDK loop
- [x] `ChatService` 已降为薄宿主，只负责持久化、SSE 转发和错误处理
- [x] NotebookLM 查询已改成 agent 可调用工具，不再由宿主前置固定查询
- [x] 状态写入、版本快照、artifact 生成都已收口到 runtime 工具
- [x] 前后端已按统一 loop 事件协议对接 `assistant_status / message_chunk / citations / *_patch`
- [x] 前端五步轨道已降级为弱语义投影，不再依赖正文关键词猜阶段
- [x] `backend/CLAUDE.md` 已补全后端 CAS 全局硬规则

## 4. 进行中

### 4.1 聊天主链路加固

- [ ] 继续压缩 Claude 首 token 时间和正文粒度，减少碎片化 chunk
- [ ] 收短讨论轮正文，避免回答过长
- [ ] 继续优化工具调用前后的状态展示和行动反馈
- [ ] 继续压缩“发送问题后长时间停顿”的体感

### 4.2 NotebookLM 体验加固

- [ ] 排查真实 NotebookLM 模式下 tool 调用失败或不可用的原因
- [ ] 为 notebook library 和 readiness 补更清楚的 loading 态
- [ ] 减少全页等待，把 NotebookLM 慢请求的影响限制在局部区域
- [ ] 为新项目默认 notebook 绑定补更顺手的引导

### 4.3 上下文连续性

- [ ] 当前按“一个项目一个主会话”收口 conversation 语义
- [ ] 确保同一项目下聊天上下文连续，不再出现“看不到上一轮问题”的误解
- [ ] 明确 `conversation_id` 的项目级绑定策略并补文档说明

## 5. 下一批要完成

### 5.1 Artifact 真实生成

- [ ] 文档稿生成链路继续打磨为稳定可演示版本
- [ ] 页面方案 HTML 输出继续做结构校验和空壳校验
- [ ] 交互稿 HTML 输出继续做结构校验和空壳校验
- [ ] artifact 成功和失败状态继续细化到右栏和大预览层
- [ ] artifact 生成成功后自动补版本快照

### 5.2 状态沉淀和版本

- [ ] 继续校准哪些讨论轮只聊天、不落盘
- [ ] 继续减少“过度沉淀”导致的延迟和噪音
- [ ] 版本快照触发条件再收紧一轮
- [ ] 右栏版本区补齐时间、触发原因、摘要

### 5.3 Source 侧补强

- [ ] URL 导入入口补齐到 UI
- [ ] source 标准化结果展示再做一轮可读性整理
- [ ] source 异常信息和同步错误信息再收敛成统一文案
- [ ] source 上传后的局部 loading、错误、重试态继续细化

### 5.4 UI 回到正确产品感

- [ ] 继续对齐 `archive/legacy-demo` 的产品感基线
- [ ] 继续压缩顶部栏高度，只保留有用信息
- [ ] 持续避免页面退化成后台表单页
- [ ] 把工作台的紧凑度、信息密度和可讲解性再收一轮

## 6. 后续阶段清单

### Phase A: Provider 真伪和失败路径验收

- [ ] 检查 Claude 主路径是否全部真走 `claude-agent-sdk + claude CLI`
- [ ] 检查 NotebookLM 主路径是否全部真走 `notebooklm-py`
- [ ] 清理残留的误导性命名、注释和文档
- [ ] 未配置 Claude 时必须明确报错
- [ ] 未认证 NotebookLM 时必须明确报错
- [ ] 项目未绑定 notebook 时必须明确报错
- [ ] NotebookLM 查询超时时必须明确报错
- [ ] artifact 生成失败时必须明确报错
- [ ] 不允许静默 fallback 成本地假成功

### Phase B: 方法论落地

- [ ] 继续把 `BABOK / JTBD / Event Storming` 的视角从 prompt 说明推进到服务层约束
- [ ] 明确什么情况下写入 `current_understanding`
- [ ] 明确什么情况下写入 `pending_items`
- [ ] 明确什么情况下写入 `confirmed_items`
- [ ] 明确什么情况下写入 `conflict_items`
- [ ] 明确什么情况下升级为 `mvp_items`
- [ ] 补针对方法论输出的自动化测试，避免只剩术语标签

### Phase C: 联调与专项验证

- [ ] 按文档重新跑一遍从安装到启动的 onboarding 验收
- [ ] 用 Chrome DevTools 重跑首页、上传、聊天、artifact 预览全链路
- [ ] 检查控制台和网络请求，确认没有静默失败
- [ ] 必要时做 provider 真伪专项 review
- [ ] 必要时做 UI 对齐专项 review
- [ ] 必要时做失败路径专项 review

## 7. 当前验收口径

后续不再只写“测试通过”，而是按下面几类分别验：

- [ ] 文档对齐检查
- [ ] provider 真伪检查
- [ ] UI 对齐检查
- [ ] 失败路径检查
- [ ] Chrome DevTools 联调检查
- [ ] 必要时的专项 AI review

## 8. 近期执行顺序

接下来默认按这个顺序继续推进：

1. 继续压缩聊天首响应时间，拆开流式输出和结构化沉淀
2. 补强 NotebookLM 慢查询和超时的前后端反馈
3. 收口 artifact 生成、校验和预览
4. 收口版本快照和关键轮次沉淀
5. 继续把 UI 拉回到 `archive/legacy-demo` 的产品感基线
6. 跑一轮完整联调和专项验收

## 9. 文档联动

当前这份 todo 配套这些文档一起看：

- [产品规格](../product/fullstack-phase1-spec.md)
- [文档索引](../README.md)
- [项目根 README](../../README.md)
- [后端运行规则](../../backend/CLAUDE.md)
