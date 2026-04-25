# Workbench Flow & State Refine Todo

## 背景

当前工作台已经是单页分析台，没有再按阶段硬切页，也已经接通了真实前后端链路。

这一轮优化不重做主链路，重点解决两件事：

1. 让五个阶段从“内部隐含状态”变成“用户可感知但不生硬的分析进度语义”
2. 让右侧沉淀区从“分类卡片列表”升级成“项目资产总览 + 抽屉 + 条目详情”

本轮默认不改数据库 schema，不改 provider 接入方式，优先以前端派生完成表达层优化。

## 目标

- 顶部能清楚表达当前主线推进阶段
- 顶部能表达局部回流，而不是只显示单向 index
- 右侧首页能像项目资产面板，而不是一堆并列状态卡
- 用户能从右侧首页进入抽屉，再进入条目详情
- 不破坏现有 source 浮卡、artifact 大预览、聊天发送与 SSE 主流程

## 范围内

- `primaryStage` / `revisitingStages` 前端派生
- 顶部轻量阶段条
- 右侧沉淀总集重组为资产总览
- 右侧抽屉
- 条目详情面板
- 配套前端测试与构建验证

## 范围外

- 后端 schema 调整
- 阶段状态回写数据库
- 聊天消息与条目、source 的双向跳转
- 复杂筛选和排序器
- artifact 生成逻辑重构
- provider 链路改造

## 实施 Todo

### 1. 阶段派生层

- [x] 新增阶段枚举定义
  - `intake`
  - `business_understanding`
  - `requirement_alignment`
  - `solution_definition`
  - `design_delivery`
- [x] 从现有 `ProjectState + artifacts` 派生 `primaryStage`
- [x] 从现有 `ProjectState + recentInsightIds` 派生 `revisitingStages`
- [x] 替换当前页面内直接使用的 `stageIndex` 判断
- [x] 提供阶段中文标签和展示文案映射

### 2. 阶段判定规则

- [x] 定义 `primaryStage` 第一版规则
  - 无结构化沉淀时为 `intake`
  - 有 `current_understanding` 时为 `business_understanding`
  - 有 `confirmed_items` 或 `conflict_items` 时为 `requirement_alignment`
  - 有 `mvp_items` 时为 `solution_definition`
  - 有 `artifacts` 时为 `design_delivery`
- [x] 定义 `revisitingStages` 第一版规则
  - `primaryStage >= requirement_alignment` 且新增高优先级 `pending_items` 时回流到 `business_understanding`
  - `primaryStage >= solution_definition` 且新增高优先级 `conflict_items` 时回流到 `requirement_alignment`
  - `primaryStage == design_delivery` 且出现新 `pending_items / conflict_items` 时默认回流到 `requirement_alignment`

### 3. 顶部阶段条

- [x] 新增轻量阶段条组件
- [x] 支持三种阶段状态
  - 已完成
  - 当前重点
  - 补充中
- [x] 移除 `Stage 1..5` 这类编号文案
- [x] 使用中文阶段名直接展示
- [x] 保持阶段条不可点击、不承担导航职责
- [x] 控制高度，避免把顶部继续做大

### 4. 聊天区阶段提示

- [ ] 设计阶段提示节点展示样式
- [ ] 第一版先做“当前阶段摘要”提示
- [ ] 只在主阶段变化或出现回流时展示
- [ ] 文案保持系统提示风格，不做大卡片

### 5. 右侧资产总览

- [x] 将右侧首页重组为以下 6 个资产块
  - 当前需求定义
  - 关键待确认
  - 风险与冲突
  - MVP 结论
  - 交付物
  - 版本快照
- [x] 区分主资产和列表资产
  - 主资产：当前需求定义、MVP 结论
  - 列表资产：待确认项、冲突项、交付物、版本快照
- [x] 每个资产块显示数量、最近更新时间、本轮新增状态
- [x] 首页每块仅展示摘要和前几项，不展示全量列表

### 6. 抽屉与详情

- [x] 新增资产块抽屉
- [x] 点击资产块打开该类条目抽屉
- [x] 新增条目详情面板
- [x] 点击条目进入详情
- [x] 详情展示字段
  - 标题
  - 正文
  - 状态
  - 形成阶段
  - 最近更新阶段
  - 更新时间
  - 来源资料数

### 7. 阶段来源展示

- [x] 为右侧条目补充 `形成于` 阶段信息
- [x] 为右侧条目补充 `最近更新于` 阶段信息
- [ ] 若属于回流修正，增加轻量 `补充修正` 标识
- [x] 第一版全部采用前端推断，不新增后端字段

### 8. 纯函数与前端派生

- [x] 抽出 `deriveStageState(...)`
- [x] 抽出 `deriveStateOverviewSections(...)`
- [x] 抽出阶段文案和状态标签映射函数
- [x] 避免继续把派生逻辑堆在 `WorkbenchPage.tsx`

### 9. 组件拆分

- [x] 新增 `WorkbenchStageRail`
- [ ] 新增 `StageTransitionMarker`
- [ ] 新增 `ProjectStateOverview`
- [x] 新增 `StateSectionCard`
- [x] 新增 `StateSectionDrawer`
- [x] 新增 `StateItemDetailPanel`
- [x] 控制 `WorkbenchPage` 不继续膨胀

### 10. 测试

- [x] 先补纯函数测试
  - `primaryStage` 判定
  - `revisitingStages` 判定
  - 资产总览分组
- [x] 补工作台集成测试
  - 顶部显示 `当前重点`
  - 顶部显示 `补充中`
  - 右侧显示资产块
  - 点击资产块打开抽屉
  - 点击条目打开详情
- [x] 跑现有回归测试
  - source 浮卡
  - artifact 大预览
  - 聊天发送
  - 本轮新增高亮

### 11. 验证

- [x] `npm test -- src/features/workbench/workbench-derived.test.ts src/App.test.tsx`
- [x] `npm test -- src/App.test.tsx`
- [x] `npm run build`
- [ ] 如有必要，用 Chrome DevTools 做一轮工作台手工联调
  - 已尝试起前端并接浏览器检查
  - 当前 `http://127.0.0.1:8000/api/projects/seed-reconciliation` 返回 `404`
  - 说明这轮视觉代码已可构建，但完整浏览器联调仍依赖正确启动项目后端

## 建议执行顺序

1. 先补阶段派生与资产分组的纯函数测试
2. 实现派生层
3. 接入顶部阶段条
4. 重组右侧资产总览
5. 实现抽屉与详情
6. 再补聊天区阶段提示
7. 最后统一做样式和密度调整

## 完成标准

- 用户能看出当前主线推进到哪一个阶段
- 用户能看出哪些前置问题在补充中
- 右侧首页看起来像项目资产总览，而不是状态卡堆叠
- 当前需求定义和 MVP 结论不再与普通列表项混排
- 点击资产块能打开抽屉，点击条目能看详情
- 不引入新的页面切换
- 不破坏现有主工作台链路
