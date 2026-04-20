---
name: requirement-analysis-methodology
description: Use when analyzing customer requirements, project materials, chat history, or project state for this repo, especially when deciding what belongs in current understanding, pending items, confirmed items, conflicts, MVP, versions, or artifacts.
---

# Requirement Analysis Methodology

## Overview

这个 skill 是本项目里“需求怎么被分析和沉淀”的方法参考。

它的作用是：

- 给主智能体 prompt 提供分析骨架
- 给开发者提供状态分类和追问方式参考
- 让聊天、状态沉淀、artifact 触发保持同一套分析逻辑

它不是运行时代码模板，也不要求后端 handler 和数据库结构逐步照着它展开。

## 什么时候用

在这些场景用它：

- 读取用户原始诉求，判断问题到底是什么
- 读取 source、访谈摘录、聊天记录，提炼当前理解
- 判断一条信息属于 `current_understanding`、`pending_items`、`confirmed_items` 还是 `conflict_items`
- 规划当前轮应该追问什么
- 判断何时可以形成 MVP 方向
- 判断何时值得生成版本快照或 artifact

不要把它当成：

- UI 文案模板
- 数据库 schema 文档
- “系统必须逐步执行的固定五阶段脚本”

## 核心工作方式

每轮分析优先做这几件事：

1. 读当前项目上下文
2. 区分“用户怎么说”和“系统真正需要理解什么”
3. 把已知、待确认、冲突、边界拆开
4. 只问当前轮最值钱的问题
5. 优先产出结构化状态，而不是长篇总结

更具体地说，一轮好的分析通常会覆盖这些维度：

- 业务目标
- 核心对象
- 关键角色
- 流程和系统边界
- 规则和映射关系
- 风险和异常
- 范围和优先级

## 状态分类

### current_understanding

当前最可信的工作理解，可以还没完全确认，但已经足够指导下一轮追问或方案判断。

### pending_items

还没定下来，而且会影响范围、规则、责任边界、验收口径的事情。

### confirmed_items

已经被用户明确确认，或者有足够可靠证据支持的事实和决策。

### conflict_items

来源之间互相打架、术语不一致、口径不一致、版本冲突、映射不唯一，都应该进这里。

### mvp_items

在边界、风险和价值权衡之后，仍然保留下来的首期能力。

## 追问策略

追问要少，但要准。

优先问这几类问题：

- 哪个业务对象才是真正的分析锚点
- 哪个系统才是口径上的 source of truth
- 哪些异常必须先纳入首期
- 哪些事情可以自动化，哪些必须保留人工确认
- 什么是“一期可交付”，什么只是未来方向

不要问这些低价值问题：

- 只是把资料换种说法重复一遍
- 对当前判断没有影响的背景闲聊
- 能从已有 source 里直接读出来的东西

## 真实需求与 MVP 判断

这个 skill 不鼓励一上来就跳到“做什么页面”。

顺序应该是：

1. 先确认问题是不是被说准了
2. 再确认范围和边界
3. 再确认哪些冲突暂时无法解
4. 最后才收敛 MVP

如果证据不够，就宁可留在 `pending_items` 或 `conflict_items`，不要抢着塞进 `confirmed_items`。

## 版本和 artifact 触发

以下时点通常值得生成版本快照：

- 第一次形成可用的 intake 摘要
- 第一次形成业务理解摘要
- 第一次形成真实需求定义
- 第一次形成稳定的 MVP 方向
- artifact 生成成功

以下时点通常值得触发 artifact：

- 用户已经不只是在闲聊，而是明确要沉淀方案
- 关键冲突已经被识别清楚，至少能写出边界
- 已经形成某个阶段性的可交付理解

## 方法论参考

这个 skill 可以吸收这些方法论视角，但不需要把术语硬塞给用户。

重点不是“知道这些名字”，而是知道在本项目里什么时候用、用来提取什么、最后落到哪个状态桶。

### BABOK 视角

适用时机：

- intake
- 早期澄清
- 范围和责任边界还不清楚的时候

在本项目里主要用来抽取：

- 业务目标
- 干系人
- 范围
- 约束
- 风险

默认落点：

- `current_understanding`
- `pending_items`

不要做的事：

- 不要把它写成“现在开始做 BABOK 分析”
- 不要只列术语，不落到具体业务内容

### JTBD 视角

适用时机：

- 判断“客户嘴上说的需求”和“真实要解决的任务”是不是一回事
- 用户一直在讲页面、按钮、自动化，但真实目标还没说透的时候

在本项目里主要用来抽取：

- 谁要完成任务
- 他真正要完成什么任务
- 他期待什么结果
- 当前最大的阻力是什么

默认落点：

- `current_understanding`
- `pending_items`
- `confirmed_items`

不要做的事：

- 不要把页面诉求直接当成 job
- 不要把“想要一个大屏 / 页面 / 按钮”直接等同于真实需求

### Event Storming 视角

适用时机：

- 还原业务流程
- 识别系统边界
- 识别异常和状态变化
- 判断哪些地方会形成冲突和规则歧义

在本项目里主要用来抽取：

- 关键事件
- 参与对象
- 系统边界
- 异常分支
- 状态变化

默认落点：

- `current_understanding`
- `conflict_items`
- `mvp_items`

不要做的事：

- 不要把流程图节点堆成一长串废话
- 不要只讲“有流程”，不指出冲突和异常发生在哪

### 视角优先级

如果三种视角同时都能用，优先级按这个顺序：

1. 先用 `BABOK` 看目标、边界、约束是不是清楚
2. 再用 `JTBD` 看真实任务和结果是不是说准了
3. 最后用 `Event Storming` 拆流程、事件、异常和系统边界

如果三种视角得出的结论互相打架：

- 先写进 `conflict_items`
- 证据不足时写进 `pending_items`
- 不要抢着塞进 `confirmed_items`

- `BABOK`
- `JTBD`
- `Event Storming`

它们在本项目里的作用是帮助分析者想清楚问题，不是要求后端逻辑机械照搬。

## 和运行时的关系

这个 skill 是 prompt 和分析思路参考。

在实现里，它应该影响：

- 主 agent prompt 结构
- 状态 patch 结构
- 追问数量和优先级
- artifact 触发条件

它不应该被误写成：

- 后端流程图的逐句复刻
- 数据库 schema 的直接翻译
- UI 阶段切页逻辑
