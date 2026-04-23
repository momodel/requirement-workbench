---
name: notebooklm-evidence-workflow
description: Use when migrating notebook-era evidence semantics, source normalization rules, and citation boundaries under this repo's Docling + Qdrant + LlamaIndex + EvidenceRuntime architecture.
---

# NotebookLM Evidence Workflow

## Overview

这个 skill 说明的是，本项目里和 NotebookLM 相关的资料处理边界，以及它在当前 evidence runtime 架构下还能承担什么窄角色。

它的定位是：

- 约束 source 标准化边界
- 约束历史 NotebookLM 资料/流程在迁移后的兼容处理
- 约束什么时候可以把 NotebookLM 结果当成补充证据参考
- 约束如何把 grounded summary / citations 诚实回写给项目运行时

它不是：

- 一期正式证据主链路说明
- 本地 mock 摘要服务的包装说明
- 项目状态判断器
- 可以脱离真实 provider 路径单独成立的伪流程

## 一期选定路线

本项目一期当前确认的正式证据路线是：

- `Docling` 负责标准化 / 文本抽取
- `Qdrant` 负责向量存储
- `LlamaIndex` 负责检索编排
- 项目自己的 `EvidenceRuntime` 负责查询与回写

NotebookLM 在当前一期里不是正式主 provider，也不是必须打通的主链路。

这个 skill 当前只描述两类事情：

- 历史 notebook-era source / 文案 / 兼容字段如何被诚实迁移
- 如果未来存在真实 NotebookLM 辅助实验或补充引用，应如何标清边界，而不是伪装成一期主运行时

## 什么时候用

这些场景用它：

- 判断一个 source 在 evidence runtime 下该直接进入标准化 / 分块 / 索引，还是需要额外整理
- 设计标准化文本或 Markdown 输出
- 判断哪些历史 NotebookLM 语义需要改写成 knowledge base / indexing 语义
- 设计 grounded summary / citations 的诚实返回方式
- 处理历史 NotebookLM 导入失败、查询失败或迁移失败的回写

这些事情不要交给这个 skill：

- 最终 scope 判断
- `confirmed_items` 的最终裁决
- 冲突是否可接受
- MVP 是否应该纳入

这些仍然属于项目分析层、主 agent 和 evidence runtime 主链路。

## Source 分类原则

先判断 source 属于哪一类，再决定是否需要标准化。

一期按下面的边界处理：

### 可直接进入 evidence runtime 标准化 / 索引路径

- 文本粘贴
- PDF
- DOCX
- Markdown / Text
- 图片
- 音频
- Web URL
- YouTube URL

### 先标准化，再进入 evidence runtime

- XLSX
- 飞书纪要原始文本以外的结构化导出内容
- 任何主要价值在表格、表头、列含义、元数据，而不是自然语言正文里的 source

## 标准化原则

标准化不是随便摘几句摘要，而是要把“后续可被引用的关键信息”整理出来。

一期至少要保留：

- 原始文件记录
- 标准化结果文件
- parse summary
- 解析状态
- index 状态

XLSX 至少抽出这些内容：

- sheet 名
- 表头
- 样例行
- 行列统计
- 关键字段含义提示

飞书纪要一期只支持：

- 直接粘贴文本
- 上传导出的 PDF / DOCX / Markdown / Text

不做飞书 OAuth 或在线连接。

## Query 原则

当前一期真正负责“基于 source 回答证据问题”的是项目 evidence runtime。

如果将来接入真实 NotebookLM 辅助实验，它也只能承担补充参考角色，不能覆盖主链路状态判断。

适合的 query：

- 某个规则在资料里是怎么描述的
- 两份资料对同一问题是否说法一致
- 哪些 source 提到了同一个映射关系
- 某条当前理解能不能找到 source 支撑

不适合的 query：

- 这个项目最终要不要做某能力
- 哪条信息应该算 confirmed
- MVP 怎么切

## 引用原则

如果要给前端 citations，就必须来自真实 provider 结果，并且要说明来源属于哪一层。

一期默认主来源是 evidence runtime 的 retrieval / chunk 命中，不是假装来自 NotebookLM。

只有在真实 NotebookLM 辅助链路确实存在时，才能把结果标为 NotebookLM citations。

不要做这些事：

- 本地拼一个 citation 数组
- 把 parse summary 的来源当成 NotebookLM citation
- 在 NotebookLM 不可用时继续伪造引用

做不到就明确返回：

- 当前无 grounding
- 当前无 citations
- 当前 query 失败

## 失败处理

历史 NotebookLM 路径失败，不能把 evidence runtime 主链路一起拖死。

正确处理方式：

- 原始 source 先入库
- 标准化尽量完成
- evidence runtime 的索引状态独立记录
- 如存在 NotebookLM 辅助实验，则它单独失败、单独暴露
- 在 source 状态里标清失败原因
- 查询失败时让 chat 明确知道“证据层暂不可用”

系统可以降级继续分析，但必须诚实说明哪一层不可用，不能把旧 notebook 语义包装成当前正式能力。

## 和外部 notebooklm-skill 的关系

[PleasePrompto/notebooklm-skill](https://github.com/PleasePrompto/notebooklm-skill) 在本项目里的作用是：

- 参考 NotebookLM 的操作习惯
- 参考 prompt 写法
- 参考 CLI 工作流

它不是：

- 本项目唯一的 skill
- 本项目运行时
- 本项目项目状态的来源

项目真正要落地的是：

- 项目自己的 `notebooklm-evidence-workflow` skill
- 项目自己的 source 标准化 / indexing 规则
- 项目自己的 `EvidenceRuntime`
- 项目自己的 knowledge base / retrieval / citation 回写

## 和实现的关系

这个 skill 应该影响：

- source ingestion 的标准化规则
- notebook-era 文案和兼容字段的迁移策略
- evidence query 的提问方式
- citations 返回格式
- 错误回写方式

它不应该被写成：

- “NotebookLM CLI 是一期正式路线”
- “项目已经接入了 NotebookLMService”
- “只要引用了这个 skill，就算真实接入 NotebookLM”
