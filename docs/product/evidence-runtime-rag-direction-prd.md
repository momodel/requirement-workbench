# 证据层重构方向 PRD（开发方向稿）

## 1. 文档定位

这份文档用于定义下一阶段证据层重构的产品与架构方向。

它的定位是：

- 说明为什么当前证据层需要从 `NotebookLM` 路线切换
- 明确下一阶段的正式方向和分层边界
- 为后续执行方案文档提供统一上位约束

它不是：

- 逐文件实现清单
- 数据库迁移脚本说明
- 接口变更 checklist
- 已经落地完成的事实描述

这份文档当前只作为**开发方向稿**使用。  
在后续执行方案、正式 spec、todo、AGENTS 完成同步之前，仓库里原有一期文档仍然是当前主线基线。

## 2. 背景

当前项目为了先把主链路跑通，证据层直接接了 `NotebookLM` / `notebooklm-py`。

这条路线在“快速验证工作台形态”阶段是有效的，但在继续往正式化方向推进时，问题已经比较明确：

- query 响应速度波动大
- 稳定性一般，超时和远端状态异常会直接影响聊天主链路
- 项目级知识库依赖外部 notebook 绑定和远端同步状态
- readiness、source 同步、query 失败路径都被 NotebookLM 语义绑住
- 不利于后续服务化部署和项目内依赖收口

同时，当前项目的真实需求也已经更清楚：

- 工作台需要的是**项目级证据检索能力**
- 需要保留 citations
- 需要支持多模态 source
- 需要诚实暴露失败路径
- 需要把主回答权继续留在 `Claude Agent SDK`

这意味着，后续证据层不应继续沿着“外部知识聊天服务”路线扩展，而应切换到“项目内可控的 retrieval 层”路线。

## 3. 这次要解决的核心问题

下一阶段证据层重构，核心要解决的是下面五件事：

### 3.1 把证据层从“回答服务”改成“检索服务”

证据层负责：

- source 标准化后的索引
- 项目级知识库隔离
- 与问题相关的 chunk 检索
- grounding summary 和 citations 返回

证据层不再负责：

- 替代主智能体做最终回答
- 冒充完整分析器
- 维护外部 notebook 式的产品语义

### 3.2 把多模态支持收敛到可控路径

下一阶段多模态默认采用：

- **先把多模态 source 转成结构化文本**
- 再做文本向量检索

不把“原生多模态向量”当成第一阶段硬目标。

### 3.3 把项目级知识库能力正式收口到项目内

系统后续需要的是：

- 每个项目有自己的知识库隔离单元
- source 入库后进入项目级索引链路
- 不依赖远端 notebook 列表、手工 notebook 绑定、远端 notebook 状态

### 3.4 引入现成检索编排层，避免厚重自研

这次方向调整，不再把“项目内自管 Evidence Runtime”理解成：

- 自己从零实现整套 chunk / retrieve / summarize / citations 编排

而是改成：

- 用现成框架承接通用 retrieval orchestration
- 项目内只保留一层很薄的适配逻辑

### 3.5 保持工作台主链路稳定

这次重构不应把工作台推倒重来。

需要尽量保持稳定的部分：

- 三栏工作台形态
- 聊天主路由和 SSE 主节奏
- citations 在聊天中的展示语义
- 右栏状态沉淀主逻辑
- artifact 仍然由主智能体生成

## 4. 方向结论

### 4.1 正式方向

下一阶段证据层的默认方向调整为：

> `Docling + Qdrant + LlamaIndex + 项目内薄适配层 + 多模态先转文字`

对应的目标形态是：

- 解析层：`Docling`
- 向量库：`Qdrant`
- 检索编排层：`LlamaIndex`
- 项目内逻辑：薄适配层，仅负责项目语义、状态回写和接口对齐
- 多模态策略：text-first
- 主智能体：继续使用 `Claude Agent SDK`
- 最终回答生成：继续由 Claude 完成

### 4.2 为什么这样改写

原先文档里写的是：

> `Qdrant + 项目内自管 Evidence Runtime + 多模态先转文字`

这个表达在方向层没有错，但“项目内自管 Evidence Runtime”容易被误读成：

- 要在项目里自己写完整检索编排系统
- 要自己承担 chunk、召回、rerank、summary、citations 的大部分通用工程量

当前更合适的表达应是：

- 解析入口由 `Docling` 统一
- 向量库由 `Qdrant` 承担
- 检索编排优先借助 `LlamaIndex`
- 项目内只保留一层**薄适配层**

这层薄适配层的职责是：

- 把 `project_id` 映射到 collection / filter / namespace
- 把 source 的 parse / normalize / chunk / index 状态回写到项目自己的模型
- 把检索结果转换成当前前端和 SSE 已经使用的 citations / grounding 结构
- 把失败、超时、未初始化、未命中等状态接到 readiness 和 UI

也就是说，后续仍然有“项目内层”，但不再把它定义为一个厚重、自攒的 Evidence Runtime。

### 4.3 新的分层结构

后续推荐采用四层结构：

#### A. Source Ingestion

负责：

- 原始文件落盘
- 标准化结果产出
- chunk-ready 数据生成

#### B. Retrieval Orchestration

由 `LlamaIndex` 负责：

- chunk ingestion
- index write
- query orchestration
- metadata 保留
- citations 所需的结果组织

#### C. Retrieval Storage

由 `Qdrant` 负责：

- 项目级向量存储
- payload / metadata 过滤
- collection 级隔离
- 后续 hybrid / rerank 升级空间

#### D. Project Retrieval Adapter

项目内薄适配层负责：

- 项目知识库初始化
- source 索引和删除的项目级语义
- query(project_id, question) 的项目内接口对齐
- grounding summary / citations 结果转换
- readiness / 错误 / 状态回写

## 5. 解析层目标

解析层的目标方向定为：

> `Docling` 作为统一标准化入口

但执行顺序上，不要求 `Docling` 成为第一天的阻塞项。

也就是说：

- 方向上，后续标准化最终要统一收口到 `Docling`
- 实施上，可以先接 `Qdrant + LlamaIndex + 项目内薄适配层`
- 再逐步把现有 PDF / DOCX / XLSX / 图片 / 音频解析能力收敛到 `Docling`

## 6. 为什么不是其他路线

### 6.1 不是继续沿用 NotebookLM

因为当前痛点已经不是“能不能跑通”，而是“能不能稳定、可控、可部署”。

### 6.2 不是先做原生多模态向量

因为当前最缺的是稳定可靠的项目级知识库，不是高上限的多模态检索实验能力。

### 6.3 不是继续写厚重的项目内自管 retrieval runtime

因为当前项目已经明确知道自己需要的是：

- 项目级隔离
- citation 保留
- 失败路径可控
- 与现有聊天链路平滑对接

这些需求并不要求项目从零实现整套 retrieval orchestration。

如果继续沿着“项目内厚重自管 runtime”推进，会带来几个问题：

- 工程量偏大
- 通用检索能力重复造轮子
- 后续维护成本高
- 难以把精力集中在项目特有的 product semantics 上

因此，这次方向调整为：

- 通用检索编排尽量交给现成框架
- 项目内只保留薄适配层

### 6.4 为什么选 LlamaIndex，不是 Haystack

`Haystack` 是有效候选，但当前更适合优先评估 `LlamaIndex`。

原因主要是：

- 它和 `Qdrant` 的集成路径直接
- 它可以作为更轻的 orchestration layer 使用
- 更容易把当前项目需要的“项目内薄适配层”保留在应用层
- 更适合当前这种“要清晰分层，但不想上完整平台”的场景

这不意味着 `Haystack` 不可用，而是当前优先级下，`LlamaIndex` 更贴合：

- `Docling + Qdrant + 薄适配层`

这条组合的边界。

### 6.5 不是先上 R2R / 一体化黑盒平台

因为项目当前最需要的是把证据层抽象和产品语义收回来，而不是再次依赖另一个更黑、更完整的一体化后端。

R2R 这类平台的优势是：

- 接入快
- 自带 ingest / retrieval / citations / API

但当前阶段它的问题也很明确：

- 平台语义更重
- 项目自己的 product semantics 更容易被平台接口反向塑形
- 失败路径、状态语义和 readiness 很容易被平台默认模型带跑

当前项目更需要的是：

- 明确知道哪部分是通用框架能力
- 哪部分是项目自己的业务和产品语义

### 6.6 不是先走 pgvector

`pgvector` 是有效备选，但当前项目主存还是 `SQLite`。如果只为了证据层先把系统整体拉到 Postgres，改造面并不比独立引入 `Qdrant` 更小。

## 7. 产品影响

这次方向切换虽然首先是后端能力重构，但它会带来明确的产品层变化。

### 7.1 项目级知识库语义会变化

当前工作台里的产品语义还是：

- notebook binding
- notebook library
- notebook sync

后续应逐步改成更中性的知识库语义，例如：

- 项目知识库是否已初始化
- 当前 source 是否已完成索引
- 当前检索能力是否可用
- 当前 retrieval adapter 是否就绪

### 7.2 source 状态语义会变化

当前 source 状态主要围绕：

- parse
- sync to notebook

后续 source 状态应围绕：

- 标准化是否完成
- chunk 是否生成
- embedding 是否完成
- index 是否完成
- 索引失败原因是什么

### 7.3 聊天中的“证据”语义会更清晰

后续聊天中展示的 citations，应该来自项目自己的检索结果，而不是远端 notebook 返回。

这会让下面这些语义更清晰：

- 当前引用来自哪份 source
- 来自哪一页、哪一段、哪一个 sheet
- 没有证据时为什么没有
- 检索失败时是哪个环节失败

## 8. 范围边界

### 8.1 这次方向文档纳入的范围

- 证据层正式方向
- 多模态默认处理策略
- 现成编排层与项目内薄适配层的职责边界
- 项目级知识库的产品语义方向
- 证据层与主智能体的职责分工

### 8.2 这次方向文档不纳入的范围

- 具体采用哪一个 embedding 模型
- 具体 chunk 策略参数
- rerank 是否首版就上
- Qdrant collection schema 细节
- LlamaIndex 具体 index / retriever / query engine 组合
- 迁移步骤和数据库脚本
- 路由命名和字段改造顺序

这些内容留给后续执行方案文档。

## 9. 新的职责分工

后续系统的职责分工应明确成下面这样：

### 9.1 Source Ingestion

负责：

- 原始文件落盘
- 标准化结果产出
- chunk-ready 数据生成

### 9.2 Retrieval Orchestration

由 `LlamaIndex` 主承接，负责：

- 文档对象组织
- 向量写入编排
- query orchestration
- citation 所需 metadata 透传

### 9.3 Retrieval Storage

由 `Qdrant` 负责：

- collection / payload / vector storage
- 项目级隔离
- 检索和过滤能力

### 9.4 Project Retrieval Adapter

项目内薄适配层负责：

- 项目级 knowledge base 初始化
- source 索引、删除、重建的项目级语义
- `query(project_id, question)` 形式的项目内接口
- grounding summary / citations 的项目内返回结构
- readiness、错误、状态回写

### 9.5 Claude Agent Runtime

负责：

- 基于项目状态、聊天上下文、evidence summary、citations 做最终分析输出
- 继续负责结构化沉淀和 artifact 生成

## 10. 多模态策略

### 10.1 默认路线

默认采用 `text-first`：

- 文本、Markdown、DOCX、PDF：转文本
- XLSX：转结构化文本
- 图片：OCR + 可选图片描述
- 音频：先转写
- URL：抓正文并转文本

再统一走 chunk、embedding、retrieval。

### 10.2 后续增强路线

如果未来明确需要下面这些能力：

- 页面截图检索
- 图片相似检索
- 图文混合语义召回
- 视觉内容优先于 OCR 文本的场景

再补原生多模态向量。

当前不把这条增强路线定义为第一阶段硬目标。

## 11. 成功标准

当这条方向后续正式落地后，至少应达到这些结果：

### 11.1 运行层

- 不再依赖 NotebookLM notebook 绑定和远端 notebook 状态
- 证据层可在项目内稳定启动和使用
- source 索引失败时可以明确回写状态
- 通用 retrieval orchestration 不再由项目从零自研

### 11.2 体验层

- 聊天拿证据的首响应时间明显下降
- evidence query 的稳定性高于当前 NotebookLM 路线
- source 的状态和失败原因更清晰

### 11.3 诚实性

- 没有命中就明确说没有命中
- citations 必须来自真实检索结果
- 不允许伪造 grounding
- retrieval adapter 不可用时，主链路可以降级，但必须明确暴露

## 12. 与现有文档的关系

当前仓库里与这份方向稿直接相关的文档包括：

- `docs/personal/evidence-runtime-rag-options.md`
- `docs/personal/evidence-runtime-rag-options-extended.md`
- `docs/personal/evidence-runtime-rag-memvid-evaluation.md`
- `docs/product/fullstack-phase1-spec.md`
- `docs/planning/fullstack-phase1-todo.md`

这份方向稿基于前几份评估文档形成方向性结论，但当前还没有同步改掉一期正式 spec。

后续如果决定正式执行，应按下面顺序推进：

1. 先出执行方案文档
2. 再同步更新正式 spec / todo / AGENTS
3. 再开始实施代码和数据迁移

## 13. 当前结论

一句话总结：

> 当前项目证据层的最佳方向，不是继续依赖外部知识聊天服务，也不是继续写厚重的项目内 retrieval runtime，而是用 `Docling + Qdrant + LlamaIndex` 形成清晰的解析、存储和检索编排层，再用项目内薄适配层承接项目语义、状态回写和接口对齐，并把最终分析权继续留给 `Claude Agent SDK`。

这份文档之后，下一份文档应是：

> 证据层重构执行方案文档

它负责把这里的方向结论展开为具体实施路径、阶段切分、接口变更和验收方式。
