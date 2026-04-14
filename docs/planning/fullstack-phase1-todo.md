# 客户需求转译台 全栈一期 Todo

## 1. Summary

这份文档只回答“怎么做”和“按什么顺序做”。

- 范围：`全栈一期`
- 目标：在当前仓库上补齐真实前后端闭环
- 原则：旧 demo 归档为参考资产，新主工程围绕 `frontend/`、`backend/`、`data/`、`docs/` 继续推进

配套规格说明见：[客户需求转译台 全栈一期 Spec](../product/fullstack-phase1-spec.md)

## 2. 实施顺序

建议按下面 11 个阶段推进，优先保证“能跑通一条完整链路”，再补能力和稳定性。

1. 工程基线与目录重组
2. SQLite 与状态模型
3. 项目与 Source API
4. Source Ingestion 管线
5. NotebookLM 证据服务
6. Claude Agent Runtime
7. SSE 聊天与状态 patch
8. 前端状态改造
9. 自动版本快照
10. Artifact 自由生成
11. 演示加固

## 3. Todo List

### Phase 1: 工程基线与目录重组

- [ ] 把旧 demo 前端、原型、PDF、zip 和历史文档统一归档到 `archive/legacy-demo/`
- [ ] 新建 `frontend/`, `backend/app/`, `data/sqlite/`, `data/projects/` 目录
- [ ] 在根目录补充新的仓库说明和前后端分开启动说明
- [ ] 明确前端默认端口与后端默认端口
- [ ] 新前端从 `frontend/` 目录启动
- [ ] 旧 demo 只保留为参考资产，不再占据主路径

### Phase 2: SQLite 与状态模型

- [ ] 设计并实现首版 SQLite schema
- [ ] 写数据库初始化逻辑，应用启动时自动建表
- [ ] 建立 `Project / Source / Message / Understanding / Conflict / MVP / Version / NotebookBinding / DemoArtifact` 的存取层
- [ ] 定义内部状态聚合函数，能把多表结果聚合成 `GET /state` 的前端消费对象
- [ ] 预置 `业财逐笔对账` seed project 及其 seed sources / seed state

### Phase 3: 项目与 Source API

- [ ] 实现项目创建接口
- [ ] 实现项目列表接口
- [ ] 实现项目详情接口
- [ ] 实现 source 上传接口，支持文本、文件、URL 三类入口
- [ ] source 上传成功后先写本地文件，再写 SQLite 记录，再异步触发标准化与 NotebookLM 同步
- [ ] source 列表接口返回解析状态、同步状态、摘要、错误信息
- [ ] 前端左栏切换到真实 source API
- [ ] 保留现有卡片风格与悬浮摘要交互

### Phase 4: Source Ingestion 管线

- [ ] 文本粘贴：直接生成 text source 和 summary
- [ ] PDF / DOCX / Markdown / Text：提取纯文本并生成摘要文件
- [ ] 图片：生成视觉描述文本并生成 notebook-friendly 文本源
- [ ] 音频：转写为文本后生成 notebook-friendly 文本源
- [ ] XLSX：提取 sheet、表头、样例行、统计摘要，并生成 Markdown / 文本版标准化文件
- [ ] 飞书纪要：只支持粘贴文本或导出文件上传，不做账号连接
- [ ] 每类 source 都统一输出 `normalized_path + parse_summary + parse_status`

### Phase 5: NotebookLM 证据服务

- [ ] 实现 `NotebookLMService` 接口与首版 provider
- [ ] 每个项目首次需要 NotebookLM 时自动创建 notebook binding
- [ ] source 标准化完成后自动导入对应 notebook
- [ ] 实现“按项目 + source 上下文查询 grounding summary / citations”能力
- [ ] 失败时回写 `sync_status`
- [ ] 确保同步失败不阻塞主项目状态
- [ ] 明确 notebook 内 source 与本地 source 的映射关系

### Phase 6: Claude Agent Runtime

- [ ] 实现 `AgentRuntime` 接口与 `ClaudeAgentRuntime`
- [ ] 输入给 runtime 的上下文锁定为：项目摘要、最近消息、聚合状态、相关 source 摘要、NotebookLM grounding
- [ ] runtime 输出锁定为：assistant 文本、citations、状态 patch、是否触发 artifact 生成、是否触发版本快照
- [ ] 主 runtime 不直接写库；只返回结构化结果给后端 service
- [ ] 明确 prompt 结构：角色设定、方法论步骤、输出格式、artifact 生成规则、禁止事项

### Phase 7: SSE 聊天与状态 Patch

- [ ] 实现 `POST /api/projects/{project_id}/chat/stream`
- [ ] 聊天开始后先写 user message，再调用 NotebookLM，再调用 Claude runtime
- [ ] assistant 文本按 chunk 流出
- [ ] citations 与 patch 作为独立 SSE 事件并行发送
- [ ] patch 入库成功后再发对应 SSE 事件
- [ ] 避免前端显示与数据库状态不一致
- [ ] 关键阶段自动创建版本快照，并通过 `version_patch` 发给前端

### Phase 8: 前端状态改造

- [ ] 前端增加 API client 和 SSE client
- [ ] 聊天区从 `demoData.ts` 进度驱动改为真实消息与 SSE 驱动
- [ ] 右栏沉淀总集从静态数组改为接收 patch 后更新 store
- [ ] 首页改成项目列表页
- [ ] 默认自动展示 seed project
- [ ] 维持已确认交互：文件摘要浮窗顶置、大预览层展示 HTML 交付物、文档稿留在抽屉
- [ ] 若后端不可达，允许切回本地 mock seed，仅作为开发 fallback，不作为主验收路径

### Phase 9: 自动版本快照

- [ ] 后端实现关键轮次自动生成版本快照
- [ ] 前端右栏展示当前版本与历史版本列表
- [ ] 快照详情至少展示：触发原因、时间、摘要
- [ ] 不做版本 diff、回滚和冲突合并

### Phase 10: Artifact 自由生成

- [ ] 文档稿生成：主模型输出结构化 sections，落盘 JSON
- [ ] 页面方案生成：主模型输出页面说明 + HTML 原型
- [ ] 交互稿生成：主模型输出流程说明 + HTML 原型
- [ ] 为 HTML 输出增加最小校验器：标题、页面区块、主要导航、无外链脚本
- [ ] 保存 artifact 元数据与落盘路径
- [ ] 前端从 `GET /artifacts` 读取并展示
- [ ] HTML artifact 继续用大预览层展示，保证演示体验

### Phase 11: 演示加固

- [ ] 固化 seed project、seed messages、seed sources
- [ ] 为 Claude / NotebookLM / artifact generation 各自加失败降级提示
- [ ] 前端补 loading、empty、error 状态
- [ ] 明确“无网 / NotebookLM 失败 / 主模型失败”三类 fallback 演示路径
- [ ] 补一份演示脚本，说明从新建项目到生成 artifact 的标准路径

## 4. 验收与测试清单

### 4.1 后端单元测试

- [ ] source 标准化输出符合预期
- [ ] SQLite 聚合状态能正确生成 `current / pending / confirmed / conflict / mvp / version / artifact`
- [ ] 关键轮次会自动生成版本快照
- [ ] artifact 校验器能拒绝空 HTML、缺标题 HTML、含外链脚本 HTML

### 4.2 后端集成测试

- [ ] 创建项目后可以读取详情
- [ ] 上传 PDF / DOCX / XLSX / 图片 / 音频样本时，能得到 source 记录与标准化结果
- [ ] NotebookLM 同步失败时 source 状态正确，不影响项目继续聊天
- [ ] `POST /chat/stream` 能顺序输出 `message_chunk -> citations -> patch -> done`
- [ ] artifact 生成成功后，`GET /artifacts` 能读到最新结果

### 4.3 前端测试

- [ ] 首屏可加载项目列表与默认 seed project
- [ ] source 上传、source 状态刷新、source 摘要浮窗正常
- [ ] 聊天区能消费 SSE 并滚动到最新消息
- [ ] 右栏能根据 patch 更新
- [ ] 文档稿走抽屉
- [ ] 页面方案和交互稿走大预览层
- [ ] 文件摘要浮窗每次打开滚到顶部
- [ ] 版本列表在关键轮次自动新增

### 4.4 端到端验收

- [ ] 新建项目
- [ ] 上传至少一种真实 source
- [ ] 发起一次聊天并看到流式输出
- [ ] 右栏同步出现理解项与待确认项
- [ ] 在关键轮次看到自动版本快照
- [ ] 生成至少一个文档稿和一个 HTML artifact
- [ ] 页面方案 HTML 能被大预览层打开
- [ ] 前后端分开启动后，可稳定完成整条演示链路

## 5. 实施约束

- [ ] 一期按单用户、本地演示环境实现
- [ ] 不做登录、多租户、权限系统
- [ ] 主产品是通用转译台，业财对账只是默认演示案例
- [ ] NotebookLM 只做资料理解层，不做项目状态管理
- [ ] 主智能体首版使用 `Claude Agent SDK`，但服务层必须保留适配接口
- [ ] `XLSX` 与 `飞书纪要` 先服务端转换 / 规范化，再接 NotebookLM
- [ ] artifact 采用模型自由生成，但必须经过后端校验与落盘
- [ ] 自动版本快照只做新增与展示，不做 diff 或回滚
