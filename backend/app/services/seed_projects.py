from __future__ import annotations

import shutil
from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..db import connection_scope
from ..models import ProjectSummary, StateItem
from .project_catalog import ProjectCatalog
from .project_state import ProjectStateService


SEED_PROJECT_ID = "seed-reconciliation"


def _seed_project() -> ProjectSummary:
    timestamp = "2026-04-16T09:00:00+08:00"
    return ProjectSummary(
        id=SEED_PROJECT_ID,
        name="集团业财逐笔对账需求分析",
        scenario_type="financial-reconciliation",
        summary=(
            "围绕订单/结算系统与财务系统对应科目金额的一致性校验，完成需求接入、"
            "业务理解、范围收敛、MVP 定义与交付物沉淀。"
        ),
        status="seed",
        created_at=timestamp,
        updated_at=timestamp,
        seed_key="reconciliation",
    )


def _reset_seed_project(settings: AppSettings) -> None:
    with connection_scope(settings) as connection:
        connection.execute(
            "DELETE FROM version_snapshots WHERE project_id = ?",
            (SEED_PROJECT_ID,),
        )
        connection.execute(
            "DELETE FROM demo_artifacts WHERE project_id = ?",
            (SEED_PROJECT_ID,),
        )
        connection.execute(
            "DELETE FROM state_items WHERE project_id = ?",
            (SEED_PROJECT_ID,),
        )
        connection.execute(
            "DELETE FROM messages WHERE project_id = ?",
            (SEED_PROJECT_ID,),
        )
        connection.execute(
            "DELETE FROM sources WHERE project_id = ?",
            (SEED_PROJECT_ID,),
        )
        connection.execute(
            "DELETE FROM projects WHERE id = ?",
            (SEED_PROJECT_ID,),
        )

    project_dir = settings.projects_dir / SEED_PROJECT_ID
    if project_dir.exists():
        # uvicorn --reload 时新旧 worker 进程可能并发清理同一目录，
        # 任何 FileNotFoundError 都可能由对方先删除导致，安全忽略。
        shutil.rmtree(project_dir, ignore_errors=True)


def _seed_source_specs() -> list[tuple[str, str, str, str]]:
    return [
        (
            "订单字段说明.md",
            "markdown",
            "梳理订单号、订单状态、业务类型、含税金额、渠道、退款标记和结算时间字段。",
            """# 订单字段说明

- 订单号：业务侧唯一单据标识，对账主键之一。
- 订单状态：已支付、已退款、部分退款、作废。
- 业务类型：直营、渠道、代销等，用于映射财务科目。
- 含税金额：业务侧展示金额，和财务侧税额拆分口径可能不同。
- 渠道：决定结算方式和部分税率。
- 退款标记：决定是否进入退款/冲销规则。
- 结算时间：用于确定财务入账周期。
""",
        ),
        (
            "结算单样例.xlsx",
            "spreadsheet",
            "包含结算单号、结算金额、税额拆分、手续费和渠道归属，用于核对逐笔结算口径。",
            """# Sheet: settlement_samples

表头: 结算单号 | 订单号 | 结算金额 | 税额 | 手续费 | 渠道归属
样例: SET-202604-001 | ORD-1001 | 1080.00 | 80.00 | 10.00 | 华东直营
样例: SET-202604-002 | ORD-1002 | -540.00 | -40.00 | 0.00 | 华南渠道
样例: SET-202604-003 | ORD-1003 | 2160.00 | 160.00 | 24.00 | 电商平台
行数估计: 2481, 列数估计: 6
""",
        ),
        (
            "财务科目口径说明.pdf",
            "pdf",
            "定义主营业务收入、退款冲销、税额和手续费对应的财务科目及入账口径。",
            """# 财务科目口径说明

- 主营业务收入：按业务类型和渠道归属挂科目。
- 退款冲销：按原始收入科目冲减，不与负单直接等价。
- 税额：财务侧按科目组合拆分，不完全复用业务侧税率拆分结果。
- 手续费：按渠道手续费科目单独入账。
- 入账记录：以凭证号和入账批次为准，不直接使用业务单号作为唯一主键。
""",
        ),
        (
            "历史差异清单.txt",
            "text",
            "记录退款重复记账、税额拆分不一致、同业务类型挂错科目等典型差异样本。",
            """历史差异清单
1. 退款订单 ORD-1002 在业务侧按负单处理，财务侧按冲销凭证处理，导致单号无法直接对齐。
2. 电商平台订单 ORD-1003 业务税额 160.00，财务税额拆分后为 158.40 + 1.60，结构不一致。
3. 渠道订单 ORD-1004 应挂“渠道收入”，实际入账到了“直营收入”。
4. 手续费在结算单中已净额扣减，但财务侧单独挂账，逐笔金额出现偏差。
""",
        ),
    ]


def _seed_sources(
    settings: AppSettings,
    catalog: ProjectCatalog,
) -> None:
    source_dir = settings.projects_dir / SEED_PROJECT_ID / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)

    for name, source_kind, parse_summary, content in _seed_source_specs():
        source_path = source_dir / name
        source_path.write_text(content, encoding="utf-8")
        catalog.create_source(
            project_id=SEED_PROJECT_ID,
            name=name,
            source_kind=source_kind,
            upload_kind="seed",
            storage_path=str(source_path),
            normalized_path=str(source_path),
            index_input_mode="direct_text",
            normalize_status="parsed",
            normalize_summary=parse_summary,
            index_status="pending",
            index_error="资料已标准化并写入 seed 项目目录，但当前还没有进入项目知识库索引。",
        )


def _seed_state(project_state: ProjectStateService) -> None:
    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="current_understanding",
        items=[
            StateItem(
                id="seed-understanding-1",
                title="逐笔对账锚点是业务单据与财务入账记录",
                body="不是先做汇总报表，而是先把订单/结算单与财务凭证或入账记录逐笔对上。",
            ),
            StateItem(
                id="seed-understanding-2",
                title="核心矛盾在业务字段到财务科目映射口径不一致",
                body="同类业务在不同渠道或场景下可能挂到不同科目，税额拆分和退款冲销也存在口径偏差。",
            ),
        ],
    )
    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="pending_items",
        items=[
            StateItem(
                id="seed-pending-1",
                title="退款、冲销、作废单是否都纳入一期",
                body="这直接决定特殊规则集合和异常闭环范围，需要财务负责人明确优先级。",
            ),
            StateItem(
                id="seed-pending-2",
                title="高金额差异是否必须人工复核",
                body="需要确定金额阈值和人工确认节点，避免系统自动归因越权。",
            ),
        ],
    )
    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="confirmed_items",
        items=[
            StateItem(
                id="seed-confirmed-1",
                title="一期不做自动改账",
                body="系统只负责发现差异、提示归因和沉淀处理过程，不自动修改财务结果。",
            ),
            StateItem(
                id="seed-confirmed-2",
                title="主要用户是财务/对账专员",
                body="业务运营和接口负责人参与规则确认，但日常使用者仍然是财务侧角色。",
            ),
        ],
    )
    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="conflict_items",
        items=[
            StateItem(
                id="seed-conflict-1",
                title="退款订单在业务侧按负单处理，在财务侧按冲销凭证处理",
                body="两边对象模型不同，导致无法直接按单号和金额一一映射。",
            ),
            StateItem(
                id="seed-conflict-2",
                title="税额拆分规则在结算单和财务入账之间不一致",
                body="业务侧按渠道税率拆分，财务侧按科目组合拆分，逐笔核对时会形成结构性差异。",
            ),
        ],
    )
    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="mvp_items",
        items=[
            StateItem(
                id="seed-mvp-1",
                title="数据接入与单据对齐",
                body="接入订单/结算数据和财务入账数据，形成逐笔比对基础索引。",
            ),
            StateItem(
                id="seed-mvp-2",
                title="规则驱动的差异识别与归因建议",
                body="基于映射规则输出金额差异、科目差异、税额差异和候选原因。",
            ),
            StateItem(
                id="seed-mvp-3",
                title="人工确认与导出闭环",
                body="把差异处理、复核意见和导出报告纳入同一条工作流。",
            ),
        ],
    )
    project_state.create_version(
        project_id=SEED_PROJECT_ID,
        trigger_kind="seed_bootstrap",
        summary="已重建业财逐笔对账 seed 项目，默认展示初始资料、需求理解、风险边界与交付物预览。",
    )


def _seed_messages(catalog: ProjectCatalog) -> None:
    messages = [
        (
            "user",
            "客户说希望核对订单或结算系统的数据，看看和财务系统里对应科目的金额是不是一致，最好别再靠 Excel 人工排查。",
            [],
        ),
        (
            "assistant",
            "我先确认问题定义。为什么现在先确认这个：如果一开始只把它当成“做自动对账”，后面很容易把范围做散。当前更像是要先定清逐笔对账锚点、业务字段到财务科目的映射关系，以及异常处理边界。",
            [],
        ),
        (
            "user",
            "对，财务侧关心的是和业务系统对应的那些科目金额。订单、结算、退款都可能涉及不同科目。",
            [],
        ),
        (
            "assistant",
            "我先把当前理解写清楚。第一，这里演示的是需求转译台在分析一个业财对账项目，不是直接演示对账系统本体。第二，逐笔对账的关键矛盾不是算不出差异，而是字段和科目映射口径不一致，所以人工才一直要反复排查。",
            [
                {"title": "订单字段说明.md", "source_id": "seed-source-order"},
                {"title": "财务科目口径说明.pdf", "source_id": "seed-source-finance"},
            ],
        ),
        (
            "user",
            "一期先别碰自动改账，你帮我把 MVP 和风险边界先收出来。",
            [],
        ),
        (
            "assistant",
            "我先收敛方案边界。为什么现在先确认这个：自动改账会把需求一下子拉到高风险区，一期更适合先做差异识别、归因建议和人工确认闭环。当前我会把“退款/冲销/作废单是否全部纳入”和“高金额差异的复核阈值”继续放在待确认项里。",
            [
                {"title": "结算单样例.xlsx", "source_id": "seed-source-settlement"},
                {"title": "历史差异清单.txt", "source_id": "seed-source-diff"},
            ],
        ),
    ]

    for role, content, refs in messages:
        catalog.create_message(
            project_id=SEED_PROJECT_ID,
            role=role,
            content=content,
            source_refs=refs,
            stream_group_id="seed-thread",
        )


def _artifact_shell(title: str, subtitle: str, body: str, inner_html: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
    <style>
      :root {{
        color-scheme: light;
        --ink: #12253d;
        --muted: #607188;
        --line: #d7e1ec;
        --accent: #17476f;
        --accent-soft: #deebf8;
        --sand: #f4efe7;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(23, 71, 111, 0.10), transparent 30%),
          linear-gradient(180deg, #eef4f9 0%, #f8fafc 52%, #eef2f7 100%);
        color: var(--ink);
      }}
      .shell {{
        max-width: 1380px;
        margin: 0 auto;
        padding: 32px;
      }}
      .hero {{
        display: flex;
        justify-content: space-between;
        gap: 24px;
        align-items: flex-start;
        padding: 28px 32px;
        border: 1px solid rgba(255,255,255,0.75);
        border-radius: 28px;
        background: rgba(255,255,255,0.92);
        box-shadow: 0 24px 60px rgba(18, 37, 61, 0.08);
      }}
      .eyebrow {{
        margin: 0 0 10px;
        color: var(--muted);
        font-size: 12px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
      }}
      h1 {{
        margin: 0;
        font-size: 34px;
      }}
      p {{
        margin: 0;
        line-height: 1.8;
      }}
      .summary {{
        max-width: 760px;
        color: var(--muted);
        margin-top: 12px;
      }}
      .tag-list {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }}
      .tag {{
        padding: 8px 12px;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--accent);
        font-size: 12px;
        font-weight: 600;
      }}
      .canvas {{
        margin-top: 18px;
        display: grid;
        gap: 18px;
      }}
      .panel {{
        border-radius: 26px;
        border: 1px solid rgba(255,255,255,0.8);
        background: rgba(255,255,255,0.94);
        box-shadow: 0 18px 42px rgba(18, 37, 61, 0.08);
        padding: 24px;
      }}
      .muted {{
        color: var(--muted);
      }}
      .chip {{
        display: inline-flex;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        background: #f3efe7;
        font-size: 12px;
        color: #6a5f4c;
        margin-right: 8px;
      }}
      .grid {{
        display: grid;
        gap: 16px;
      }}
      .grid-2 {{
        grid-template-columns: 1.15fr 0.85fr;
      }}
      .card {{
        border: 1px solid var(--line);
        border-radius: 22px;
        background: #f8fbff;
        padding: 18px;
      }}
      .card h3 {{
        margin: 0 0 10px;
        font-size: 16px;
      }}
      .table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 12px;
        font-size: 14px;
      }}
      .table th,
      .table td {{
        text-align: left;
        padding: 12px 10px;
        border-bottom: 1px solid #e8eef5;
      }}
      .table th {{
        color: var(--muted);
        font-size: 12px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .lane {{
        display: grid;
        gap: 12px;
        margin-top: 14px;
      }}
      .step {{
        border: 1px solid var(--line);
        border-radius: 20px;
        background: white;
        padding: 16px;
      }}
      .step strong {{
        display: block;
        margin-bottom: 8px;
      }}
      .footer-note {{
        margin-top: 14px;
        font-size: 13px;
        color: var(--muted);
      }}
      @media (max-width: 980px) {{
        .hero,
        .grid-2 {{
          grid-template-columns: 1fr;
          display: grid;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <div>
          <p class="eyebrow">{subtitle}</p>
          <h1>{title}</h1>
          <p class="summary">{body}</p>
        </div>
        <div class="tag-list">
          <span class="tag">业财逐笔对账</span>
          <span class="tag">需求转译台产出</span>
          <span class="tag">一期演示稿</span>
        </div>
      </section>
      <section class="canvas">
        {inner_html}
      </section>
    </main>
  </body>
</html>
"""


def _write_page_solution_html(settings: AppSettings) -> Path:
    html = _artifact_shell(
        "业财逐笔对账页面方案",
        "Page Solution",
        "页面方案把未来对账系统收敛为总览、逐笔差异、异常处理、规则配置和导出报告五个页面，重点突出逐笔定位和人工复核闭环。",
        """
        <section class="panel grid grid-2">
          <div class="card">
            <p class="eyebrow">Page Map</p>
            <h2>页面清单</h2>
            <div class="lane">
              <div class="step"><strong>对账总览页</strong>展示差异总量、差异金额、异常分类和待确认任务。</div>
              <div class="step"><strong>逐笔差异明细页</strong>按业务单号、科目、渠道、含税口径和差异原因联合筛选。</div>
              <div class="step"><strong>异常处理页</strong>保留确认归因、指派责任人、补录说明和处理状态流转。</div>
              <div class="step"><strong>映射规则配置页</strong>维护业务字段到财务科目的映射口径、特殊交易规则和优先级。</div>
              <div class="step"><strong>导出报告页</strong>导出差异明细、处理结论和复核记录，供财务归档。</div>
            </div>
          </div>
          <div class="card">
            <p class="eyebrow">Wireframe Focus</p>
            <h2>总览页线框重点</h2>
            <span class="chip">差异总额</span>
            <span class="chip">高风险任务</span>
            <span class="chip">规则覆盖率</span>
            <table class="table">
              <thead>
                <tr><th>模块</th><th>内容</th></tr>
              </thead>
              <tbody>
                <tr><td>顶部 KPI</td><td>逐笔对账成功率、未处理差异、今日新增异常</td></tr>
                <tr><td>中部看板</td><td>金额差异、科目差异、税额差异、退款异常四类卡片</td></tr>
                <tr><td>底部列表</td><td>待人工确认的高金额差异与规则缺口</td></tr>
              </tbody>
            </table>
            <p class="footer-note">设计上强调“先看到风险，再进入逐笔定位”，而不是先堆复杂配置。</p>
          </div>
        </section>
        <section class="panel">
          <p class="eyebrow">Detail Page</p>
          <h2>逐笔差异明细页信息架构</h2>
          <table class="table">
            <thead>
              <tr>
                <th>区域</th>
                <th>核心信息</th>
                <th>交互目标</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>筛选条</td>
                <td>业务单号、结算单号、科目、渠道、差异类型、处理状态</td>
                <td>把疑难差异快速收敛到可操作范围</td>
              </tr>
              <tr>
                <td>差异主表</td>
                <td>业务金额、财务金额、税额、差异值、建议原因</td>
                <td>先看结果，再看归因建议</td>
              </tr>
              <tr>
                <td>右侧详情</td>
                <td>业务原单、财务凭证、规则命中记录、历史处理备注</td>
                <td>支持人工复核和处理闭环</td>
              </tr>
            </tbody>
          </table>
        </section>
        """,
    )
    artifact_dir = settings.projects_dir / SEED_PROJECT_ID / "artifacts" / "page_solution"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def _write_interaction_flow_html(settings: AppSettings) -> Path:
    html = _artifact_shell(
        "业财逐笔对账关键交互稿",
        "Interaction Flow",
        "交互稿聚焦财务/对账专员从发现差异、筛选原因、确认归因到提交处理和导出报告的主流程，避免把系统做成只会展示数据的静态报表。",
        """
        <section class="panel grid grid-2">
          <div class="card">
            <p class="eyebrow">Primary Flow</p>
            <h2>主流程</h2>
            <div class="lane">
              <div class="step"><strong>1. 查看差异总览</strong>先看到高风险差异和规则缺口，再决定从哪一批差异切入。</div>
              <div class="step"><strong>2. 筛选差异原因</strong>按金额、科目、渠道、退款/冲销标签收敛候选差异。</div>
              <div class="step"><strong>3. 确认归因</strong>系统给出规则命中结果，人工选择最终原因并补充说明。</div>
              <div class="step"><strong>4. 提交处理</strong>把差异转入待修复、待复核或已关闭状态，并沉淀责任人和处理意见。</div>
              <div class="step"><strong>5. 导出报告</strong>输出差异明细、归因结论和未决问题，供财务复盘和项目推进。</div>
            </div>
          </div>
          <div class="card">
            <p class="eyebrow">Interaction Rules</p>
            <h2>关键约束</h2>
            <div class="lane">
              <div class="step"><strong>归因建议不等于最终结论</strong>高金额差异和特殊交易必须人工确认。</div>
              <div class="step"><strong>规则缺口要显式暴露</strong>不能把未知情况偷偷归类成“其他”。</div>
              <div class="step"><strong>所有处理动作要留痕</strong>导出报告必须能回溯到规则命中和人工确认记录。</div>
            </div>
          </div>
        </section>
        <section class="panel">
          <p class="eyebrow">Flow by Screen</p>
          <h2>页面之间的衔接</h2>
          <table class="table">
            <thead>
              <tr>
                <th>起点</th>
                <th>动作</th>
                <th>落点</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>对账总览页</td>
                <td>点击“高金额差异”</td>
                <td>带着筛选条件进入逐笔差异明细页</td>
              </tr>
              <tr>
                <td>逐笔差异明细页</td>
                <td>打开右侧详情并确认归因</td>
                <td>进入异常处理页，补充处理意见</td>
              </tr>
              <tr>
                <td>异常处理页</td>
                <td>选择“规则需调整”</td>
                <td>跳转映射规则配置页，带出冲突样本</td>
              </tr>
              <tr>
                <td>导出报告页</td>
                <td>勾选“仅导出未关闭差异”</td>
                <td>生成当前阶段问题清单，供财务例会使用</td>
              </tr>
            </tbody>
          </table>
        </section>
        """,
    )
    artifact_dir = settings.projects_dir / SEED_PROJECT_ID / "artifacts" / "interaction_flow"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def _seed_artifacts(settings: AppSettings, catalog: ProjectCatalog) -> None:
    page_path = _write_page_solution_html(settings)
    flow_path = _write_interaction_flow_html(settings)

    catalog.save_artifact(
        project_id=SEED_PROJECT_ID,
        artifact_type="document",
        title="需求分析与 MVP 文档稿",
        summary="沉淀真实需求、范围边界、主要冲突、MVP 能力包与验收指标。",
        status="seed_ready",
        content_format="markdown",
        storage_path=None,
        body=(
            "# 一、项目目标\n\n"
            "围绕订单/结算系统与财务系统对应科目金额的一致性校验，完成逐笔差异识别、归因建议和人工确认闭环。\n\n"
            "# 二、真实需求\n\n"
            "1. 以业务单据与财务入账记录为逐笔对账锚点。\n"
            "2. 把业务字段到财务科目的映射口径沉淀成可维护规则。\n"
            "3. 对退款、冲销、税额拆分等特殊场景形成可解释的差异原因。\n\n"
            "# 三、范围边界\n\n"
            "- 一期不自动改账。\n"
            "- 高金额差异必须人工复核。\n"
            "- 规则未确认时只标记风险，不默认自动归因。\n\n"
            "# 四、MVP 能力包\n\n"
            "- 数据接入与单据对齐\n"
            "- 映射规则管理\n"
            "- 差异识别与归因建议\n"
            "- 异常处理闭环与报告导出\n\n"
            "# 五、验收指标\n\n"
            "- 对账耗时下降\n"
            "- 差异定位时效提升\n"
            "- 人工核对工作量下降\n"
            "- 规则覆盖率提升\n"
        ),
        metadata={"seed": True},
        artifact_id="seed-document",
    )
    catalog.save_artifact(
        project_id=SEED_PROJECT_ID,
        artifact_type="page_solution",
        title="页面方案",
        summary="未来业财逐笔对账系统的页面结构和线框重点预览。",
        status="seed_ready",
        content_format="html",
        storage_path=str(page_path),
        body=None,
        metadata={"seed": True},
        artifact_id="seed-page-solution",
    )
    catalog.save_artifact(
        project_id=SEED_PROJECT_ID,
        artifact_type="interaction_flow",
        title="交互稿",
        summary="聚焦差异定位、归因确认、处理提交和导出报告的关键交互流。",
        status="seed_ready",
        content_format="html",
        storage_path=str(flow_path),
        body=None,
        metadata={"seed": True},
        artifact_id="seed-interaction-flow",
    )


def ensure_seed_project(settings: AppSettings = DEFAULT_SETTINGS) -> None:
    catalog = ProjectCatalog(settings)
    _reset_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    catalog.upsert_project(_seed_project())
    _seed_sources(settings, catalog)
    _seed_state(project_state)
    _seed_messages(catalog)
    _seed_artifacts(settings, catalog)
