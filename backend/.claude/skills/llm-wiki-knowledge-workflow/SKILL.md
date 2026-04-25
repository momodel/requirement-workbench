---
name: llm-wiki-knowledge-workflow
description: Use when maintaining or consulting the project-local LLM Wiki synthesis layer. The Wiki is for cross-source working understanding, term glossaries, business rules, conflicts, decisions, open questions. It is NOT the evidence layer; citations and grounding still go through 项目知识库 RAG (rag-evidence-workflow).
---

# LLM Wiki Knowledge Workflow

## Overview

LLM Wiki 是项目内的**综合 / 工作理解层**，由 LLM 自己维护。

它的定位是：

- 让跨多份资料的合成结果（实体画像、术语、规则、冲突、阶段决策、待办问题）能落地为持久化 markdown
- 让每轮聊天不必从零重新合成
- 让后续 agent 一进来就能从 wiki 读到当前项目的可读 working understanding

它不是：

- 证据层（chunk 级 grounding 仍然走 RAG，见 `rag-evidence-workflow`）
- citation 来源（`confirmed_items` 与 artifact 的 citation 必须来自 `query_project_evidence` 的真实返回）
- 项目状态桶（state buckets 仍然在 `project_state` 服务里）
- 可以自动接管"决策"或"裁决"的层

## Wiki 与 RAG 的边界

|  | Wiki | RAG (`rag-evidence-workflow`) |
| --- | --- | --- |
| 内容 | LLM 维护的 markdown 页面，跨源合成 | 原文 chunk + 向量索引 |
| 颗粒度 | 页面 / 段落 | chunk |
| 可变性 | 可修订、可跨页改写 | 与原文绑定，源更新才变 |
| 可作为 citation 吗 | 不可 | 可（前端 source_refs 唯一来源） |
| 主要回答的问题 | "我们对项目当前怎么理解？" | "原文里到底怎么说？" |
| 失败回退 | 已有页面降级只读 | 走错误路径，不伪造 |

涉及这些问题时，**必须**走 RAG，不许只看 wiki：

- 客户资料是否明确写过某条规则
- 哪份 source 支撑某条断言
- 两份资料对同一规则是否冲突
- 前端要展示的 citation
- artifact 里要标注的引用

涉及这些问题时，**优先**读 wiki：

- "这个项目当前在做什么场景？"
- "我们之前对 XX 实体怎么定义？"
- "目前已经识别出来的待确认问题有哪些？"
- "上次阶段性结论是什么？"

## 页面种类（kind）

phase 1 固定骨架（每个项目初始化时创建）：

- `overview` — 项目背景与当前工作理解（slug: `overview`）
- `source-intake` — 已接入资料的合成索引（slug: `source-intake`）
- `glossary` — 业务术语（slug: `glossary`）
- `rules-and-conflicts` — 业务规则与冲突（slug: `rules-and-conflicts`）
- `open-questions` — 待确认问题（slug: `open-questions`）

LLM 维护时 **可以** 新建页面，类型限于：

- `entity` — 单个实体的画像页（slug: `entity-<short-slug>`）
- `term` — 单个术语的展开页（slug: `term-<short-slug>`）
- `rule` — 单条业务规则的展开页（slug: `rule-<short-slug>`）
- `conflict` — 单条冲突的展开页（slug: `conflict-<short-slug>`）
- `open_question` — 单条待确认问题的展开页（slug: `open-question-<short-slug>`）

slug 规则：小写 ASCII + 连字符；entity/term/rule/conflict/open_question 必须带前缀；不允许中文 slug。

每个页面必须带前置块（front-matter, JSON 格式）：

```
---
{
  "title": "<人读标题>",
  "kind": "<上面之一>",
  "source_ids": ["<source_id>", ...],
  "last_maintained_at": "<iso8601 或 null>",
  "last_maintained_by": "subagent | manual | skeleton"
}
---

<markdown 正文>
```

`source_ids` 必须填实际存在于本项目的 source 列表里的 ID。骨架页可以是空数组。entity/term/rule/conflict/open_question 类页面**至少** 1 条 source_id。

## Citation 强制

**写入侧：** 每段断言性的内容必须能追到 `source_ids`。维护者 LLM 在写新内容时，正文里可以写「[src: <source_id>]」内联引用，但更重要的是 front-matter 里 `source_ids` 字段必须保持完整。

**读取侧：** 任何使用 wiki 内容形成对外回答的 agent，**不得**把 wiki 的段落当作 citation 直接给前端。需要 citation 就调 `query_project_evidence`。

`update_project_state` 写 `confirmed_items` 时，`source_ids` 字段必须命中真实的 catalog source；wiki 的 slug 不通过此校验。

## 何时维护

维护者（host 后台 subagent）触发时机：

- 项目初始化（创建骨架页，`last_maintained_by="skeleton"`）
- source 入库成功后（fire-and-forget，不阻塞上传 HTTP）
- version checkpoint 形成后（fire-and-forget）
- 管理触发 `POST /wiki/maintain`（手动）

不要在每轮普通聊天里主动写 wiki。

## 维护原则

- **追加 / 改写，不全量重写。** 维护者用 Read 读现有页面，用 Edit 做局部修改，用 Write 只在新增页面或骨架页第一次被改时使用。
- **冲突先标，不直接覆盖。** 新源与旧理解冲突时，写到 `rules-and-conflicts.md` 或新建 `conflict-<slug>` 页面，而不是把 overview 改掉。
- **保守新建页面。** 默认扩展骨架页；只有当某实体 / 术语 / 规则 / 冲突 / 问题已经在 source 里被多次提到，且骨架页篇幅放不下时，才新建展开页。
- **log.md 追加不改写。** 每次维护成功后追加一段：`## [<iso8601>] <operation>` + 触发原因 + 改了哪些页面 + 涉及的 source_id 列表。`log.md` 的历史记录不允许 Edit。
- **不要伪造 source_id。** 维护提示词会显式给出当前项目的 source_id 列表；只能从这个列表里挑。

## 失败处理

维护者失败不能反向影响 RAG 索引。

正确处理：

- RAG 索引成功就是成功
- wiki 维护失败在 source 行的 `wiki_sync_status` 上记 `failed` + 原因
- 已有 wiki 页面仍然可读
- 下一次维护触发会覆盖修复

`get_global_readiness` 在以下情况返回非 `ready`：

- `data/projects/` 不可写 → `error`
- Claude SDK 未配置 → `degraded_readonly`（已有页面只读，新维护跳过）
- 首次维护 health probe 失败 → `error`

## 和实现的关系

这个 skill 应该影响：

- `WikiRuntime` Protocol 与 `ClaudeWikiRuntime` 的行为
- `WikiMaintainer` 子 agent 的 prompt 构造
- 入库 / 版本快照后的 fire-and-forget 触发逻辑
- 聊天 agent 的 `wiki_read_page` / `wiki_list_pages` 工具说明
- `update_project_state` 工具的 source_id 校验

它不应该被写成「只要引用了 skill，就算真的接入了 LLM Wiki」的借口。Wiki 是不是真由 LLM 维护，看的是 wiki 文件的写入路径有没有真实跑过 `claude_agent_sdk.query`。
