# 客户需求转译台

这个仓库已经从“单个前端 demo 仓”切到“全栈一期主工程仓”。

当前目录按两个层次组织：

- 主工程
  - `frontend/`：新的一期前端工程
  - `backend/`：FastAPI 后端骨架
  - `data/`：SQLite 和项目文件落盘目录
  - `docs/`：当前有效的规格、计划和文档索引
- 参考资产
  - `archive/legacy-demo/`：旧的 Vite demo、PRD、HTML 原型、PDF 和归档包

## 当前状态

这次整理完成了三件事：

1. 把旧 demo 资产整体归档，不再占据主路径
2. 把当前有效文档整理到新的 `docs/` 结构
3. 新建一期主工程骨架，后续开发围绕 `frontend/` 和 `backend/` 展开

## 目录说明

```text
.
├── archive/
│   └── legacy-demo/
├── backend/
│   ├── app/
│   └── requirements.txt
├── data/
│   ├── projects/
│   └── sqlite/
├── docs/
│   ├── README.md
│   ├── planning/
│   └── product/
└── frontend/
    ├── package.json
    └── src/
```

## 文档入口

- 当前规格：[docs/product/fullstack-phase1-spec.md](/Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/docs/product/fullstack-phase1-spec.md)
- 当前执行清单：[docs/planning/fullstack-phase1-todo.md](/Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/docs/planning/fullstack-phase1-todo.md)
- 归档说明：[archive/legacy-demo/README.md](/Users/zhaofengli/projects/requirement_nyl/.worktrees/codex-fullstack-phase1-bootstrap/archive/legacy-demo/README.md)

## 开发方式

前后端分开启动。

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 说明

- `archive/legacy-demo/` 里的内容仍然保留，后续可以按需复用交互、文案和原型
- 新的一期实现不要再继续往归档目录里加主逻辑
