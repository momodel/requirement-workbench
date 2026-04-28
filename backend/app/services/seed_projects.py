from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import AppSettings, DEFAULT_SETTINGS
from ..db import connection_scope
from ..models import ProjectSummary, StateItem
from .project_catalog import ProjectCatalog
from .project_state import ProjectStateService


SEED_PROJECT_ID = "seed-reconciliation"

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_MATERIALS_DIR = REPO_ROOT / "docs" / "客户需求转译台-原始材料"
SEED_ASSETS_DIR = Path(__file__).resolve().parent / "seed_assets"
CHAT_IMAGES_SOURCE_DIR = SEED_ASSETS_DIR / "chat-images"
IMAGE_URL_PREFIX = f"/api/projects/{SEED_PROJECT_ID}/chat-images"


def _seed_project() -> ProjectSummary:
    timestamp = "2026-04-27T09:00:00+08:00"
    return ProjectSummary(
        id=SEED_PROJECT_ID,
        name="客户需求转译台·产品自我分析",
        scenario_type="product-self-analysis",
        summary=(
            "把客户需求转译台这个产品本身当成一个待分析的客户需求："
            "梳理它面向谁、解决什么、形态是什么、边界在哪，"
            "并把整个分析过程沉淀成一份完整的需求稿、页面方案与交互稿。"
        ),
        status="seed",
        created_at=timestamp,
        updated_at=timestamp,
        seed_key="self-analysis",
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
        shutil.rmtree(project_dir)


def _seed_source_specs() -> list[tuple[str, str, str]]:
    """Return (filename, source_kind, normalize_summary) for raw client materials.

    Files are read verbatim from docs/客户需求转译台-原始材料/ — they are the actual
    raw materials that started this product, used here as the recursive demo input.
    """
    return [
        (
            "项目背景-先看这个.md",
            "markdown",
            "客户内部口吻的项目缘起，列出诉求、使用场景与未拍板的几个关键点。",
        ),
        (
            "补充说明-v1.md",
            "markdown",
            "会后补充说明，分 5 节：项目定位 / 使用人 / 输入材料 / 结果产出 / 零散点。",
        ),
        (
            "微信群里先聊的内容整理.md",
            "markdown",
            "3.24–3.27 微信群聊原文整理，含张总 / 李敏 / 陈帆 / 赵倩 4 人发言。",
        ),
        (
            "0328碰一下会议纪要.md",
            "markdown",
            "3.28 需求碰头会纪要，含「当前没定的」与「会后动作」两节。",
        ),
        (
            "现有材料先发这些.txt",
            "text",
            "材料清单，列出 7 项手头资料及其完整度（PPT / 纪要 / 草图 / 案例材料 / 截图）。",
        ),
    ]


def _seed_sources(
    settings: AppSettings,
    catalog: ProjectCatalog,
) -> None:
    source_dir = settings.projects_dir / SEED_PROJECT_ID / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)

    for name, source_kind, parse_summary in _seed_source_specs():
        raw_path = RAW_MATERIALS_DIR / name
        content = raw_path.read_text(encoding="utf-8")
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
            index_status="indexed",
            index_error=None,
        )


def _seed_state(project_state: ProjectStateService) -> None:
    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="current_understanding",
        items=[
            StateItem(
                id="seed-self-understanding-1",
                title="是把客户模糊诉求转成可交付物的「需求转译台」，不是通用聊天助手",
                body=(
                    "原始材料里反复出现「客户讲得乱」「前面聊清楚后面还要重新整理」——"
                    "核心定位是接住散乱诉求并沉淀成可继续推进的结构化结果。"
                ),
            ),
            StateItem(
                id="seed-self-understanding-2",
                title="产品形态是三栏工作台：左资料 / 中聊天 / 右沉淀",
                body=(
                    "0328 纪要明确「不是一个单聊天界面」——一边看资料、一边聊天、一边看整理后的结论；"
                    "每一轮分析在三栏上同步推进。"
                ),
            ),
            StateItem(
                id="seed-self-understanding-3",
                title="沉淀按类落盘（7 类），不靠 LLM 总结合并",
                body=(
                    "客户多次强调「看到哪些已确认、哪些没确认很重要」——分类持久化是产品的核心承诺，"
                    "不允许用一段总结把分类糊起来。"
                ),
            ),
            StateItem(
                id="seed-self-understanding-4",
                title="主要使用人是售前 / 咨询顾问 / 产品经理",
                body=(
                    "补充说明 §2 列出 3 段使用人；客户方是否直接用还没定，"
                    "暂按「内部 + 可能给客户一起看」的双重身份理解。"
                ),
            ),
        ],
    )

    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="pending_items",
        items=[
            StateItem(
                id="seed-self-pending-1",
                title="音频/语音输入一期是否纳入",
                body=(
                    "群聊和补充说明对此口径不一致——3.26 群聊倾向「先别太重」，"
                    "补充说明 §3 又把「语音」放在输入清单里，需要拍板。"
                ),
            ),
            StateItem(
                id="seed-self-pending-2",
                title="客户方是否直接使用这个工作台",
                body=(
                    "补充说明 §2 写「客户方的人会不会直接用，现在没有定」——"
                    "直接影响交互复杂度与权限边界。"
                ),
            ),
            StateItem(
                id="seed-self-pending-3",
                title="输出物是否包含页面草图与原型方向",
                body=(
                    "补充说明 §4 列了两种想法（只出需求结论 / 出到原型方向），"
                    "到底走到哪一步还要再收一收。"
                ),
            ),
        ],
    )

    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="confirmed_items",
        items=[
            StateItem(
                id="seed-self-confirmed-1",
                title="一期不做大平台，只做需求转译这一个场景",
                body=(
                    "0328 纪要「会后动作」明确「先出一个比较轻的方向，不要直接做成大而全」；"
                    "群聊里「第一版别太重」也反复出现。"
                ),
            ),
            StateItem(
                id="seed-self-confirmed-2",
                title="第一版不做权限，先专注分析与沉淀本身",
                body=(
                    "0328 纪要「当前没定的」列了「有没有必要做权限」——目前共识是先不做。"
                ),
            ),
            StateItem(
                id="seed-self-confirmed-3",
                title="输出至少要「能继续推进讨论」",
                body=(
                    "补充说明 §4 与 0328 纪要 §3 都强调最差也要「一份可以继续讨论的文档」，"
                    "不能只是聊天记录。"
                ),
            ),
        ],
    )

    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="conflict_items",
        items=[
            StateItem(
                id="seed-self-conflict-1",
                title="群聊 vs 补充说明对「音频是否第一版做」口径不一致",
                body=(
                    "3.26 陈帆群里说「先把资料接入、分析过程、结论沉淀这几件事跑通」暗示先不做音频；"
                    "补充说明 §3 又把「语音」列在输入清单。需要会议明确。"
                ),
            ),
            StateItem(
                id="seed-self-conflict-2",
                title="想做轻 vs 想给原型方向之间的张力",
                body=(
                    "补充说明 §1 说「第一版先证明方向成立就行」，§4 又允许「带一点初版方案 / 页面草图」——"
                    "需求轻重边界还没收齐。"
                ),
            ),
        ],
    )

    project_state.replace_category(
        project_id=SEED_PROJECT_ID,
        category="mvp_items",
        items=[
            StateItem(
                id="seed-self-mvp-1",
                title="三栏工作台基础：资料上传 + 聊天分析 + 沉淀同步",
                body=(
                    "左侧接收混杂资料（md / pdf / txt / 截图）、中间聊天驱动分析、"
                    "右侧 7 类沉淀实时更新；三栏在每一轮分析中同步演进。"
                ),
            ),
            StateItem(
                id="seed-self-mvp-2",
                title="7 类状态沉淀按类落盘",
                body=(
                    "current_understanding / pending / confirmed / conflict / mvp / versions / artifacts，"
                    "每类独立维护、可单独追加或撤回，不允许 LLM 用总结合并分类。"
                ),
            ),
            StateItem(
                id="seed-self-mvp-3",
                title="三件套交付物 + 版本快照",
                body=(
                    "document（需求稿 markdown）+ page_solution（页面方案 HTML）+ "
                    "interaction_flow（交互稿 HTML），每次重要节点打版本快照可回溯。"
                ),
            ),
            StateItem(
                id="seed-self-mvp-4",
                title="多模态消息（一期：文本 + 图片）",
                body=(
                    "聊天里支持插入截图与生成图，让分析过程可以引用视觉素材；"
                    "语音 / 视频先不进 MVP，留到 pending 项收敛后再议。"
                ),
            ),
        ],
    )

    project_state.create_version(
        project_id=SEED_PROJECT_ID,
        trigger_kind="seed_bootstrap",
        summary=(
            "已重建产品自我分析 seed 项目，默认展示 5 份原始客户材料、"
            "agent 引导的 18 条分析对话（含 3 张生图与「先生图 → 用户确认 → 照图出 HTML」节奏）、"
            "7 类沉淀与三件套交付物预览。"
        ),
    )


def _seed_messages(catalog: ProjectCatalog) -> None:
    src_bg = {"title": "项目背景-先看这个.md", "source_id": "seed-source-bg"}
    src_supp = {"title": "补充说明-v1.md", "source_id": "seed-source-supp"}
    src_wechat = {"title": "微信群里先聊的内容整理.md", "source_id": "seed-source-wechat"}
    src_mtg = {"title": "0328碰一下会议纪要.md", "source_id": "seed-source-mtg"}
    src_list = {"title": "现有材料先发这些.txt", "source_id": "seed-source-list"}

    img_overview = {
        "__image_results__": [
            {
                "id": "seed-img-system-overview",
                "title": "客户需求转译台 · 系统总览",
                "url": f"{IMAGE_URL_PREFIX}/system-overview",
                "summary": "三栏工作台 + 三件套交付物的整体布局示意。",
            }
        ]
    }
    img_sediment = {
        "__image_results__": [
            {
                "id": "seed-img-state-sediment",
                "title": "7 类沉淀分类全景",
                "url": f"{IMAGE_URL_PREFIX}/state-sediment",
                "summary": "current_understanding / pending / confirmed / conflict / mvp / versions / artifacts，颜色编码与触发条件。",
            }
        ]
    }
    img_chat_flow = {
        "__image_results__": [
            {
                "id": "seed-img-chat-flow",
                "title": "端到端聊天流",
                "url": f"{IMAGE_URL_PREFIX}/chat-flow",
                "summary": "用户输入 → RAG 证据召回 → Wiki 综合 → 状态 patch → artifact 触发 → 三件套产物。",
            }
        ]
    }

    messages: list[tuple[str, str, list[dict]]] = [
        (
            "user",
            "这堆材料先发你了，群里聊的、会议纪要、补充说明都有。帮我看看，我们这东西到底要做成什么样。先别出方案。",
            [],
        ),
        (
            "assistant",
            (
                "我先把 5 份材料过一遍，给你一版「我看到了什么」。\n\n"
                "初步看到 3 件事：第一，你们想做的不是聊天机器人，而是把客户那种「想法不是需求」的散乱表达接住、"
                "再整理成可推进结果的工作台。第二，输入材料天生很杂——会议纪要、群聊、补充说明、截图、PPT 都会有。"
                "第三，你们自己反复在说「不要做太重」，但又希望能往后多走一步、带一点页面草图。\n\n"
                "这一轮我没急着写沉淀，先停在讨论态。两件我现在就能看到、但材料里没说清的事：\n"
                "1) 客户方的人会不会直接用这个工作台？补充说明 §2 写「还没定」——这会直接影响交互形态。\n"
                "2) 输出到底走到哪一步——只出需求结论，还是要带原型方向？补充说明 §4 给了两种想法。\n\n"
                "要不要我把这两条先写到右侧「待确认」？"
            ),
            [src_bg, src_supp, src_wechat, src_mtg, src_list],
        ),
        ("user", "写吧。", []),
        (
            "assistant",
            (
                "两条 pending 已写到右侧。继续往下：\n\n"
                "我把核心矛盾往清楚里讲一下：你们自己在反复说「客户讲的是想法不是需求」，"
                "但你们内部对「一期到底做到哪一步」也没收齐——这两件事其实是一回事，"
                "都是「前期分析没有可沉淀的中间态」导致的。3 段使用人（售前 / 咨询 / 产品）抓到的信息也不一致。\n\n"
                "所以「产品形态是三栏工作台、不是单聊天界面」这条已经被原始材料反复说到了——"
                "0328 纪要里「一边看资料、一边聊天、一边看整理后的结论」就是这个意思。\n\n"
                "我建议把「是个把模糊诉求转成可交付物的需求转译台」和「产品形态是三栏工作台」"
                "这两条作为当前最可信的工作理解写进 current_understanding。可以吗？"
            ),
            [src_bg, src_mtg],
        ),
        ("user", "可以。", []),
        (
            "assistant",
            (
                "current_understanding 落了 4 条（核心定位 / 三栏形态 / 7 类沉淀 / 主要使用人是 3 段 PM 角色）。\n\n"
                "顺手抛一个我看到的冲突：你们群里和补充说明对「音频是否第一版做」口径不一致——"
                "3.26 群里陈帆说「先把资料接入、分析过程、结论沉淀这几件事跑通」暗示先不做，"
                "补充说明 §3 又把「语音」放在输入清单里。我把这个标到 conflict_items 了。\n\n"
                "还有 3 条事实其实在材料里已经被反复确认，建议落到 confirmed_items：\n"
                "- 一期不做大平台，只做需求转译这一个场景（0328 纪要「会后动作」明确）\n"
                "- 第一版不做权限（0328 纪要「当前没定的」，但群聊倾向不做）\n"
                "- 输出至少要「能继续推进讨论」（补充说明 §4 + 0328 纪要 §3）\n\n"
                "3 条 confirmed 我直接落了？"
            ),
            [src_wechat, src_supp],
        ),
        ("user", "落。", []),
        (
            "assistant",
            (
                "3 条 confirmed + 1 条 conflict 已落。基于已有边界，我把 MVP 收一版给你看：\n\n"
                "1) 三栏工作台基础（左资料上传 / 中聊天分析 / 右沉淀同步）\n"
                "2) 7 类状态沉淀按类落盘\n"
                "3) 三件套交付物 + 版本快照（document / page_solution / interaction_flow）\n"
                "4) 多模态消息（一期：文本 + 图片；语音 / 视频先不进）\n\n"
                "如果你认可这个 MVP 框架，我直接整理一版需求稿初稿到右侧交付物面板，你看完再回来调具体哪条。"
            ),
            [src_mtg, src_supp],
        ),
        ("user", "来。", []),
        (
            "assistant",
            (
                "需求稿已经放到右侧「需求分析与 MVP 文档稿」，包含项目目标、真实需求、范围边界、"
                "冲突与风险、MVP 能力包、验收建议 6 章。基于已确认的 3 条事实 + 已落的 4 条理解写的，"
                "把 2 条 pending 和 1 条 conflict 都标在了「待确认 / 风险」区，没有伪造结论。\n\n"
                "下一步要出页面方案 HTML，但 HTML 直接写完容易方向不对——我先画一张「系统总览图」给你确认结构对不对，"
                "再照着图出 HTML 才稳。先看图。"
            ),
            [src_supp, img_overview],
        ),
        ("user", "整体感觉对，但右栏沉淀那块看不清。", []),
        (
            "assistant",
            (
                "重画一张更细的「7 类沉淀全景」给你——每类一张色块，标注触发条件和一条样例，颜色编码对上。\n\n"
                "这张图就是页面方案右侧沉淀区的直接依据。两张图（系统总览 + 沉淀全景）这下齐了，结构和颜色都讲清楚了。"
                "等你确认 OK，我就照着这两张图出 page_solution HTML，HTML 里的页面拆分和右栏分类会一比一对应这两张图。"
            ),
            [src_bg, img_sediment],
        ),
        ("user", "这下清楚了，照图出 HTML 吧。", []),
        (
            "assistant",
            (
                "page_solution HTML 已经生成，放到右侧「三栏工作台页面方案」可以预览。\n\n"
                "我是这么对应的：\n"
                "- 系统总览图里的「左资料 / 中聊天 / 右沉淀 / 底部三件套」→ HTML 里的工作台三栏线框区\n"
                "- 沉淀全景图里的 7 类色块 + 触发条件 → HTML 里的「右侧 7 类沉淀的分类与触发」表\n"
                "- 总览图里隐含的 5 张页面（首页 / 工作台 / 资料预览 / 沉淀详情抽屉 / 交付物预览）→ HTML 顶部「页面清单」\n\n"
                "如果哪里和图不一致，告诉我哪一块，我改图或改 HTML 都行。"
            ),
            [src_mtg],
        ),
        ("user", "对得上。再来交互稿。", []),
        (
            "assistant",
            (
                "交互稿之前一样先确认流程——我画一张端到端聊天流图，把「用户输入 → RAG 证据召回 → "
                "LLM Wiki 综合 → 状态 patch → artifact 触发 → 三件套产物」每一步走过的环节标出来。\n\n"
                "你看流程对了，我就照这张图出 interaction_flow HTML，HTML 里的主流程会一一对应这张图的节点。"
            ),
            [src_supp, img_chat_flow],
        ),
        ("user", "流程对，出 HTML 吧。", []),
        (
            "assistant",
            (
                "interaction_flow HTML 已生成，放到右侧「端到端转译交互稿」可以预览。\n\n"
                "HTML 里我是这么对应聊天流图的：\n"
                "- 图里 6 个主节点 → 主流程 5 步 + 三件套触发判断（用户明示？菱形对应「执行态」入口）\n"
                "- 图里两个分支注释（讨论态：仅聊天 / 执行态：触发生成）→ 关键约束 3 条 + 三态切换表\n\n"
                "三件套到这里齐了。本轮收束：4 条 current_understanding / 3 confirmed / 3 pending / 2 conflict / 4 mvp。"
                "剩余主要风险：音频 / 语音输入一期要不要做还没拍板——建议下一轮先把这条收掉。"
                "如果有调整指方向就行，我直接改对应的栏或重画对应的图。"
            ),
            [],
        ),
    ]

    # Insert with explicit, monotonically increasing timestamps. SQLite's
    # `datetime()` cast strips fractional seconds, so back-to-back inserts in
    # the same wall-clock second would have unstable ordering. Spacing by 1
    # minute makes the demo conversation read like a 15-minute session and
    # guarantees stable sort.
    base = datetime(2026, 4, 27, 9, 0, 0, tzinfo=ZoneInfo(catalog.settings.default_timezone))
    with connection_scope(catalog.settings) as connection:
        for idx, (role, content, refs) in enumerate(messages):
            ts = (base + timedelta(minutes=idx)).isoformat()
            mid = f"msg-{uuid.uuid4().hex[:10]}"
            connection.execute(
                """
                INSERT INTO messages (id, project_id, role, content, source_refs_json, created_at, stream_group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    SEED_PROJECT_ID,
                    role,
                    content,
                    json.dumps(refs, ensure_ascii=False),
                    ts,
                    "seed-thread",
                ),
            )
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (
                (base + timedelta(minutes=len(messages))).isoformat(),
                SEED_PROJECT_ID,
            ),
        )


def _seed_chat_images(settings: AppSettings) -> None:
    target_root = settings.projects_dir / SEED_PROJECT_ID / "chat-images"
    target_root.mkdir(parents=True, exist_ok=True)
    for source_png in sorted(CHAT_IMAGES_SOURCE_DIR.glob("*.png")):
        slug = source_png.stem
        target_dir = target_root / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_png, target_dir / "image.png")


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
          <span class="tag">产品自我分析</span>
          <span class="tag">需求转译台 MVP</span>
          <span class="tag">seed 演示稿</span>
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
    inner = """
        <style>
          /* === Interactive page solution prototype === */
          .proto-app { background: #f5f7fb; border-radius: 20px; border: 1px solid #e0e6ee; overflow: hidden; margin-top: 14px; }
          .proto-topbar { display: flex; align-items: center; gap: 18px; padding: 12px 18px; background: white; border-bottom: 1px solid #e6ebf2; }
          .proto-brand { font-weight: 600; color: #2c425a; font-size: 14px; }
          .proto-tabs { display: flex; gap: 2px; background: #eef2f7; border-radius: 999px; padding: 3px; }
          .proto-tabs button { background: transparent; border: 0; padding: 7px 16px; border-radius: 999px; font-size: 12.5px; color: #6b7689; cursor: pointer; transition: all 0.18s; font-family: inherit; }
          .proto-tabs button:hover { color: #2c425a; }
          .proto-tabs button.active { background: white; color: #17476f; box-shadow: 0 1px 4px rgba(40,55,80,0.08); }
          .proto-spacer { flex: 1; }
          .proto-actions { display: flex; gap: 8px; }
          .proto-btn { background: #17476f; color: white; border: 0; padding: 8px 14px; border-radius: 8px; font-size: 12px; cursor: pointer; font-family: inherit; transition: all 0.15s; }
          .proto-btn:hover { background: #1a567d; }
          .proto-btn.ghost { background: transparent; color: #17476f; border: 1px solid #c7d4e2; }
          .proto-btn.ghost:hover { background: #eaf1f8; }

          .proto-page { display: none; padding: 18px; min-height: 480px; }
          .proto-page.active { display: block; }

          /* Home page */
          .home-hero { background: linear-gradient(135deg, #fff 0%, #f4eee0 100%); border: 1px solid #ece4d4; border-radius: 16px; padding: 22px 24px; }
          .home-hero h2 { margin: 0 0 6px; font-size: 22px; color: #2c425a; }
          .home-hero p { margin: 0 0 12px; color: #6b7689; font-size: 13px; line-height: 1.6; }
          .home-seed { background: white; border: 2px solid #c7d4e2; border-radius: 14px; padding: 16px 18px; margin-top: 14px; cursor: pointer; transition: all 0.18s; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
          .home-seed:hover { border-color: #17476f; transform: translateY(-1px); box-shadow: 0 8px 20px rgba(40,55,80,0.08); }
          .home-seed strong { display: block; font-size: 15px; color: #2c425a; }
          .home-seed small { color: #6b7689; font-size: 12px; }
          .home-seed-arrow { color: #17476f; font-size: 18px; }
          .home-list { margin-top: 16px; display: grid; gap: 8px; }
          .home-list-row { padding: 12px 14px; background: white; border: 1px solid #e6ebf2; border-radius: 10px; display: flex; align-items: center; justify-content: space-between; font-size: 12.5px; color: #2c425a; transition: all 0.15s; }
          .home-list-row:hover { border-color: #c7d4e2; background: #f9fbfd; }
          .home-list-row .meta { color: #94a0b1; font-size: 11px; font-family: ui-monospace, monospace; }

          /* Workbench page */
          .ws-overview { display: grid; grid-template-columns: 0.85fr 1.55fr 0.7fr; gap: 14px; padding: 16px; background: #faf7f2; border-radius: 16px; border: 1px solid #ece4d4; }
          .ws-col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
          .ws-col-title { font-size: 12.5px; font-weight: 600; color: #2c425a; padding: 4px 4px 7px; border-bottom: 2px solid #2c425a; display: flex; align-items: center; justify-content: space-between; }
          .ws-col-title small { color: #6b7689; font-weight: 400; font-family: ui-monospace, monospace; font-size: 10.5px; }
          .ws-col-title .count { background: #2c425a; color: white; font-size: 10px; padding: 1px 7px; border-radius: 999px; font-weight: 500; }

          .ws-file { display: grid; grid-template-columns: 36px 1fr auto; align-items: center; gap: 9px; padding: 8px 9px; background: white; border-radius: 10px; border: 1px solid #ece8e0; cursor: pointer; transition: all 0.15s; }
          .ws-file:hover { border-color: #c5b89a; transform: translateX(2px); box-shadow: 0 3px 10px rgba(80,60,30,0.06); }
          .ws-file-icon { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 10.5px; color: white; }
          .ws-file-icon.md1 { background: #e89384; }
          .ws-file-icon.txt1 { background: #6da6cd; }
          .ws-file-icon.pdf { background: #de5454; }
          .ws-file-icon.md2 { background: #d8a57d; }
          .ws-file-icon.txt2 { background: #b9b6ae; }
          .ws-file-meta { min-width: 0; }
          .ws-file-meta strong { font-size: 12px; display: block; color: #2c425a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
          .ws-file-meta small { font-size: 10px; color: #94a0b1; }
          .ws-file-pill { font-size: 9px; padding: 2px 6px; background: #d4ebd9; color: #2d6e3a; border-radius: 4px; font-weight: 600; white-space: nowrap; }

          .ws-chat { display: flex; flex-direction: column; gap: 11px; max-height: 460px; overflow-y: auto; padding-right: 4px; }
          .ws-msg { display: flex; gap: 8px; align-items: flex-start; }
          .ws-msg.user { justify-content: flex-end; }
          .ws-bubble { padding: 9px 12px; border-radius: 12px; font-size: 12px; line-height: 1.55; color: #2c425a; max-width: 78%; }
          .ws-bubble.user { background: #e7eaef; border-bottom-right-radius: 4px; }
          .ws-bubble.asst { background: white; border: 1px solid #e7eaef; border-bottom-left-radius: 4px; }
          .ws-avatar { width: 26px; height: 26px; border-radius: 999px; display: flex; align-items: center; justify-content: center; font-size: 10px; color: white; flex-shrink: 0; }
          .ws-avatar.u { background: #b8b4ad; }
          .ws-avatar.a { background: #2c425a; }
          .ws-refs { display: flex; gap: 5px; margin-top: 7px; flex-wrap: wrap; }
          .ws-ref-chip { font-size: 9px; padding: 2px 7px; background: #fde1d6; color: #b85a3e; border-radius: 5px; cursor: pointer; transition: all 0.15s; }
          .ws-ref-chip:hover { background: #fcd1c1; }
          .ws-input { margin-top: 4px; padding: 9px 12px; background: white; border: 1px solid #d6dde8; border-radius: 10px; display: flex; align-items: center; gap: 9px; }
          .ws-input input { flex: 1; border: 0; outline: 0; font-size: 12px; color: #2c425a; background: transparent; font-family: inherit; }
          .ws-input button { background: #17476f; color: white; border: 0; padding: 5px 12px; border-radius: 7px; font-size: 11.5px; cursor: pointer; }

          .ws-sed { display: flex; flex-direction: column; gap: 7px; }
          .ws-sed-row { display: grid; grid-template-columns: 4px 26px 1fr auto; gap: 9px; align-items: center; padding: 9px 9px 9px 0; background: white; border-radius: 7px; cursor: pointer; transition: all 0.15s; overflow: hidden; }
          .ws-sed-row:hover { transform: translateX(-2px); box-shadow: 0 3px 10px rgba(80,60,30,0.06); }
          .ws-sed-row .a { width: 4px; height: 24px; border-radius: 0 2px 2px 0; }
          .ws-sed-row .ic { width: 24px; height: 24px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }
          .ws-sed-row .lbl { font-size: 12.5px; color: #2c425a; font-weight: 500; }
          .ws-sed-row .cnt { font-size: 11px; color: #94a0b1; font-family: ui-monospace, monospace; padding-right: 8px; }

          .ws-triple { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 14px; padding: 14px; background: #faf7f2; border-radius: 16px; border: 1px solid #ece4d4; }
          .ws-tcard { background: white; border-radius: 11px; padding: 12px 14px; border: 1px solid #ece8e0; cursor: pointer; transition: all 0.18s; display: grid; gap: 9px; }
          .ws-tcard:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(80,60,30,0.08); border-color: #c5b89a; }
          .ws-tcard-head { display: flex; align-items: center; gap: 8px; }
          .ws-tcard-head .ic { width: 22px; height: 22px; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: white; font-size: 10px; font-weight: 700; }
          .ws-tcard-head .ic.doc { background: #5ea874; }
          .ws-tcard-head .ic.page { background: #5ea874; }
          .ws-tcard-head .ic.flow { background: #8c75b8; }
          .ws-tcard-head strong { font-size: 12.5px; color: #2c425a; }
          .ws-tcard-head small { font-size: 10px; color: #94a0b1; margin-left: auto; font-family: ui-monospace, monospace; }
          .ws-tcard-prev { background: #faf7f2; border-radius: 7px; height: 64px; padding: 8px; }
          .ws-tcard-prev.doc { display: flex; flex-direction: column; gap: 4px; }
          .ws-tcard-prev.doc div:first-child { height: 6px; width: 60%; background: #c4ccd8; border-radius: 2px; }
          .ws-tcard-prev.doc div { height: 4px; background: #e0e4ec; border-radius: 2px; }
          .ws-tcard-prev.page { display: grid; grid-template-columns: 0.7fr 1.5fr 0.5fr; gap: 4px; }
          .ws-tcard-prev.page > div { background: #d6dde8; border-radius: 3px; }
          .ws-tcard-prev.page > .pp-c { background: #c4d0e0; }
          .ws-tcard-prev.flow { display: flex; align-items: center; justify-content: space-around; gap: 3px; }
          .ws-tcard-prev.flow .ph { width: 22px; height: 46px; background: white; border: 1.5px solid #c5b8d8; border-radius: 4px; }
          .ws-tcard-prev.flow .arr { color: #8c75b8; font-size: 10px; font-weight: 700; }

          /* Modal */
          .proto-overlay { display: none; position: fixed; inset: 0; background: rgba(20,30,45,0.45); z-index: 100; align-items: center; justify-content: center; padding: 30px; backdrop-filter: blur(2px); }
          .proto-overlay.open { display: flex; }
          .proto-modal { background: white; border-radius: 14px; max-width: 640px; width: 100%; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(20,30,45,0.3); }
          .proto-modal-head { padding: 14px 18px; border-bottom: 1px solid #e6ebf2; display: flex; align-items: center; justify-content: space-between; }
          .proto-modal-head strong { font-size: 14px; color: #2c425a; }
          .proto-modal-head small { color: #94a0b1; font-size: 11px; margin-left: 10px; }
          .proto-modal-close { background: transparent; border: 0; cursor: pointer; padding: 4px 8px; border-radius: 6px; color: #6b7689; font-size: 16px; }
          .proto-modal-close:hover { background: #f0f4f9; color: #2c425a; }
          .proto-modal-body { padding: 18px; overflow-y: auto; font-size: 13px; line-height: 1.7; color: #2c425a; }
          .proto-modal-body pre { background: #faf7f2; padding: 12px 14px; border-radius: 8px; font-family: ui-monospace, monospace; font-size: 12px; line-height: 1.65; white-space: pre-wrap; margin: 0; color: #2c425a; }

          /* Drawer */
          .proto-drawer { display: none; position: fixed; top: 0; right: 0; bottom: 0; width: 380px; max-width: 90vw; background: white; box-shadow: -10px 0 30px rgba(20,30,45,0.18); z-index: 100; flex-direction: column; }
          .proto-drawer.open { display: flex; }
          .proto-drawer-head { padding: 16px 18px; border-bottom: 1px solid #e6ebf2; }
          .proto-drawer-head .ribbon { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; margin-bottom: 6px; }
          .proto-drawer-head h3 { margin: 0; font-size: 15px; color: #2c425a; }
          .proto-drawer-head p { margin: 4px 0 0; font-size: 11.5px; color: #6b7689; font-style: italic; }
          .proto-drawer-body { padding: 14px 18px 18px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 10px; }
          .proto-drawer-item { padding: 10px 12px; background: #f9fbfd; border: 1px solid #e6ebf2; border-radius: 9px; }
          .proto-drawer-item strong { display: block; font-size: 12.5px; color: #2c425a; margin-bottom: 4px; }
          .proto-drawer-item p { margin: 0; font-size: 11.5px; color: #6b7689; line-height: 1.55; }
          .proto-drawer-close { position: absolute; top: 14px; right: 14px; background: transparent; border: 0; cursor: pointer; padding: 4px 8px; border-radius: 6px; color: #6b7689; font-size: 16px; }
          .proto-drawer-close:hover { background: #f0f4f9; color: #2c425a; }

          /* Artifact preview page */
          .art-tabs { display: flex; gap: 8px; margin-bottom: 14px; border-bottom: 1px solid #e6ebf2; padding-bottom: 0; }
          .art-tab { background: transparent; border: 0; padding: 9px 16px; font-size: 12.5px; color: #6b7689; cursor: pointer; border-bottom: 2px solid transparent; font-family: inherit; transition: all 0.15s; }
          .art-tab:hover { color: #2c425a; }
          .art-tab.active { color: #17476f; border-bottom-color: #17476f; font-weight: 500; }
          .art-pane { display: none; }
          .art-pane.active { display: block; }
          .art-pane-doc { background: white; border: 1px solid #e6ebf2; border-radius: 12px; padding: 22px 26px; min-height: 360px; }
          .art-pane-doc h3 { font-size: 17px; margin: 0 0 10px; color: #2c425a; }
          .art-pane-doc h4 { font-size: 13px; margin: 16px 0 8px; color: #2c425a; }
          .art-pane-doc p { font-size: 12.5px; line-height: 1.7; color: #2c425a; margin: 0 0 8px; }
          .art-pane-doc ul { font-size: 12.5px; line-height: 1.7; color: #2c425a; margin: 0 0 10px; padding-left: 22px; }
          .art-pane-page, .art-pane-flow { background: #faf7f2; border: 1px solid #ece4d4; border-radius: 12px; padding: 16px; min-height: 320px; display: flex; align-items: center; justify-content: center; color: #94a0b1; font-size: 13px; flex-direction: column; gap: 10px; }
          .art-pane-page .iframe-mock, .art-pane-flow .iframe-mock { width: 100%; height: 280px; background: white; border: 1px dashed #c7d4e2; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #94a0b1; font-size: 13px; }

          .proto-toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(120%); background: #2c425a; color: white; padding: 10px 18px; border-radius: 999px; font-size: 12.5px; box-shadow: 0 8px 24px rgba(20,30,45,0.25); transition: transform 0.25s; z-index: 200; }
          .proto-toast.show { transform: translateX(-50%) translateY(0); }

          @media (max-width: 980px) {
            .ws-overview { grid-template-columns: 1fr; }
            .ws-triple { grid-template-columns: 1fr; }
          }
        </style>

        <div class="proto-app">
          <nav class="proto-topbar">
            <div class="proto-brand">客户需求转译台</div>
            <div class="proto-tabs">
              <button data-page="home">项目首页</button>
              <button data-page="workbench" class="active">工作台</button>
              <button data-page="artifact">交付物预览</button>
            </div>
            <div class="proto-spacer"></div>
            <div class="proto-actions">
              <button class="proto-btn ghost" onclick="protoToast('运行状态：所有服务 ready')">运行状态</button>
              <button class="proto-btn" onclick="protoToast('打开新建项目弹窗')">+ 新建项目</button>
            </div>
          </nav>

          <!-- HOME -->
          <section class="proto-page" data-page="home">
            <div class="home-hero">
              <h2>把客户的散乱诉求，转成可以继续推进的结果</h2>
              <p>左侧资料 / 中间聊天 / 右侧 7 类沉淀，每一轮分析三栏同步推进。一期固定输出三件套交付物。</p>
              <div class="home-seed" onclick="protoNav('workbench')">
                <div>
                  <strong>客户需求转译台 · 产品自我分析</strong>
                  <small>seed 演示项目 · 5 份原始材料 · 18 轮分析 · 3 件套已生成</small>
                </div>
                <span class="home-seed-arrow">→</span>
              </div>
            </div>
            <div class="home-list">
              <div class="home-list-row"><span>智慧园区平台需求转译</span><span class="meta">2026-04-22 · 进行中</span></div>
              <div class="home-list-row"><span>政府数据中台前期分析</span><span class="meta">2026-04-18 · 已收稿</span></div>
              <div class="home-list-row"><span>文化文投 OPC 需求转译</span><span class="meta">2026-04-12 · 已收稿</span></div>
            </div>
          </section>

          <!-- WORKBENCH -->
          <section class="proto-page active" data-page="workbench">
            <div class="ws-overview">
              <div class="ws-col">
                <div class="ws-col-title"><span>资料区 <small>/ Sources</small></span><span class="count">5 已索引</span></div>
                <div class="ws-file" onclick="protoOpenFile('product')"><span class="ws-file-icon md1">M&#x2193;</span><div class="ws-file-meta"><strong>产品需求.md</strong><small>Markdown</small></div><span class="ws-file-pill">已索引</span></div>
                <div class="ws-file" onclick="protoOpenFile('research')"><span class="ws-file-icon txt1">TXT</span><div class="ws-file-meta"><strong>用户调研.txt</strong><small>Text</small></div><span class="ws-file-pill">已索引</span></div>
                <div class="ws-file" onclick="protoOpenFile('analysis')"><span class="ws-file-icon pdf">PDF</span><div class="ws-file-meta"><strong>需求分析.pdf</strong><small>PDF</small></div><span class="ws-file-pill">已索引</span></div>
                <div class="ws-file" onclick="protoOpenFile('prd')"><span class="ws-file-icon md2">M&#x2193;</span><div class="ws-file-meta"><strong>PRD_v1.2.md</strong><small>Markdown</small></div><span class="ws-file-pill">已索引</span></div>
                <div class="ws-file" onclick="protoOpenFile('stack')"><span class="ws-file-icon txt2">TXT</span><div class="ws-file-meta"><strong>技术栈.txt</strong><small>Text</small></div><span class="ws-file-pill">已索引</span></div>
              </div>

              <div class="ws-col">
                <div class="ws-col-title"><span>聊天 <small>/ Chat</small></span><span class="count">引用 5 份</span></div>
                <div class="ws-chat">
                  <div class="ws-msg user"><div class="ws-bubble user">我们要做一个支持多端的项目协作平台，核心目标是什么？</div><div class="ws-avatar u">U</div></div>
                  <div class="ws-msg"><div class="ws-avatar a">A</div><div class="ws-bubble asst">核心目标是提升多端协作效率，打通需求、设计、开发、测试到发布的完整流程。<div class="ws-refs"><span class="ws-ref-chip" onclick="protoOpenFile('product')">产品需求.md</span><span class="ws-ref-chip" onclick="protoOpenFile('research')">用户调研.txt</span></div></div></div>
                  <div class="ws-msg user"><div class="ws-bubble user">那权限设计上有什么建议？</div><div class="ws-avatar u">U</div></div>
                  <div class="ws-msg"><div class="ws-avatar a">A</div><div class="ws-bubble asst">建议采用基于角色的权限模型（RBAC），并支持项目级别的细粒度权限配置。<div class="ws-refs"><span class="ws-ref-chip" onclick="protoOpenFile('prd')">PRD_v1.2.md</span><span class="ws-ref-chip" onclick="protoOpenFile('stack')">技术栈.txt</span></div></div></div>
                </div>
                <div class="ws-input"><input placeholder="继续补充业务背景、目标或限制条件…" /><button onclick="protoToast('消息已发送（演示）')">发送</button></div>
              </div>

              <div class="ws-col">
                <div class="ws-col-title"><span>沉淀 <small>/ Sediment</small></span><span class="count">16 条</span></div>
                <div class="ws-sed">
                  <div class="ws-sed-row" onclick="protoOpenSed('understanding')"><span class="a" style="background:#5b8fc7;"></span><span class="ic" style="background:#fef3c7;color:#b87f2c;">&#9786;</span><span class="lbl">当前理解</span><span class="cnt">4</span></div>
                  <div class="ws-sed-row" onclick="protoOpenSed('pending')"><span class="a" style="background:#d49d4a;"></span><span class="ic" style="background:#faecd0;color:#b87f2c;">?</span><span class="lbl">待确认</span><span class="cnt">3</span></div>
                  <div class="ws-sed-row" onclick="protoOpenSed('confirmed')"><span class="a" style="background:#5ea874;"></span><span class="ic" style="background:#ddf0e3;color:#3a7d4f;">&#10003;</span><span class="lbl">已确认</span><span class="cnt">3</span></div>
                  <div class="ws-sed-row" onclick="protoOpenSed('conflict')"><span class="a" style="background:#c46e57;"></span><span class="ic" style="background:#fadfd6;color:#a04f3a;">&#9650;</span><span class="lbl">冲突</span><span class="cnt">2</span></div>
                  <div class="ws-sed-row" onclick="protoOpenSed('mvp')"><span class="a" style="background:#8c75b8;"></span><span class="ic" style="background:#ebe2f5;color:#654e91;">&#9650;</span><span class="lbl">MVP</span><span class="cnt">4</span></div>
                  <div class="ws-sed-row" onclick="protoOpenSed('versions')"><span class="a" style="background:#6b7689;"></span><span class="ic" style="background:#dde2eb;color:#4a5365;">&#9776;</span><span class="lbl">版本快照</span><span class="cnt">1</span></div>
                  <div class="ws-sed-row" onclick="protoOpenSed('artifacts')"><span class="a" style="background:#3f9b8f;"></span><span class="ic" style="background:#d2eae6;color:#2a7269;">&#9776;</span><span class="lbl">交付物</span><span class="cnt">3</span></div>
                </div>
              </div>
            </div>

            <div class="ws-triple">
              <div class="ws-tcard" onclick="protoOpenArtifact('document')">
                <div class="ws-tcard-head"><span class="ic doc">M</span><strong>需求稿</strong><small>document</small></div>
                <div class="ws-tcard-prev doc"><div></div><div></div><div></div><div></div><div></div></div>
              </div>
              <div class="ws-tcard" onclick="protoOpenArtifact('page')">
                <div class="ws-tcard-head"><span class="ic page">&#9636;</span><strong>页面方案</strong><small>page_solution</small></div>
                <div class="ws-tcard-prev page"><div></div><div class="pp-c"></div><div></div></div>
              </div>
              <div class="ws-tcard" onclick="protoOpenArtifact('flow')">
                <div class="ws-tcard-head"><span class="ic flow">&#8599;</span><strong>交互稿</strong><small>interaction_flow</small></div>
                <div class="ws-tcard-prev flow"><div class="ph"></div><span class="arr">&#8594;</span><div class="ph"></div><span class="arr">&#8594;</span><div class="ph"></div><span class="arr">&#8594;</span><div class="ph"></div></div>
              </div>
            </div>
          </section>

          <!-- ARTIFACT PREVIEW -->
          <section class="proto-page" data-page="artifact">
            <div class="art-tabs">
              <button class="art-tab active" data-art="document">需求稿</button>
              <button class="art-tab" data-art="page">页面方案</button>
              <button class="art-tab" data-art="flow">交互稿</button>
            </div>
            <div class="art-pane active" data-art="document">
              <div class="art-pane-doc">
                <h3>客户需求转译台 · MVP 需求稿</h3>
                <h4>一、项目目标</h4>
                <p>把客户散乱诉求转成可继续推进的结构化结果。</p>
                <h4>二、真实需求</h4>
                <ul><li>RN-1：接住混杂输入，不要求先整理</li><li>RN-2：分析过程同步沉淀</li><li>RN-3：可看到「分析中间态」</li><li>RN-4：交付物至少能继续推进讨论</li><li>RN-5：agent 主动引导</li></ul>
                <h4>三、范围边界</h4>
                <p><strong>IN：</strong>三栏工作台 / 7 类沉淀 / 三件套交付物 / 多模态消息（文本+图片）</p>
                <p><strong>OUT：</strong>多人实时协同 / 权限体系 / 插件市场 / 自动改账</p>
                <p><strong>GREY：</strong>音频是否一期 / 客户方是否直接用 / 原型深度</p>
              </div>
            </div>
            <div class="art-pane" data-art="page">
              <div class="art-pane-page">
                <p>这就是你正在看的页面方案 HTML 本身——切回「工作台」tab 继续探索。</p>
                <div class="iframe-mock">[ page_solution.html iframe 区 ]</div>
              </div>
            </div>
            <div class="art-pane" data-art="flow">
              <div class="art-pane-flow">
                <p>切到「交互稿」预览：interaction_flow.html 是另一份独立的可交互产物。</p>
                <div class="iframe-mock">[ interaction_flow.html iframe 区 ]</div>
              </div>
            </div>
          </section>
        </div>

        <!-- Modal: file preview -->
        <div class="proto-overlay" id="protoModal" onclick="if(event.target===this)protoCloseModal()">
          <div class="proto-modal">
            <div class="proto-modal-head">
              <div><strong id="protoModalTitle">文件名</strong><small id="protoModalKind">Markdown</small></div>
              <button class="proto-modal-close" onclick="protoCloseModal()">&times;</button>
            </div>
            <div class="proto-modal-body"><pre id="protoModalBody"></pre></div>
          </div>
        </div>

        <!-- Drawer: sediment detail -->
        <div class="proto-drawer" id="protoDrawer">
          <button class="proto-drawer-close" onclick="protoCloseDrawer()">&times;</button>
          <div class="proto-drawer-head">
            <span class="ribbon" id="protoDrawerRibbon"></span>
            <h3 id="protoDrawerTitle">分类详情</h3>
            <p id="protoDrawerTrigger"></p>
          </div>
          <div class="proto-drawer-body" id="protoDrawerBody"></div>
        </div>

        <div class="proto-toast" id="protoToast"></div>

        <script>
          (function () {
            // --- Tab navigation ---
            const tabs = document.querySelectorAll('.proto-tabs button');
            tabs.forEach(btn => btn.addEventListener('click', () => protoNav(btn.dataset.page)));

            window.protoNav = function (page) {
              document.querySelectorAll('.proto-tabs button').forEach(b => b.classList.toggle('active', b.dataset.page === page));
              document.querySelectorAll('.proto-page').forEach(p => p.classList.toggle('active', p.dataset.page === page));
            };

            // --- File preview modal ---
            const fileData = {
              product: {name:'产品需求.md', kind:'Markdown', body:'# 产品需求\\n\\n## 1. 背景\\n做一个支持多端的项目协作平台，目标客户是中小团队。\\n\\n## 2. 核心目标\\n打通需求、设计、开发、测试到发布的完整流程，确保跨端信息可见同步。\\n\\n## 3. 一期范围\\n- 项目空间 + 文档模块\\n- Web + 移动端 + 桌面 PWA\\n- 集成 Slack / 飞书通知\\n\\n## 4. 不在一期范围\\n- 自动化工作流编排\\n- 第三方插件市场'},
              research: {name:'用户调研.txt', kind:'Text', body:'用户调研访谈节选\\n========================\\n\\n[A 公司 PM]: 「我们最痛的是切换工具——需求在 Notion，设计在 Figma，进度在 Jira，每个 PM 一天要切 5 个工具。」\\n\\n[B 公司设计师]: 「希望评论能跟设计稿对齐，不是另开一个系统。」\\n\\n[C 公司技术负责人]: 「权限要灵活，但不要做成 SAP 那种迷宫。」\\n\\n关键词: 单一工作台、上下文聚合、轻量权限'},
              analysis: {name:'需求分析.pdf', kind:'PDF', body:'[需求分析报告 · 第 1-3 页摘要]\\n\\n第一节：市场格局\\n- 通用 SaaS（Notion/Coda）：上手低，但深度不足\\n- 垂直工具（Jira/Linear）：深度够，跨工具协同弱\\n- 我们的位置：中小团队的「单一上下文协作台」\\n\\n第二节：用户画像\\n- 主用户：5-50 人团队的 PM / 设计师 / 工程师\\n- 关键场景：从想法到上线 4-12 周的项目周期\\n\\n第三节：竞品仪表盘对比\\n（图）'},
              prd: {name:'PRD_v1.2.md', kind:'Markdown', body:'# PRD v1.2\\n\\n## 权限模型\\n采用 RBAC（基于角色的权限模型）：\\n- 系统级角色：Owner / Admin / Member / Guest\\n- 项目级角色：项目所有者 / 项目编辑 / 项目阅读\\n- 资源级颗粒度：文档 / 评论 / 附件可单独控制\\n\\n## 关键决策\\n- v1.0 不开放自定义角色，避免迷宫\\n- v1.2 开始支持项目级权限重写'},
              stack: {name:'技术栈.txt', kind:'Text', body:'前端: React 18 + TypeScript + Vite\\n后端: FastAPI (Python 3.11) + PostgreSQL\\n实时: WebSocket (FastAPI native) + Redis pubsub\\n搜索: Meilisearch\\n部署: 自托管 Docker Compose（一期）+ Hetzner / 国内阿里云\\n监控: OpenTelemetry → Grafana Cloud'},
            };
            window.protoOpenFile = function (key) {
              const f = fileData[key]; if (!f) return;
              document.getElementById('protoModalTitle').textContent = f.name;
              document.getElementById('protoModalKind').textContent = f.kind;
              document.getElementById('protoModalBody').textContent = f.body;
              document.getElementById('protoModal').classList.add('open');
            };
            window.protoCloseModal = function () {
              document.getElementById('protoModal').classList.remove('open');
            };

            // --- Sediment drawer ---
            const sedData = {
              understanding: {title:'当前理解', slug:'current_understanding', color:'#5b8fc7', bg:'#e8f0f9', trigger:'从资料中提炼的阶段性理解', items:[
                {t:'需求转译台是把模糊诉求转成可交付物的工作台', b:'不是通用聊天，而是一个左资料/中聊天/右沉淀的三栏分析台'},
                {t:'产品形态是三栏工作台', b:'每一轮分析三栏同步推进'},
                {t:'沉淀按类落盘，不靠 LLM 总结合并', b:'分类持久化是核心承诺'},
                {t:'主要使用人是售前 / 咨询 / PM 三段角色', b:'客户方是否直接用还没定'},
              ]},
              pending: {title:'待确认', slug:'pending_items', color:'#d49d4a', bg:'#faecd0', trigger:'信息不足或口径未统一，需追问', items:[
                {t:'音频/语音输入一期是否纳入', b:'群聊和补充说明口径不一致'},
                {t:'客户方是否直接使用这个工作台', b:'影响交互复杂度与权限边界'},
                {t:'输出物是否包含页面草图与原型方向', b:'补充说明 §4 给了两种想法'},
              ]},
              confirmed: {title:'已确认', slug:'confirmed_items', color:'#5ea874', bg:'#ddf0e3', trigger:'当在会议、文档或客户回复中明确', items:[
                {t:'一期不做大平台，只做需求转译这一个场景', b:'0328 纪要明确'},
                {t:'第一版不做权限', b:'群聊倾向不做'},
                {t:'输出至少要能继续推进讨论', b:'补充说明 §4 + 0328 纪要 §3'},
              ]},
              conflict: {title:'冲突', slug:'conflict_items', color:'#c46e57', bg:'#fadfd6', trigger:'不同来源出现明显矛盾', items:[
                {t:'群聊 vs 补充说明对「音频」口径不一致', b:'3.26 群聊倾向不做，补充说明把「语音」放在输入清单'},
                {t:'「想做轻」vs「想给原型方向」的张力', b:'补充说明 §1 vs §4'},
              ]},
              mvp: {title:'MVP', slug:'mvp_items', color:'#8c75b8', bg:'#ebe2f5', trigger:'为最小可交付版本固定范围', items:[
                {t:'三栏工作台基础', b:'资料上传 + 聊天分析 + 沉淀同步'},
                {t:'7 类状态沉淀按类落盘', b:'独立维护，可单独追加或撤回'},
                {t:'三件套交付物 + 版本快照', b:'document + page_solution + interaction_flow'},
                {t:'多模态消息（文本 + 图片）', b:'语音 / 视频先不进 MVP'},
              ]},
              versions: {title:'版本快照', slug:'versions', color:'#6b7689', bg:'#dde2eb', trigger:'对当前收敛状态做冻结记录', items:[
                {t:'v1 — MVP 框架已收敛', b:'已落 4 条 understanding / 3 条 confirmed / 4 条 mvp'},
              ]},
              artifacts: {title:'交付物', slug:'artifacts', color:'#3f9b8f', bg:'#d2eae6', trigger:'最终输出给团队或客户的内容', items:[
                {t:'需求分析与 MVP 文档稿', b:'document · markdown · seed_ready'},
                {t:'三栏工作台页面方案', b:'page_solution · HTML · seed_ready'},
                {t:'端到端转译交互稿', b:'interaction_flow · HTML · seed_ready'},
              ]},
            };
            window.protoOpenSed = function (key) {
              const s = sedData[key]; if (!s) return;
              const ribbon = document.getElementById('protoDrawerRibbon');
              ribbon.textContent = s.slug;
              ribbon.style.background = s.bg;
              ribbon.style.color = s.color;
              document.getElementById('protoDrawerTitle').textContent = s.title;
              document.getElementById('protoDrawerTrigger').textContent = s.trigger;
              const body = document.getElementById('protoDrawerBody');
              body.innerHTML = s.items.map(it => '<div class="proto-drawer-item"><strong>' + it.t + '</strong><p>' + it.b + '</p></div>').join('');
              document.getElementById('protoDrawer').classList.add('open');
            };
            window.protoCloseDrawer = function () {
              document.getElementById('protoDrawer').classList.remove('open');
            };

            // --- Artifact preview tabs ---
            window.protoOpenArtifact = function (key) {
              protoNav('artifact');
              document.querySelectorAll('.art-tab').forEach(t => t.classList.toggle('active', t.dataset.art === key));
              document.querySelectorAll('.art-pane').forEach(p => p.classList.toggle('active', p.dataset.art === key));
            };
            document.querySelectorAll('.art-tab').forEach(t => {
              t.addEventListener('click', () => protoOpenArtifact(t.dataset.art));
            });

            // --- Toast ---
            window.protoToast = function (msg) {
              const el = document.getElementById('protoToast');
              el.textContent = msg;
              el.classList.add('show');
              clearTimeout(window.__protoToastT);
              window.__protoToastT = setTimeout(() => el.classList.remove('show'), 1800);
            };

            // ESC closes modal/drawer
            document.addEventListener('keydown', e => {
              if (e.key === 'Escape') { protoCloseModal(); protoCloseDrawer(); }
            });
          })();
        </script>
        """
    html = _artifact_shell(
        "客户需求转译台 · 三栏工作台页面方案",
        "Page Solution",
        "可交互原型：3 个页面（项目首页 / 工作台 / 交付物预览）+ 文件预览 modal + 沉淀分类抽屉 + 三件套切换。点击试试。",
        inner,
    )
    artifact_dir = settings.projects_dir / SEED_PROJECT_ID / "artifacts" / "page_solution"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def _write_interaction_flow_html(settings: AppSettings) -> Path:
    inner = """
        <style>
          /* === Interactive 5-step walkthrough === */
          .if-app { background: #f5f7fb; border-radius: 20px; border: 1px solid #e0e6ee; padding: 18px; margin-top: 14px; }
          .if-header { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; padding: 12px 16px; background: white; border-radius: 12px; border: 1px solid #e6ebf2; }
          .if-step-num { font-family: ui-monospace, monospace; font-size: 12px; color: #6b7689; }
          .if-step-num strong { color: #17476f; font-size: 14px; }
          .if-state-badge { padding: 4px 12px; border-radius: 999px; font-size: 11.5px; font-weight: 600; transition: all 0.25s; }
          .if-state-badge.discuss { background: #e8f0f9; color: #2f5b8c; }
          .if-state-badge.confirm { background: #ddf0e3; color: #2d6638; }
          .if-state-badge.execute { background: #faecd0; color: #8a5e1a; }
          .if-spacer { flex: 1; }
          .if-controls { display: flex; gap: 6px; }
          .if-btn { background: #17476f; color: white; border: 0; padding: 8px 16px; border-radius: 8px; font-size: 12.5px; cursor: pointer; font-family: inherit; transition: all 0.15s; }
          .if-btn:hover:not(:disabled) { background: #1a567d; }
          .if-btn:disabled { background: #c7d4e2; cursor: not-allowed; }
          .if-btn.ghost { background: transparent; color: #17476f; border: 1px solid #c7d4e2; }
          .if-btn.ghost:hover:not(:disabled) { background: #eaf1f8; }
          .if-btn.ghost:disabled { color: #c7d4e2; cursor: not-allowed; }

          .if-rail { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin-bottom: 16px; }
          .if-rail-step { padding: 10px 8px; border-radius: 10px; background: white; border: 1px solid #e6ebf2; text-align: center; font-size: 11.5px; color: #6b7689; cursor: pointer; transition: all 0.18s; user-select: none; }
          .if-rail-step:hover { color: #2c425a; border-color: #c7d4e2; }
          .if-rail-step.active { background: #17476f; color: white; border-color: #17476f; box-shadow: 0 4px 12px rgba(23,71,111,0.2); }
          .if-rail-step.done { background: #ddf0e3; color: #2d6638; border-color: #b9d8be; }
          .if-rail-step .num { display: block; font-family: ui-monospace, monospace; font-size: 10px; opacity: 0.7; margin-bottom: 2px; }
          .if-rail-step strong { font-size: 12px; }

          /* Mini workbench scene */
          .if-scene { background: white; border-radius: 14px; border: 1px solid #e6ebf2; padding: 14px; min-height: 340px; }
          .if-mini { display: grid; grid-template-columns: 0.85fr 1.5fr 0.85fr; gap: 10px; }
          .if-mini-col { background: #faf7f2; border-radius: 10px; border: 1px solid #ece4d4; padding: 10px; min-height: 280px; display: flex; flex-direction: column; gap: 8px; }
          .if-mini-col-title { font-size: 11.5px; font-weight: 600; color: #2c425a; padding-bottom: 6px; border-bottom: 1.5px solid #2c425a; display: flex; justify-content: space-between; align-items: center; }
          .if-mini-col-title small { font-size: 10px; color: #6b7689; font-family: ui-monospace, monospace; }
          .if-mini-col-title .badge { background: #2c425a; color: white; font-size: 9px; padding: 1px 6px; border-radius: 999px; }

          .if-mini-file { display: grid; grid-template-columns: 26px 1fr auto; gap: 6px; align-items: center; padding: 6px 7px; background: white; border-radius: 7px; border: 1px solid #ece8e0; font-size: 11px; opacity: 0; transform: translateX(-8px); transition: all 0.4s; }
          .if-mini-file.show { opacity: 1; transform: none; }
          .if-mini-file .ic { width: 26px; height: 26px; border-radius: 6px; color: white; font-size: 9px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
          .if-mini-file strong { color: #2c425a; font-size: 11px; }
          .if-mini-file .pill { font-size: 8.5px; padding: 1px 5px; background: #d4ebd9; color: #2d6e3a; border-radius: 4px; font-weight: 600; }

          .if-mini-msg { font-size: 11px; padding: 7px 10px; border-radius: 9px; max-width: 88%; line-height: 1.5; opacity: 0; transform: translateY(6px); transition: all 0.4s; }
          .if-mini-msg.show { opacity: 1; transform: none; }
          .if-mini-msg.user { background: #e7eaef; color: #2c425a; margin-left: auto; border-bottom-right-radius: 3px; }
          .if-mini-msg.asst { background: white; border: 1px solid #e7eaef; color: #2c425a; border-bottom-left-radius: 3px; }
          .if-mini-input { margin-top: auto; padding: 6px 9px; background: white; border: 1px solid #d6dde8; border-radius: 7px; display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: #94a0b1; }
          .if-mini-input.pulse { animation: ifPulse 1.5s ease-in-out infinite; }
          @keyframes ifPulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(23,71,111,0.0); } 50% { box-shadow: 0 0 0 6px rgba(23,71,111,0.12); } }

          .if-mini-sed { display: grid; grid-template-columns: 4px 22px 1fr auto; gap: 7px; align-items: center; padding: 6px 7px 6px 0; background: white; border-radius: 6px; font-size: 11px; transition: all 0.3s; }
          .if-mini-sed.glow { box-shadow: 0 0 0 3px rgba(94,168,116,0.25); transform: translateX(-2px); }
          .if-mini-sed .a { width: 4px; height: 18px; border-radius: 0 2px 2px 0; }
          .if-mini-sed .ic { width: 22px; height: 22px; border-radius: 5px; font-size: 10px; display: flex; align-items: center; justify-content: center; font-weight: 700; }
          .if-mini-sed .lbl { color: #2c425a; }
          .if-mini-sed .cnt { font-size: 10px; color: #94a0b1; font-family: ui-monospace, monospace; padding-right: 6px; transition: all 0.3s; }
          .if-mini-sed .cnt.bumped { color: #2d6638; font-weight: 700; transform: scale(1.3); }

          .if-deliver { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px; padding: 10px; background: #faf7f2; border-radius: 10px; border: 1px solid #ece4d4; }
          .if-dcard { background: white; border-radius: 8px; padding: 8px 10px; border: 1px solid #ece8e0; font-size: 11px; transition: all 0.3s; }
          .if-dcard.ready { border-color: #5ea874; background: #f0f8f2; }
          .if-dcard strong { display: block; color: #2c425a; font-size: 11.5px; margin-bottom: 3px; }
          .if-dcard small { font-size: 9px; color: #94a0b1; font-family: ui-monospace, monospace; }
          .if-dcard .status { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 9.5px; margin-top: 3px; }
          .if-dcard .status.empty { background: #f0f4f9; color: #94a0b1; }
          .if-dcard .status.ready { background: #d4ebd9; color: #2d6638; font-weight: 600; }

          .if-preview { margin-top: 10px; height: 120px; background: white; border: 1.5px dashed #c7d4e2; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #94a0b1; font-size: 12px; transition: all 0.3s; }
          .if-preview.open { border-style: solid; border-color: #5ea874; background: linear-gradient(135deg, #f0f8f2 0%, #fff 100%); color: #2d6638; }

          .if-caption { margin-top: 14px; padding: 14px 18px; background: #fbf3df; border: 1px solid #e9d6a2; border-radius: 12px; }
          .if-caption strong { display: block; font-size: 13px; color: #2c425a; margin-bottom: 4px; }
          .if-caption p { margin: 0; font-size: 12.5px; line-height: 1.65; color: #6b7689; }

          @media (max-width: 980px) {
            .if-mini { grid-template-columns: 1fr; }
            .if-rail { grid-template-columns: repeat(2, 1fr); }
          }
        </style>

        <div class="if-app">
          <div class="if-header">
            <div class="if-step-num">Step <strong id="ifCur">1</strong> / 5</div>
            <span class="if-state-badge discuss" id="ifBadge">讨论态</span>
            <div class="if-spacer"></div>
            <div class="if-controls">
              <button class="if-btn ghost" id="ifPrev" disabled>← 上一步</button>
              <button class="if-btn" id="ifNext">下一步 →</button>
              <button class="if-btn ghost" id="ifReset">↺ 重置</button>
            </div>
          </div>

          <div class="if-rail" id="ifRail">
            <div class="if-rail-step active" data-step="1"><span class="num">01</span><strong>上传资料</strong></div>
            <div class="if-rail-step" data-step="2"><span class="num">02</span><strong>启动对话</strong></div>
            <div class="if-rail-step" data-step="3"><span class="num">03</span><strong>状态沉淀</strong></div>
            <div class="if-rail-step" data-step="4"><span class="num">04</span><strong>触发交付物</strong></div>
            <div class="if-rail-step" data-step="5"><span class="num">05</span><strong>确认收稿</strong></div>
          </div>

          <div class="if-scene">
            <div class="if-mini">
              <div class="if-mini-col">
                <div class="if-mini-col-title"><span>资料区</span><span class="badge" id="ifFileCount">0</span></div>
                <div class="if-mini-file" id="ifFile1"><span class="ic" style="background:#e89384;">M</span><div><strong>项目背景.md</strong></div><span class="pill">已索引</span></div>
                <div class="if-mini-file" id="ifFile2"><span class="ic" style="background:#6da6cd;">TXT</span><div><strong>补充说明.md</strong></div><span class="pill">已索引</span></div>
                <div class="if-mini-file" id="ifFile3"><span class="ic" style="background:#de5454;">PDF</span><div><strong>会议纪要.pdf</strong></div><span class="pill">已索引</span></div>
                <div class="if-mini-file" id="ifFile4"><span class="ic" style="background:#d8a57d;">M</span><div><strong>群聊整理.md</strong></div><span class="pill">已索引</span></div>
                <div class="if-mini-file" id="ifFile5"><span class="ic" style="background:#b9b6ae;">TXT</span><div><strong>材料清单.txt</strong></div><span class="pill">已索引</span></div>
              </div>
              <div class="if-mini-col">
                <div class="if-mini-col-title"><span>聊天</span><span class="badge" id="ifMsgCount">0 轮</span></div>
                <div id="ifChat" style="display:flex;flex-direction:column;gap:6px;"></div>
                <div class="if-mini-input" id="ifInput">输入框…</div>
              </div>
              <div class="if-mini-col">
                <div class="if-mini-col-title"><span>沉淀</span><span class="badge" id="ifSedCount">0</span></div>
                <div class="if-mini-sed" id="ifSed-und"><span class="a" style="background:#5b8fc7;"></span><span class="ic" style="background:#fef3c7;color:#b87f2c;">&#9786;</span><span class="lbl">当前理解</span><span class="cnt">0</span></div>
                <div class="if-mini-sed" id="ifSed-pen"><span class="a" style="background:#d49d4a;"></span><span class="ic" style="background:#faecd0;color:#b87f2c;">?</span><span class="lbl">待确认</span><span class="cnt">0</span></div>
                <div class="if-mini-sed" id="ifSed-con"><span class="a" style="background:#5ea874;"></span><span class="ic" style="background:#ddf0e3;color:#3a7d4f;">&#10003;</span><span class="lbl">已确认</span><span class="cnt">0</span></div>
                <div class="if-mini-sed" id="ifSed-cnf"><span class="a" style="background:#c46e57;"></span><span class="ic" style="background:#fadfd6;color:#a04f3a;">&#9650;</span><span class="lbl">冲突</span><span class="cnt">0</span></div>
                <div class="if-mini-sed" id="ifSed-mvp"><span class="a" style="background:#8c75b8;"></span><span class="ic" style="background:#ebe2f5;color:#654e91;">&#9650;</span><span class="lbl">MVP</span><span class="cnt">0</span></div>
                <div class="if-mini-sed" id="ifSed-ver"><span class="a" style="background:#6b7689;"></span><span class="ic" style="background:#dde2eb;color:#4a5365;">&#9776;</span><span class="lbl">版本快照</span><span class="cnt">0</span></div>
                <div class="if-mini-sed" id="ifSed-art"><span class="a" style="background:#3f9b8f;"></span><span class="ic" style="background:#d2eae6;color:#2a7269;">&#9776;</span><span class="lbl">交付物</span><span class="cnt">0</span></div>
              </div>
            </div>

            <div class="if-deliver">
              <div class="if-dcard" id="ifDoc"><strong>需求稿</strong><small>document</small><br/><span class="status empty">未生成</span></div>
              <div class="if-dcard" id="ifPage"><strong>页面方案</strong><small>page_solution</small><br/><span class="status empty">未生成</span></div>
              <div class="if-dcard" id="ifFlow"><strong>交互稿</strong><small>interaction_flow</small><br/><span class="status empty">未生成</span></div>
            </div>

            <div class="if-preview" id="ifPreview">交付物预览区（执行态后才打开）</div>
          </div>

          <div class="if-caption" id="ifCaption">
            <strong>第 1 步：上传混杂资料</strong>
            <p>把客户给的会议纪要 / 群聊 / 补充说明 / 截图 / PPT 拖到左栏。系统自动标准化与索引，每份资料卡上出现「已索引」徽标。点「下一步 →」推进。</p>
          </div>
        </div>

        <script>
          (function () {
            const stages = [
              {
                step: 1, state: 'discuss', stateLbl: '讨论态',
                title: '第 1 步：上传混杂资料',
                desc: '把客户给的会议纪要 / 群聊 / 补充说明 / 截图 / PPT 拖到左栏。系统自动标准化与索引，每份资料卡上出现「已索引」徽标。点「下一步 →」推进。',
              },
              {
                step: 2, state: 'discuss', stateLbl: '讨论态',
                title: '第 2 步：启动对话分析',
                desc: '输入框提示亮起。一句话告诉 agent 你要它做什么；agent 主动读资料，给一版「我看到了什么」+ 引用具体资料 chip + 提 pending 问你要不要写。这一步还是讨论态，没有写沉淀。',
              },
              {
                step: 3, state: 'confirm', stateLbl: '确认态',
                title: '第 3 步：状态同步沉淀',
                desc: '你说「写吧」「可以」「落」，agent 进入确认态——把本轮要写的内容按类落到右栏 7 类沉淀。计数器 +1，对应分类卡闪烁。版本快照在 MVP 收敛时打。',
              },
              {
                step: 4, state: 'execute', stateLbl: '执行态',
                title: '第 4 步：触发三件套交付物',
                desc: '你明示「来一版需求稿」「再来个页面方案」「出交互稿」，进入执行态。先生图给你确认 → 用户 OK → 才出 HTML。底部三件套卡变 ready，对应分类计数 +1。',
              },
              {
                step: 5, state: 'execute', stateLbl: '执行态',
                title: '第 5 步：确认收稿',
                desc: '点「预览」打开 iframe / markdown 渲染。可切换历史版本。下一轮分析以本版本为基线继续推进。版本快照分区 +1。',
              },
            ];
            let cur = 1;

            function applyStep(s) {
              cur = s;
              document.getElementById('ifCur').textContent = s;

              // Rail
              document.querySelectorAll('.if-rail-step').forEach(r => {
                const n = parseInt(r.dataset.step, 10);
                r.classList.toggle('active', n === s);
                r.classList.toggle('done', n < s);
              });

              // State badge
              const stage = stages[s - 1];
              const badge = document.getElementById('ifBadge');
              badge.textContent = stage.stateLbl;
              badge.className = 'if-state-badge ' + stage.state;

              // Caption
              document.getElementById('ifCaption').innerHTML = '<strong>' + stage.title + '</strong><p>' + stage.desc + '</p>';

              // Buttons
              document.getElementById('ifPrev').disabled = (s === 1);
              document.getElementById('ifNext').disabled = (s === 5);

              // === Scene state ===
              // Files appear in step 1
              const filesShown = s >= 1 ? 5 : 0;
              for (let i = 1; i <= 5; i++) {
                document.getElementById('ifFile' + i).classList.toggle('show', i <= filesShown);
              }
              document.getElementById('ifFileCount').textContent = filesShown + ' 已索引';

              // Chat messages in step 2
              const chat = document.getElementById('ifChat');
              if (s >= 2) {
                chat.innerHTML = '<div class="if-mini-msg user show">帮我看看材料想做什么</div><div class="if-mini-msg asst show">我看到 3 件事…列了 2 个 pending，要不要先写？</div>';
                document.getElementById('ifMsgCount').textContent = '2 轮';
                document.getElementById('ifInput').textContent = '继续输入…';
                document.getElementById('ifInput').classList.toggle('pulse', s === 2);
              } else {
                chat.innerHTML = '';
                document.getElementById('ifMsgCount').textContent = '0 轮';
                document.getElementById('ifInput').textContent = '输入框…';
                document.getElementById('ifInput').classList.remove('pulse');
              }

              // Sediment counters
              const sed = {
                und: 0, pen: 0, con: 0, cnf: 0, mvp: 0, ver: 0, art: 0,
              };
              if (s >= 3) { sed.und = 4; sed.pen = 3; sed.con = 3; sed.cnf = 2; sed.mvp = 4; }
              if (s >= 4) { sed.ver = 1; sed.art = 1; }  // document is the first artifact
              if (s >= 5) { sed.art = 3; sed.ver = 2; }  // all three artifacts + final snapshot
              ['und', 'pen', 'con', 'cnf', 'mvp', 'ver', 'art'].forEach(k => {
                const row = document.getElementById('ifSed-' + k);
                const cntEl = row.querySelector('.cnt');
                cntEl.textContent = sed[k];
                row.classList.toggle('glow', s === 3 && sed[k] > 0);
              });
              const totalSed = Object.values(sed).reduce((a, b) => a + b, 0);
              document.getElementById('ifSedCount').textContent = totalSed;

              // Deliverables
              const docCard = document.getElementById('ifDoc');
              const pageCard = document.getElementById('ifPage');
              const flowCard = document.getElementById('ifFlow');
              const setCard = (el, ready) => {
                el.classList.toggle('ready', ready);
                const status = el.querySelector('.status');
                status.textContent = ready ? 'seed_ready' : '未生成';
                status.className = ready ? 'status ready' : 'status empty';
              };
              setCard(docCard, s >= 4);
              setCard(pageCard, s >= 5);
              setCard(flowCard, s >= 5);

              // Preview area
              document.getElementById('ifPreview').classList.toggle('open', s === 5);
              document.getElementById('ifPreview').textContent = s === 5
                ? '交付物 iframe 已打开 · 三件套就绪 · 版本快照 v1 已记录'
                : '交付物预览区（执行态后才打开）';
            }

            document.getElementById('ifNext').addEventListener('click', () => {
              if (cur < 5) applyStep(cur + 1);
            });
            document.getElementById('ifPrev').addEventListener('click', () => {
              if (cur > 1) applyStep(cur - 1);
            });
            document.getElementById('ifReset').addEventListener('click', () => applyStep(1));
            document.querySelectorAll('.if-rail-step').forEach(r => {
              r.addEventListener('click', () => applyStep(parseInt(r.dataset.step, 10)));
            });

            applyStep(1);
          })();
        </script>
        """
    html = _artifact_shell(
        "客户需求转译台 · 端到端转译交互稿",
        "Interaction Flow",
        "可交互演示：5 步推进按钮，每步真把工作台 mini 状态跑起来——文件进场 / 聊天展开 / 沉淀计数 +1 / 三件套就绪 / 预览打开。点「下一步」试试。",
        inner,
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
        summary="基于 5 份客户原始材料沉淀的真实需求、范围边界、冲突与风险、MVP 能力包与验收建议。",
        status="seed_ready",
        content_format="markdown",
        storage_path=None,
        body=(
            "# 一、项目目标\n\n"
            "搭一个把客户散乱诉求转成可继续推进的结构化结果的「需求转译台」。原始材料里出现得最多的两句话是"
            "「客户讲得乱」「前面聊清楚后面还要重新整理」——这两件事本质上是同一个问题：**前期分析没有可沉淀的中间态**。"
            "于是同一个项目每多一轮人都会重新理解一遍，售前 / 咨询 / 产品经理之间也常对不上口径。\n\n"
            "本项目不做通用聊天助手，也不做大平台。一期目标只有两条：\n"
            "1. 让混杂的客户材料（PPT / 会议纪要 / 群聊截图 / 补充说明 / 表格 / 图片）一次喂进来就能进入分析。\n"
            "2. 让每一轮分析都同步落到结构化沉淀，并能产出「可继续推进讨论」的交付物——文档稿 + 页面方向 + 交互链路。\n\n"
            "# 二、真实需求\n\n"
            "**RN-1：接住混杂输入，不要求客户先整理。**\n"
            "- 现象：补充说明 §3 列了 Word / PDF / 群聊 / 纪要 / 截图 / 表格至少 6 类输入。0328 纪要 §1 又补了「音频也提到，但没定」。\n"
            "- 期望：上传后自动标准化与索引，左侧能看到每份资料的处理状态；不强迫先整理成「标准格式」。\n\n"
            "**RN-2：分析过程同步沉淀，分类落盘。**\n"
            "- 现象：群聊里张总反复说「最好能看到哪些已经确认了，哪些还没确认」。0328 纪要 §2 也明确「把已确认和未确认的内容分开」。\n"
            "- 期望：right pane 维护 7 类沉淀（current_understanding / pending / confirmed / conflict / mvp / versions / artifacts），"
            "每类独立维护，不能用一段总结糊起来。\n\n"
            "**RN-3：可看到「分析中间态」，而不是只能看聊天记录或只看文档。**\n"
            "- 现象：0328 纪要 §4 提到倾向「不是单聊天界面」，要「一边看资料、一边聊天、一边看整理结论」。\n"
            "- 期望：三栏工作台同步演进；点击右侧任一沉淀条目可回溯它来自哪些资料、哪轮对话。\n\n"
            "**RN-4：交付物至少能「继续推进讨论」。**\n"
            "- 现象：补充说明 §4 + 0328 纪要 §3 都强调最差也要「一份可以继续讨论的文档」，不能只是聊天记录。\n"
            "- 期望：固定三件套交付物（需求稿 markdown / 页面方案 HTML / 交互稿 HTML），可独立预览、可版本回滚。\n\n"
            "**RN-5：agent 主导引导，不只是被动答题。**\n"
            "- 现象：原始材料里客户讲得散，期望 agent 能「自动发现还缺哪些信息，给出下一步该追问什么」（0328 纪要 §2.2）。\n"
            "- 期望：agent 在每轮主动提议「沉淀哪条 / 触发哪份产物 / 抛哪个冲突」，由用户用一句话点头或修正方向。\n\n"
            "# 三、范围边界\n\n"
            "**IN scope（一期做）：**\n"
            "- 单项目工作台（三栏布局）+ 资料接入 + 聊天分析 + 7 类沉淀同步\n"
            "- 三件套交付物生成 + 版本快照\n"
            "- 多模态消息（文本 + 图片输入 / 生成图）\n"
            "- RAG 证据层 + LLM Wiki 综合层（Wiki 不作为 citation 源）\n\n"
            "**OUT of scope（一期不做）：**\n"
            "- 多人实时协同 / 评论 / @ 提醒\n"
            "- 权限体系（0328 纪要「当前没定的」，群聊倾向不做）\n"
            "- 插件市场 / 自定义 agent / 工作流编排\n"
            "- 自动改账、自动签发、对接正式交付流程\n"
            "- 多项目跨项目合并分析\n\n"
            "**GREY area（未拍板，留 pending）：**\n"
            "- 音频 / 视频转写输入是否一期纳入\n"
            "- 客户方是否直接使用这个工作台\n"
            "- 输出物是否包含页面草图与原型方向（vs 只出需求结论）\n\n"
            "# 四、冲突与风险\n\n"
            "**C-1：音频是否一期做。**\n"
            "- 群聊（3.26）：陈帆说「先把资料接入、分析过程、结论沉淀这几件事跑通」——隐含先不做音频。\n"
            "- 补充说明 §3：把「语音」列在输入清单。\n"
            "- 0328 纪要 §1：明说「音频也提到，但没定第一版一定要不要做」。\n"
            "- 处理建议：标到 pending，下一轮要求拍板；如先不做，多模态 MVP 收紧到只有图片。\n\n"
            "**C-2：「想做轻」vs「想给原型方向」的张力。**\n"
            "- 补充说明 §1：「第一版先证明这个方向成立就行」。\n"
            "- 补充说明 §4：「最好再往后多走一步，带一点初版方案 / 页面草图 / 原型方向」。\n"
            "- 处理建议：在 MVP 里把交付物定到 document（必出）+ page_solution + interaction_flow（HTML 简版，不是真原型），既不是「只出文档」也不会做成「正式原型平台」。\n\n"
            "**C-3：客户方是否直接使用还没定。**\n"
            "- 补充说明 §2：「客户方的人会不会直接用，现在没有定」。\n"
            "- 风险：如果一期就要给客户用，交互复杂度、权限、敏感数据脱敏都要重新评估；如果只内部用，UI 可以更密。\n"
            "- 处理建议：默认按「内部 + 可能给客户一起看」做，UI 留出「分享给客户」的入口但不做权限。\n\n"
            "# 五、MVP 能力包\n\n"
            "**MVP-1：三栏工作台基础。**\n"
            "- 输入：客户原始材料（md / pdf / docx / xlsx / txt / png / 截图）\n"
            "- 输出：left pane 文件列表 + 索引状态；center pane 多模态聊天；right pane 7 类沉淀同步\n"
            "- 验收点：上传一份新材料后 30 秒内出现在 left pane 且开始索引；任何一轮分析后 right pane 至少一个分类有更新或保持\n\n"
            "**MVP-2：7 类状态沉淀按类落盘。**\n"
            "- 输入：每轮 agent 分析结果（含 source_refs）\n"
            "- 输出：state_items 写入对应 category；可单独追加 / 撤回 / 合并；带来源引用\n"
            "- 验收点：每条沉淀可点开看引用了哪几份资料 / 哪几轮对话；撤回后版本快照保留历史\n\n"
            "**MVP-3：三件套交付物 + 版本快照。**\n"
            "- 输入：用户明示「整理出来」+ 当前已沉淀边界\n"
            "- 输出：document（markdown）+ page_solution（HTML）+ interaction_flow（HTML），"
            "右侧粘性面板可独立预览，每次重新生成打版本快照\n"
            "- 验收点：三类产物可分别预览 / 回滚到任意历史版本；预览不依赖外网资源\n\n"
            "**MVP-4：多模态消息（文本 + 图片）。**\n"
            "- 输入：拖拽 / 粘贴 / 上传图片到聊天框；agent 主动调用视觉工具产出架构图\n"
            "- 输出：消息支持 image_results 内嵌渲染；图片可作为下一轮分析的输入\n"
            "- 验收点：图片消息往返不丢失；前端可缩放查看；agent 生图时给出「为什么画这张」的说明\n\n"
            "# 六、验收建议\n\n"
            "**功能层面：**\n"
            "- 单项目从「上传 5 份混杂材料」到「三件套产出」端到端可在 30 分钟内完成（含 agent 等待时间）\n"
            "- 7 类沉淀的每一条都可追溯到至少一份资料引用 / 一轮对话引用\n"
            "- 「已确认 / 待确认 / 冲突」三态在 right pane 视觉上可一眼区分（颜色 / 图标）\n"
            "- 三件套交付物可独立预览，版本快照可回滚\n\n"
            "**体验层面：**\n"
            "- 第一次打开工作台，新人不需要培训能看懂三栏分别是干什么的\n"
            "- agent 回复不堆术语，不暴露内部 tool_call / 桶名 / 文件路径\n"
            "- 用户「修改主意」（撤回沉淀 / 重新分类）后系统行为可逆，不丢历史\n\n"
            "**收敛建议：**\n"
            "- 三个 pending 项（音频 / 客户方使用 / 原型深度）在下一轮分析前必须各自有明确收敛建议\n"
            "- 真上线前需要至少一个非 demo 的真实客户项目跑通，验证「混杂输入 → 三件套」链路\n"
        ),
        metadata={"seed": True},
        artifact_id="seed-document",
    )
    catalog.save_artifact(
        project_id=SEED_PROJECT_ID,
        artifact_type="page_solution",
        title="三栏工作台页面方案",
        summary="把工作台收敛为 5 张页面，强调三栏布局与 7 类沉淀的信息架构。",
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
        title="端到端转译交互稿",
        summary="聚焦「上传 → 对话 → 沉淀 → 触发 → 收稿」端到端流程与三态切换。",
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
    _seed_chat_images(settings)
    _seed_artifacts(settings, catalog)
