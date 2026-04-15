# 客户需求转译台 全栈一期 Handoff

## 1. 当前工作目录

- 仓库路径：
  - `/Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap`
- 当前分支：
  - `codex-fullstack-phase1-bootstrap`

## 2. 本轮已经完成的内容

### 2.1 工程结构

- 旧 demo、原型、PDF、zip、历史文档已经归档到 `archive/legacy-demo/`
- 主工程目录已经切到：
  - `frontend/`
  - `backend/`
  - `data/`
  - `docs/`
- 项目级 skills 已创建：
  - `.claude/skills/requirement-analysis-methodology/`
  - `.claude/skills/notebooklm-evidence-workflow/`
- `AGENTS.md` 已更新
- `.codex/config.toml` 已写入：

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

注意：
- 这只是项目配置文件
- 当前旧会话的实际权限并没有自动升级

### 2.2 后端

后端已经不是纯占位骨架，当前具备一条可测试的本地闭环：

- SQLite schema 已落地
- `init_db()` 会自动建表并写入 seed data
- seed project、seed sources、seed state、seed messages、seed version 已落库
- `projects / sources / state / chat / versions / artifacts` 路由已接通
- Source ingestion 已支持：
  - text
  - url
  - file
- 标准化输出会生成：
  - 原始文件
  - `normalized.md`
  - `parse_summary`
  - `parse_status`
- `NotebookLMService` 适配层已落地：
  - notebook binding
  - source sync status
  - grounding summary
  - citations
- `AgentRuntime` 适配层已落地：
  - assistant 文本
  - citations
  - state patches
  - artifact requests
  - version summary
- `chat_service` 已支持：
  - 存储 user / assistant message
  - 查询 evidence
  - 产出 `message_chunk`
  - 产出 `citations`
  - 产出状态 patch
  - 自动生成版本快照
  - 可触发 artifact 生成
- `artifact_generation` 已支持：
  - `document`
  - `page_solution`
  - `interaction_flow`
- HTML artifact 已有最小校验器：
  - 必须包含 `<title>`
  - 必须包含 `<main>`
  - 必须包含 `<nav>`
  - 禁止外链 script
  - 禁止外链 href
- artifact 已落盘到：
  - `data/projects/<project-id>/artifacts/<artifact-id>/`

### 2.3 前端

前端已经从 seed-only demo 改成 backend-first workbench：

- 首页已切到项目列表 + 新建项目
- 工作台保留三栏结构：
  - Sources
  - Chat
  - Project State
- 左栏已支持：
  - 导入文本资料
  - 导入链接资料
  - 导入文件资料
  - 查看 source 摘要浮窗
- 中栏已支持：
  - 调用真实 chat API
  - 消费 SSE 事件
  - 逐步渲染 chat events
- 右栏已支持：
  - 当前理解
  - 待确认项
  - 已确认项
  - 冲突项
  - MVP
  - 版本
  - 交付物
- 文档稿走大文本预览
- 页面方案 / 交互稿走 HTML 大预览层
- 后端不可达时仍保留本地 fallback

### 2.4 文档

下面这些文档已经更新：

- `README.md`
- `docs/README.md`
- `docs/product/fullstack-phase1-spec.md`
- `docs/planning/fullstack-phase1-todo.md`
- `docs/demo/fullstack-phase1-demo-script.md`

## 3. 关键文件

### 3.1 后端核心

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/schema.sql`
- `backend/app/models.py`
- `backend/app/routes/projects.py`
- `backend/app/routes/sources.py`
- `backend/app/routes/chat.py`
- `backend/app/routes/versions.py`
- `backend/app/routes/artifacts.py`
- `backend/app/services/project_catalog.py`
- `backend/app/services/source_ingestion.py`
- `backend/app/services/notebooklm_service.py`
- `backend/app/services/agent_runtime.py`
- `backend/app/services/project_state.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/artifact_generation.py`
- `backend/app/services/seed_projects.py`

### 3.2 前端核心

- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/features/projects/ProjectsPage.tsx`
- `frontend/src/features/workbench/WorkbenchPage.tsx`
- `frontend/src/styles.css`

### 3.3 测试

- `backend/tests/`
- `frontend/src/lib/api.test.ts`
- `frontend/src/features/projects/ProjectsPage.test.tsx`
- `frontend/src/features/workbench/WorkbenchPage.test.tsx`

## 4. 当前验证结果

以下命令在当前会话里已经验证通过：

### 4.1 后端测试

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap
python3 -m unittest discover -s backend/tests -v
```

结果：
- 18 个测试全部通过

### 4.2 前端测试

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/frontend
npm test
```

结果：
- 8 个测试全部通过

### 4.3 前端构建

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/frontend
npm run build
```

结果：
- 构建通过

## 5. 当前没完成的事

这几项是一期里还没有真正收完的：

### 5.1 真实运行环境联调

当前旧会话里没能完成：

- 安装 `backend/requirements.txt`
- 真正起 `uvicorn`
- 真正起 `vite dev server`
- 用 Chrome DevTools 打开前端页面做浏览器验收

原因不是代码没写，而是旧会话的实际权限仍然受限：

- 无法出网
- 无法监听本地端口
- 无法写 `.git`

### 5.2 真实 provider 替换

现在的 `NotebookLMService` 和 `ClaudeAgentRuntime` 仍是本地可测试 provider。

它们已经有正式适配层接口，但还没替换成：

- 真实 Claude Agent SDK provider
- 真实 NotebookLM provider

### 5.3 git 提交与推送

当前还没有完成：

- `git add`
- `git commit`
- `git push`

原因：
- 当前旧会话不能写 `.git/worktrees/.../index.lock`

## 6. 旧会话里确认过的限制

以下命令在旧会话里都已经试过，并且确实失败：

### 6.1 pip 装依赖失败

```bash
cd backend
./.venv/bin/pip install -r requirements.txt
```

失败现象：
- 连不到 `fastapi` 包源
- 提示 `Failed to establish a new connection`

### 6.2 前端 dev server 起不来

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 4173
```

失败现象：
- `listen EPERM`

### 6.3 无法写 `.git`

尝试写：

```bash
touch /Users/zhaofengli/projects/requirement_nyl/.git/worktrees/codex-fullstack-phase1-bootstrap/perm-check
```

失败现象：
- `Operation not permitted`

## 7. 新会话接手后要做什么

新会话不要再重新整理 spec，也不要重复分析目录，直接按下面顺序做。

### 7.1 先确认权限真的升级了

先做 3 个探针：

1. 确认能写 `.git`

```bash
touch /Users/zhaofengli/projects/requirement_nyl/.git/worktrees/codex-fullstack-phase1-bootstrap/perm-check && rm /Users/zhaofengli/projects/requirement_nyl/.git/worktrees/codex-fullstack-phase1-bootstrap/perm-check
```

2. 确认能联网装依赖

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/backend
./.venv/bin/pip install -r requirements.txt
```

3. 确认能监听端口

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/frontend
npm run dev -- --host 127.0.0.1 --port 4173
```

### 7.2 起后端

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

先验：

```bash
curl http://127.0.0.1:8000/api/health
```

预期：

```json
{"status":"ok"}
```

### 7.3 起前端

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/frontend
npm install
npm run dev -- --host 127.0.0.1 --port 4173
```

### 7.4 用 Chrome DevTools 验收

打开：

- `http://127.0.0.1:4173/`

至少验这几项：

1. 首页项目列表能打开
2. 进入 `seed-reconciliation` 工作台
3. 导入文本资料
4. 导入链接资料
5. 聊天发一轮请求
6. 右栏能看到 patch 后的新状态
7. 生成文档稿
8. 生成页面方案
9. 生成交互稿
10. HTML artifact 能在大预览层打开
11. console 没有致命错误
12. network 关键请求返回正常

### 7.5 如有现场问题，优先修这些

如果起服务后有问题，优先看：

- API 路由响应结构是否和前端一致
- artifact content 接口是否返回正确 `media_type`
- 前端 SSE 消费是否有边界问题
- `parse_summary / sync_status / artifact list` 是否刷新一致
- `seed message / seed state / patch append` 是否有重复渲染

### 7.6 最后做 git 收尾

在新会话里完成：

```bash
cd /Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap
git add README.md docs .claude .codex AGENTS.md backend frontend
git commit -m "feat: advance fullstack phase1 workbench" -m "Issue: N/A"
git push origin codex-fullstack-phase1-bootstrap
```

如果分支名需要调整，先看：

```bash
git branch --show-current
```

## 8. 建议新会话的提示词

可以直接把下面这段发给新会话：

```text
继续这个项目，不要重新分析 spec。先读 docs/handoff/fullstack-phase1-handoff.md，然后直接接着做：
1. 确认当前会话已经具备 danger-full-access 和网络访问
2. 安装 backend 依赖并起 uvicorn
3. 起 frontend dev server
4. 用 Chrome DevTools 验收首页和工作台主流程
5. 修掉现场发现的问题
6. 跑后端测试、前端测试、前端构建
7. git add / commit / push
```

## 9. 补充说明

- 当前代码主目标不是“做得多漂亮”，而是已经把一期的主链路搭通
- 现在最缺的是：
  - 真机联调
  - 浏览器验收
  - git 收尾
- 新会话如果权限正确，应该很快就能接上，不需要再重做这轮代码
