"""用真实项目资料跑 RAG 评测对比（不再用 seed mock 数据）。

资料来源：原仓库 data/projects/project-e247c8192d/sources/ 下的 5 份会议/群聊
材料 + project-c46b1bf88f/sources/ 下的访谈纪要。query 是按资料里出现过的关键
信息点反向设计的 13 条，每条至少有一个明确的期望 source。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_REPO_DATA = Path("/Users/zhaofengli/projects/requirement_nyl/data/projects")

sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_eval import EvalCase, SeedSource, run_config


def _load_sources() -> list[SeedSource]:
    spec = [
        ("e247-bg", "项目背景-先看这个.md", "markdown",
         ORIGINAL_REPO_DATA / "project-e247c8192d/sources/项目背景-先看这个.md"),
        ("e247-supp", "补充说明-v1.md", "markdown",
         ORIGINAL_REPO_DATA / "project-e247c8192d/sources/补充说明-v1.md"),
        ("e247-wechat", "微信群里先聊的内容整理.md", "markdown",
         ORIGINAL_REPO_DATA / "project-e247c8192d/sources/微信群里先聊的内容整理.md"),
        ("e247-materials", "现有材料先发这些.txt", "text",
         ORIGINAL_REPO_DATA / "project-e247c8192d/sources/现有材料先发这些.txt"),
        ("e247-meeting", "0328碰一下会议纪要.md", "markdown",
         ORIGINAL_REPO_DATA / "project-e247c8192d/sources/0328碰一下会议纪要.md"),
        ("c46b-interview", "客户初访纪要.txt", "text",
         ORIGINAL_REPO_DATA / "project-c46b1bf88f/sources/客户初访纪要.txt"),
        ("c46b-flow", "requirement-flow-evidence.txt", "text",
         ORIGINAL_REPO_DATA / "project-c46b1bf88f/sources/requirement-flow-evidence.txt"),
    ]
    sources = []
    for sid, name, kind, path in spec:
        if not path.exists():
            print(f"  [warn] missing: {path}", file=sys.stderr)
            continue
        sources.append(SeedSource(source_id=sid, name=name, source_kind=kind, text=path.read_text(encoding="utf-8")))
    return sources


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        query="这个项目内部叫什么名字，是谁起的",
        expected_sources=("e247-wechat",),
        note="3月27日 李敏提议名字",
    ),
    EvalCase(
        query="项目主要解决什么问题",
        expected_sources=("e247-meeting", "e247-bg"),
    ),
    EvalCase(
        query="这个工具的目标使用人群是谁",
        expected_sources=("e247-supp", "e247-bg"),
    ),
    EvalCase(
        query="客户方的人会不会直接使用",
        expected_sources=("e247-supp",),
        note="补充说明明确说没定",
    ),
    EvalCase(
        query="第一版要不要支持音频输入",
        expected_sources=("e247-meeting",),
        note="0328会议提到但没定",
    ),
    EvalCase(
        query="输入资料的类型大概有哪些",
        expected_sources=("e247-supp", "e247-meeting"),
    ),
    EvalCase(
        query="为什么不应该把它做成普通聊天框",
        expected_sources=("e247-bg", "e247-meeting", "e247-wechat"),
    ),
    EvalCase(
        query="第一阶段输出物有哪些可能选项",
        expected_sources=("e247-supp", "e247-meeting"),
    ),
    EvalCase(
        query="页面草图必须要在第一版做出来吗",
        expected_sources=("e247-meeting",),
        note="0328 当前没定中",
    ),
    EvalCase(
        query="目前还有哪些没定下来的事",
        expected_sources=("e247-bg", "e247-meeting", "e247-supp"),
    ),
    EvalCase(
        query="为什么不能让 AI 自动做项目判断",
        expected_sources=("e247-wechat",),
        note="陈帆 3月25日发言",
    ),
    EvalCase(
        query="为什么客户前期需求经常聊不清楚",
        expected_sources=("e247-meeting", "e247-bg"),
    ),
    EvalCase(
        query="区分已确认和未确认的状态有什么用",
        expected_sources=("e247-wechat", "e247-meeting"),
    ),
    EvalCase(
        query="演示用的对账案例和产品本身是什么关系",
        expected_sources=("e247-materials",),
        note="第5项明确说 演示案例不代表产品方向",
    ),
]


def main() -> None:
    sources = _load_sources()
    print(f"loaded {len(sources)} real sources, total chars = {sum(len(s.text) for s in sources)}")

    configs = [
        {
            "name": "baseline (bge-small-en, 800/0, no rerank)",
            "embed_model": None,
            "chunk_size": 800,
            "chunk_overlap": 0,
            "reranker_model": None,
            "recall_top_k": 6,
            "top_k": 6,
        },
        {
            "name": "zh embed (bge-small-zh, 800/0, no rerank)",
            "embed_model": "BAAI/bge-small-zh-v1.5",
            "chunk_size": 800,
            "chunk_overlap": 0,
            "reranker_model": None,
            "recall_top_k": 6,
            "top_k": 6,
        },
        {
            "name": "zh embed + overlap (bge-small-zh, 500/120, no rerank)",
            "embed_model": "BAAI/bge-small-zh-v1.5",
            "chunk_size": 500,
            "chunk_overlap": 120,
            "reranker_model": None,
            "recall_top_k": 6,
            "top_k": 6,
        },
        {
            "name": "zh embed + overlap + rerank (recall 20 → top 6)",
            "embed_model": "BAAI/bge-small-zh-v1.5",
            "chunk_size": 500,
            "chunk_overlap": 120,
            "reranker_model": "BAAI/bge-reranker-base",
            "recall_top_k": 20,
            "top_k": 6,
        },
    ]

    results = []
    for cfg in configs:
        print(f"\n=== running: {cfg['name']} ===", flush=True)
        result = run_config(**cfg, sources=sources, cases=EVAL_CASES)
        results.append(result)
        agg = result.aggregate
        print(f"  hit@1={agg['hit@1']}  hit@3={agg['hit@3']}  hit@6={agg['hit@6']}  MRR={agg['MRR']}  chunks={agg['n_chunks']}")
        print(f"  index={result.timing['index_seconds']}s  q_avg={result.timing['query_seconds_avg']}s")

    out_path = REPO_ROOT / "reports" / "rag_eval_real.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nresults saved to {out_path}")


if __name__ == "__main__":
    main()
