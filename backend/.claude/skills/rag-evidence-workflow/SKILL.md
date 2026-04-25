---
name: rag-evidence-workflow
description: Use when working on source ingestion, source normalization, 项目知识库 RAG 索引, grounded summaries, or citations in this repo, especially when deciding what can go into 项目知识库 RAG directly and what must be converted first.
---

# 项目知识库 RAG Evidence Workflow

## Overview

这个 skill 说明的是，本项目里资料理解层应该怎么接入 项目知识库 RAG。

它的定位是：

- 约束 source 标准化边界
- 约束什么时候该查 项目知识库 RAG
- 约束如何把 grounding 和 citations 回给运行时

它不是：

- 本地 mock 摘要服务的包装说明
- 项目状态判断器
- 可以脱离真实 项目知识库 RAG 路径单独成立的伪流程

## 一期选定路线

本项目一期对 项目知识库 RAG 的正式路线是：

- 真实 `Docling + Qdrant + LlamaIndex + EvidenceRuntime`
- Docling 或现有解析器负责 source 标准化
- Qdrant/LlamaIndex 负责 chunk 索引和检索
- EvidenceRuntime 承接运行时调用，不依赖外部笔记本服务

## 什么时候用

这些场景用它：

- 判断一个 source 能不能直接进入 RAG 索引
- 设计标准化文本或 Markdown 输出
- 设计项目知识库检索 query
- 需要 grounded summary
- 需要 citations
- 需要处理 RAG 索引失败或查询失败

这些事情不要交给 项目知识库 RAG：

- 最终 scope 判断
- `confirmed_items` 的最终裁决
- 冲突是否可接受
- MVP 是否应该纳入

这些仍然属于项目分析层和主 agent。

## Source 分类原则

先判断 source 属于哪一类，再决定是否需要标准化。

一期按下面的边界处理：

### 可直接进入正式 RAG 路径

- 文本粘贴
- PDF
- DOCX
- Markdown / Text
- 图片
- 音频
- Web URL
- YouTube URL

### 先标准化，再进入 RAG

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
- 索引状态

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

项目知识库 RAG 只负责“基于 source 回答证据问题”。

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

如果要给前端 citations，就必须来自真实 项目知识库 RAG 结果。

不要做这些事：

- 本地拼一个 citation 数组
- 把 parse summary 的来源当成 RAG citation
- 在 项目知识库 RAG 不可用时继续伪造引用

做不到就明确返回：

- 当前无 grounding
- 当前无 citations
- 当前 query 失败

## 失败处理

项目知识库 RAG 失败不能把 source 入库一起拖死。

正确处理方式：

- 原始 source 先入库
- 标准化尽量完成
- RAG 索引独立失败
- 在 source 状态里标清失败原因
- 查询失败时让 chat 明确知道“证据层暂不可用”

系统可以降级继续分析，但必须诚实说明证据能力当前不可用。

## 和旧外部笔记本方案的关系

旧外部笔记本方案只作为历史参考，不再是一线查询工具。

项目真正要落地的是：

- 项目自己的 `rag-evidence-workflow` skill
- 项目自己的 `QdrantLlamaIndexEvidenceRuntime`
- 项目自己的 source chunk 与 citation 数据

## 和实现的关系

这个 skill 应该影响：

- source ingestion 的标准化规则
- RAG 索引策略
- grounding query 的提问方式
- citations 返回格式
- 错误回写方式

它不应该被写成一个“只要引用了 skill，就算真实接入 RAG provider”的借口。
