# 音频线上 ASR 与七牛存储接入 PRD（目标态 / 当前现状对齐版）

## 1. 文档定位

这份文档定义的是：

- 音频 source 接入正式 `text-first RAG` 主链路的目标方案
- 当前分支真实代码现状下，音频链路已经具备什么、还缺什么
- 后续实现、联调和验收的统一口径

这份文档明确区分两类内容：

- `当前现状`：当前代码已经真实具备的能力
- `目标方案`：本专题要落地的正式能力

它不是：

- 把未实现的 provider 写成“已接入”
- 全项目总 spec 的替代品
- 逐文件开发清单
- 本地假转写或临时 fallback 的背书文档

如果未来实现与当前代码冲突，以这份文档定义的 `目标方案` 为准；但在目标能力真正落地前，UI、接口、文档都必须诚实暴露“尚未接通”的事实。

## 2. 设计目标

本专题的设计目标保持不变：

1. 用户上传音频文件
2. 后端保存原始音频
3. 后端把音频上传到七牛对象存储
4. 阿里云 ASR 完成异步转写
5. 转写结果写入 `normalized.md`
6. 现有 `EvidenceRuntime` 基于 `normalized.md` 完成 `chunk -> embed -> index`
7. 工作台与聊天检索基于真实转写文本展示状态、预览和 citations

目标不是：

- 做原生音频向量检索
- 用本地摘要伪装成转写正文
- 让前端绕开现有 source 上传主链路直接传对象存储
- 用多层 fallback 把失败包装成“基本可用”

## 3. 当前代码现状

### 3.1 已有能力

当前分支已经具备这些基础能力：

- source 上传接口已经存在，文件会落到项目内 `sources/` 目录
- `SourceIngestionService` 会基于文件后缀识别 `source_kind=audio`
- `normalized.md` 一旦存在，现有 `EvidenceRuntime` 已经可以把音频 source 当作文本 source 继续索引和检索
- source 内容预览接口已经支持：
  - 读取 `normalized_path` 返回全文
  - 读取原始文本资料返回全文
  - 在没有全文时返回 `normalize_summary`
- 当前工作台已经能展示 source 类型、标准化状态、索引状态、摘要和预览

这意味着：

- 现有 RAG 主链路本身不需要为了音频重做
- 真正的缺口不在检索层，而在“音频如何诚实地产出 `normalized.md`”

### 3.2 当前音频处理的真实行为

截至当前分支，音频 source 的真实行为是：

- `DoclingNormalizer` 把音频后缀也纳入 `SUPPORTED_SUFFIXES`
- `SourceIngestionService.ingest_file()` 会像处理图片 / PDF 一样，直接同步调用 `docling_normalizer.normalize_to_markdown()`
- 如果没有可用的 Docling / ASR 运行时，或转换失败，音频 source 会直接进入 `normalize_status=failed`
- 当前代码里没有音频专属异步处理链路，也没有 `processing` 这一套音频转写中的正式状态推进

换句话说，当前分支并不存在“后端代传七牛 + 阿里云异步转写”的正式主链路。

### 3.3 当前缺口

当前分支尚未具备这些能力：

- 项目内 `Qiniu` 对象存储接入
- 项目内 `Aliyun ASR` 接入
- `ObjectStorageService`
- `AudioTranscriptionService`
- `AudioIngestionOrchestrator`
- `source_processing_jobs` 之类的轻量任务记录
- 音频链路专属 readiness 信息
- 音频 source 的异步 `processing` 状态
- 音频失败后重新触发转写的 `reindex` 语义
- 前端针对音频“转写中 / 转写失败 / 已转写待入库”的专属语义

### 3.4 已验证的兼容前提

当前测试已经证明一件重要事实：

- 只要音频 source 有真实 `normalized.md`
- 现有 `EvidenceRuntime` 就可以继续索引它
- 音频 citations 也可以沿用当前 source-level / chunk-level 的文本检索语义

因此，音频正式接入的正确方向是：

- 补齐“音频 -> 标准化文本”这段链路
- 而不是推翻现有 RAG 主链路

## 4. 问题定义

当前分支的问题不是“完全不能存音频文件”，而是：

- 音频还没有正式、稳定、诚实的线上转写链路
- 当前代码把音频也塞进了同步 Docling 标准化语义里，但这不是本专题要的正式方案
- readiness、失败态、前端状态语义都还没有对齐音频正式链路

所以，本专题真正要解决的是：

> 如何在不改动现有 `text-first RAG` 主链路边界的前提下，为音频 source 增加一条项目内、可配置、可失败、可重试、可验收的标准化文本生产路径。

## 5. 范围边界

### 5.1 本期纳入范围

- 线上 ASR provider：`阿里云`
- 对象存储 provider：`七牛云`
- 上传模式：`后端代传`
- 执行模式：`异步转写`
- 结果形态：`normalized.md`
- RAG 接入方式：复用现有 `EvidenceRuntime`
- 展示方式：音频 source 保持音频标记，但预览和检索都基于转写文本

### 5.2 本期明确不做

- 本地 ASR
- 前端直传七牛
- 阿里云 OSS
- 其他对象存储 provider
- 原生音频 embedding / 音频向量检索
- 通用任务平台
- 多 provider 自动 fallback

## 6. 设计原则

### 6.1 诚实原则

- 未配置就报 `not_configured`
- provider 失败就报失败
- 不把上传成功包装成“转写成功”
- 不把摘要、meta、伪正文包装成正式 transcript

### 6.2 边界原则

- 七牛只负责把本地音频变成阿里云可读取的对象地址
- 阿里云只负责把音频转换成文本
- `EvidenceRuntime` 继续只负责文本索引与查询
- 宿主只负责串联流程、状态回写、错误处理，不在宿主内部模拟“需求分析式 if/else”

### 6.3 项目内依赖原则

- 依赖、脚本、配置、数据目录优先收口到项目内
- 不把用户机器上的个人环境、登录态、家目录配置写成项目能力
- 任何必须人工完成的认证步骤都要明确暴露

## 7. 目标方案

### 7.1 总体方案

目标方案固定为：

> 用户上传音频后，后端先把原始音频写入项目内 `sources/` 目录，再通过项目内 `ObjectStorageService` 上传到七牛；随后由项目内 `AudioTranscriptionService` 调用阿里云 ASR 完成异步转写；转写结果落盘为 `normalized.md` 后，再进入现有 `EvidenceRuntime` 的索引与检索主链路。

### 7.2 目标分层

#### A. Source Ingestion

职责：

- 接收音频上传
- 写入原始文件
- 创建 source 记录
- 触发音频异步处理

不负责：

- 对象存储上传
- 转写轮询
- 索引实现

#### B. Object Storage Adapter

目标新增：`ObjectStorageService`

职责：

- 校验七牛配置
- 生成稳定 object key
- 上传本地音频文件
- 返回阿里云可访问的 URL

#### C. Audio Transcription Adapter

目标新增：`AudioTranscriptionService`

职责：

- 校验阿里云配置
- 提交转写任务
- 查询 / 轮询转写结果
- 生成 transcript markdown

#### D. Audio Workflow Layer

目标新增：`AudioIngestionOrchestrator`

职责：

- 串联“上传七牛 -> 提交转写 -> 获取结果 -> 写 `normalized.md` -> 回写状态 -> 触发索引”
- 管理失败文案和重试
- 记录 provider job 信息

#### E. Existing Evidence Runtime

保持不变：

- 读取 `normalized.md`
- chunk
- embed
- index
- query
- citations

### 7.3 正式主链路

目标主链路如下：

1. 用户上传 `mp3 / wav / m4a / aac / flac / ogg`
2. 后端把原始音频写入项目内 `sources/`
3. source 记录创建为 `source_kind=audio`
4. source 先进入 `normalize_status=processing`
5. 后端异步任务调用 `ObjectStorageService`
6. 上传成功后调用 `AudioTranscriptionService`
7. 转写完成后生成 `*.normalized.md`
8. source 更新为 `normalize_status=parsed`
9. 触发现有 `EvidenceRuntime.index_source()`
10. 索引成功后 source 更新为 `index_status=indexed`
11. 工作台可预览转写全文
12. 聊天检索可以命中音频转写文本

### 7.4 为什么必须异步

- 阿里云长音频转写不适合同步塞进上传请求
- 音频文件大小、时长、provider 时延都不稳定
- 上传接口需要尽快返回 source 记录和真实状态
- 当前系统已经有 source 生命周期和索引状态语义，异步更自然

## 8. 状态模型

### 8.1 当前分支真实状态基线

截至当前分支，音频 source 的真实状态更接近：

- 成功时：`normalize_status=parsed`
  - 前提是同步标准化链路偶然拿到了文本
- 失败时：`normalize_status=failed`
  - 常见于当前环境没有可用的音频转文本运行时

当前并没有正式的：

- `normalize_status=processing`
- 音频 provider job 状态
- 音频转写中的前端轮询语义

### 8.2 目标状态口径

目标方案中，音频 source 的状态应与当前中性字段兼容，但语义要明确：

- `normalize_status`
  - `processing`：音频已入库，异步转写进行中
  - `parsed`：`normalized.md` 已生成
  - `failed`：音频标准化链路失败

- `index_status`
  - `normalization_pending`：还在等转写结果，暂不可索引
  - `pending` / `indexing` / `indexed`：沿用现有索引状态推进
  - `knowledge_base_missing` / `not_configured` / `error`：沿用现有 evidence readiness 语义
  - `index_failed`：转写成功了，但索引失败

### 8.3 关键状态解释

#### `normalize_status=processing`

表示：

- 原始音频已经落盘
- 正式转写链路已经启动
- 当前还没有可索引正文

#### `normalize_status=parsed`

表示：

- `normalized.md` 已经生成
- 音频已退化为文本 source
- 但索引不一定已经成功

#### `normalize_status=failed`

表示：

- 七牛未配置或上传失败
- 阿里云未配置、提交失败、查询失败或超时
- 转写结果为空
- `normalized.md` 落盘失败

此时不得继续伪装成 `parsed` 或 `indexed`。

## 9. API 语义

### 9.1 上传接口

继续复用现有 source 上传接口。

目标行为：

- 上传音频后立即返回 source 记录
- 不等待阿里云转写完成
- 初始返回：
  - `source_kind=audio`
  - `normalize_status=processing`
  - `index_status=normalization_pending`

### 9.2 source content 接口

目标行为：

- 有 `normalized.md`：返回 `full_text`
- 没有全文但有摘要：返回 `summary_only`
- 完全不可展示：返回 `unavailable`

这与当前接口形态兼容，不需要重做 content API。

### 9.3 reindex 接口

目标行为：

- 如果已经有 `normalized.md`：沿用现有 evidence reindex
- 如果没有 `normalized.md` 且音频转写失败：重新触发音频标准化流程
- 如果仍在 `processing`：返回当前处理中状态，不伪造索引已重建

### 9.4 readiness 接口

当前真实现状：

- 只返回 `claude` 和 `evidence`

目标行为：

- 在现有结构上扩展：
  - `object_storage`
  - `audio_transcription`
- 返回它们各自的 `provider / status / summary / detail / action_label`

未落地前，不应在接口文档、前端文案里写成“readiness 已支持七牛和阿里云”。

## 10. 前端语义

### 10.1 当前前端基线

当前工作台已经能展示：

- source 类型 badge
- 通用标准化状态
- 通用索引状态
- source 摘要和全文预览
- 运行状态弹层中的 `Claude Agent SDK` 和 `项目知识库`

但当前还没有：

- 音频专属 `processing` 语义
- 七牛 / 阿里云 readiness 卡片
- 音频转写中的轮询刷新

### 10.2 目标前端语义

目标行为：

- 音频 source 保留音频类型标记
- 处理中显示“音频已上传，正在转写，完成后自动进入项目知识库”
- 成功后显示标准化摘要和完整 transcript
- 失败后显示明确失败原因和可重试动作
- 运行状态弹层新增七牛 / 阿里云 provider readiness

### 10.3 文案约束

禁止出现：

- “已接入正式 provider”但实际未配置
- “已可检索”但实际尚未生成 `normalized.md`
- “转写成功”但实际只是文件已上传

## 11. 配置与依赖边界

### 11.1 当前依赖现状

当前项目内已经有：

- `docling`
- `qdrant-client`
- `llama-index-*`
- `fastembed`

当前项目内还没有：

- 七牛 SDK
- 阿里云 ASR SDK
- 音频 provider 配置字段

### 11.2 目标配置要求

目标方案至少需要：

- 七牛 `AccessKey`
- 七牛 `SecretKey`
- 七牛 `Bucket`
- 七牛 `Domain`
- 阿里云 `AccessKeyId`
- 阿里云 `AccessKeySecret`
- 阿里云 `AppKey`

约束：

- 不默认依赖用户家目录里的配置
- 不把本机手工登录状态当项目能力
- 缺配置时 readiness 和实际运行都必须提前报 `not_configured`

## 12. 从现状到目标的关键差距

要把当前分支推进到目标态，至少还需要补齐这些能力面：

- 配置层：
  - 新增七牛 / 阿里云配置项
  - 新增项目内依赖

- 服务层：
  - 新增 `ObjectStorageService`
  - 新增 `AudioTranscriptionService`
  - 新增 `AudioIngestionOrchestrator`

- 持久化层：
  - 新增轻量任务记录，例如 `source_processing_jobs`

- 路由层：
  - 上传接口接入异步音频流程
  - `reindex` 增加“重触发音频转写”语义
  - readiness 接口扩展音频 provider 状态

- 前端层：
  - 支持音频 `processing` 状态
  - 支持 provider readiness 展示
  - 支持转写中轮询刷新

- 验证层：
  - 覆盖成功、失败、重试、回归测试
  - 明确验证聊天 citations 来自真实 retrieval hit

## 13. 失败路径

### 13.1 目标方案下的失败路径

- 七牛未配置：
  - 音频 source 失败
  - 明确提示对象存储未配置
  - 不继续调用阿里云

- 七牛上传失败：
  - 音频 source 失败
  - 保留本地原始音频
  - 不伪装成处理中

- 阿里云未配置：
  - 音频 source 失败
  - 明确提示 ASR 未配置

- 阿里云提交失败 / 查询失败 / 超时：
  - 音频 source 失败
  - 保留 provider 错误明细
  - 允许后续重试

- 转写为空：
  - 视为失败
  - 不允许进入 `parsed`

- 索引失败：
  - `normalize_status=parsed`
  - `index_status=index_failed`
  - 全文仍可预览
  - 允许单独 reindex

### 13.2 目标落地前的诚实要求

在目标能力真正落地前：

- 当前音频路径如果失败，就继续如实返回当前实现产生的失败信息
- 不允许在 UI 或文档里把现状包装成“只是缺最后一层 UI”
- 不允许把当前同步 Docling 音频尝试写成“正式线上 ASR 已接通”

## 14. 验收标准

### 14.1 实现完成后的主链路验收

- 上传音频后，接口立即返回 source 记录
- source 真实进入 `normalize_status=processing`
- 转写成功后生成 `normalized.md`
- 现有 `EvidenceRuntime` 能索引该音频 source
- 聊天检索可以命中音频转写内容

### 14.2 UI 验收

- 音频 source 保持音频样式标记
- 成功后可查看完整 transcript
- 处理中和失败态可明确区分
- 运行状态面板可展示七牛 / 阿里云 readiness

### 14.3 诚实性验收

- 未配置时明确报未配置
- provider 失败时明确报失败
- 不伪造转写成功
- 不伪造 grounding / citations

### 14.4 回归验收

- 不破坏文本、PDF、图片、DOCX、XLSX、URL 的既有主链路
- 不改变现有 `EvidenceRuntime` 的职责边界
- 不让音频链路把系统重新拖回同步重处理模型

## 15. 当前结论

一句话总结：

> 当前分支已经具备“音频一旦有真实 `normalized.md` 就能进入现有 RAG 主链路”的基础，但还没有“七牛对象存储 + 阿里云异步转写”的正式音频标准化能力；后续实现应补齐这段链路，而不是重做 `EvidenceRuntime`。

后续所有实现、联调、UI 和 readiness 设计，都应围绕这条结论展开。
