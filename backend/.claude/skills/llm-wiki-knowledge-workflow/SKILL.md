---
name: llm-wiki-knowledge-workflow
description: Use when maintaining project-local LLM Wiki knowledge pages for durable working understanding, source intake summaries, business rules, conflicts, decisions, and open questions. This skill never replaces NotebookLM grounding or citations.
---

# LLM Wiki Knowledge Workflow

## 定位

LLM Wiki 是项目内的“长期工作理解层”。

它负责沉淀：

- 项目背景和当前理解
- source intake 摘要索引
- 业务术语
- 规则和映射关系
- 冲突与待确认项
- 阶段性决策和版本线索

它不负责：

- 原文证据查询
- NotebookLM citation
- 判断某条信息是否最终 confirmed
- 替代项目状态桶

## 和 NotebookLM 的边界

NotebookLM / RAG 仍然是证据层。

涉及这些问题时，必须回到 NotebookLM grounding 或原始 source：

- 客户资料是否明确写过
- 哪份资料支持某条说法
- 两份资料对同一规则是否冲突
- 前端需要展示 citation

LLM Wiki 只能作为可修订的工作理解。不能把 Wiki 页面当成 NotebookLM citation，也不能在 NotebookLM 不可用时伪造 citation。

## 项目内目录

每个项目维护自己的 wiki：

```text
data/projects/<project_id>/wiki/
├── index.md
├── log.md
├── project-overview.md
├── source-intake.md
└── rules-and-conflicts.md
```

一期先保持小集合，避免每轮聊天都写大量页面。

## 更新时机

可以更新：

- 项目 wiki 初始化
- source 入库或 source 摘要发生变化
- 形成阶段性理解
- 生成 artifact 后形成版本线索

不要每轮普通追问都强制更新 wiki。

## 写入原则

- 只写项目内路径，不依赖用户家目录
- 记录 source_id 或原始 source 链接
- 发现冲突先标为冲突或待确认，不自动覆盖旧理解
- 语言简洁，面向后续 agent 读取，不写营销式说明
- 所有页面都应提醒：引用和 grounding 仍以 NotebookLM 为准

## 查询原则

聊天时可以把 Wiki 摘要作为连续记忆提供给主 agent。

主 agent 使用时必须遵守：

- Wiki 可帮助理解上下文
- Wiki 不可单独支撑 confirmed_items
- Wiki 不可生成前端 citation
- Wiki 和 NotebookLM grounding 冲突时，优先暴露冲突
