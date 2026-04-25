"""离线评测当前 RAG 配置的命中率/MRR。

直接调用 evidence_indexing 的切分逻辑 + vector_store 的 Qdrant 写入/检索，绕开
sqlite catalog，每个配置跑一个临时 qdrant 目录，互不影响。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))


@dataclass(frozen=True)
class SeedSource:
    source_id: str
    name: str
    source_kind: str
    text: str


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_sources: tuple[str, ...]
    note: str = ""


@dataclass
class ConfigResult:
    name: str
    settings_summary: dict
    per_query: list[dict] = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)
    timing: dict = field(default_factory=dict)


SEED_SOURCES: list[SeedSource] = [
    SeedSource(
        source_id="seed-source-order",
        name="订单字段说明.md",
        source_kind="markdown",
        text="""# 订单字段说明

- 订单号：业务侧唯一单据标识，对账主键之一。
- 订单状态：已支付、已退款、部分退款、作废。
- 业务类型：直营、渠道、代销等，用于映射财务科目。
- 含税金额：业务侧展示金额，和财务侧税额拆分口径可能不同。
- 渠道：决定结算方式和部分税率。
- 退款标记：决定是否进入退款/冲销规则。
- 结算时间：用于确定财务入账周期。
""",
    ),
    SeedSource(
        source_id="seed-source-settlement",
        name="结算单样例.xlsx",
        source_kind="spreadsheet",
        text="""# Sheet: settlement_samples

表头: 结算单号 | 订单号 | 结算金额 | 税额 | 手续费 | 渠道归属
样例: SET-202604-001 | ORD-1001 | 1080.00 | 80.00 | 10.00 | 华东直营
样例: SET-202604-002 | ORD-1002 | -540.00 | -40.00 | 0.00 | 华南渠道
样例: SET-202604-003 | ORD-1003 | 2160.00 | 160.00 | 24.00 | 电商平台
行数估计: 2481, 列数估计: 6
""",
    ),
    SeedSource(
        source_id="seed-source-finance",
        name="财务科目口径说明.pdf",
        source_kind="pdf",
        text="""# 财务科目口径说明

- 主营业务收入：按业务类型和渠道归属挂科目。
- 退款冲销：按原始收入科目冲减，不与负单直接等价。
- 税额：财务侧按科目组合拆分，不完全复用业务侧税率拆分结果。
- 手续费：按渠道手续费科目单独入账。
- 入账记录：以凭证号和入账批次为准，不直接使用业务单号作为唯一主键。
""",
    ),
    SeedSource(
        source_id="seed-source-diff",
        name="历史差异清单.txt",
        source_kind="text",
        text="""历史差异清单
1. 退款订单 ORD-1002 在业务侧按负单处理，财务侧按冲销凭证处理，导致单号无法直接对齐。
2. 电商平台订单 ORD-1003 业务税额 160.00，财务税额拆分后为 158.40 + 1.60，结构不一致。
3. 渠道订单 ORD-1004 应挂"渠道收入"，实际入账到了"直营收入"。
4. 手续费在结算单中已净额扣减，但财务侧单独挂账，逐笔金额出现偏差。
""",
    ),
]


EVAL_CASES: list[EvalCase] = [
    EvalCase(
        query="退款订单在业务和财务两边怎么处理",
        expected_sources=("seed-source-diff", "seed-source-finance"),
        note="退款冲销 vs 负单",
    ),
    EvalCase(
        query="税额拆分规则在业务和财务侧有什么差别",
        expected_sources=("seed-source-finance", "seed-source-diff"),
    ),
    EvalCase(
        query="主营业务收入按什么挂科目",
        expected_sources=("seed-source-finance",),
    ),
    EvalCase(
        query="结算单包含哪些字段",
        expected_sources=("seed-source-settlement",),
    ),
    EvalCase(
        query="订单都有哪些字段",
        expected_sources=("seed-source-order",),
    ),
    EvalCase(
        query="渠道订单挂错到直营科目算什么差异",
        expected_sources=("seed-source-diff",),
    ),
    EvalCase(
        query="手续费在业务侧和财务侧记账方式有什么不同",
        expected_sources=("seed-source-diff", "seed-source-finance"),
    ),
    EvalCase(
        query="含税金额是什么意思",
        expected_sources=("seed-source-order",),
    ),
    EvalCase(
        query="财务凭证号和业务订单号能直接对齐吗",
        expected_sources=("seed-source-finance", "seed-source-diff"),
    ),
    EvalCase(
        query="电商平台 ORD-1003 的税额差异具体多少",
        expected_sources=("seed-source-diff",),
        note="期望命中具体数字片段",
    ),
    EvalCase(
        query="作废订单的状态怎么标记",
        expected_sources=("seed-source-order",),
    ),
    EvalCase(
        query="入账批次和凭证号的作用",
        expected_sources=("seed-source-finance",),
    ),
]


def _build_settings(*, data_dir: Path, embed_model: str | None, chunk_size: int, chunk_overlap: int, reranker_model: str | None, recall_top_k: int, top_k: int):
    from app.config import AppSettings

    settings = AppSettings(
        root_dir=REPO_ROOT,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "eval.db",
        projects_dir=data_dir / "projects",
        qdrant_path=data_dir / "qdrant",
        evidence_top_k=top_k,
        embedder_model=embed_model,
        reranker_model=reranker_model,
        evidence_recall_top_k=recall_top_k,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return settings


def run_config(
    *,
    name: str,
    embed_model: str | None,
    chunk_size: int = 800,
    chunk_overlap: int = 0,
    reranker_model: str | None = None,
    recall_top_k: int = 6,
    top_k: int = 6,
    sources: list[SeedSource] | None = None,
    cases: list[EvalCase] | None = None,
) -> ConfigResult:
    if sources is None:
        sources = SEED_SOURCES
    if cases is None:
        cases = EVAL_CASES
    from app.services import evidence_indexing
    from app.services.vector_store import QdrantLlamaIndexVectorStore, VectorDocument

    tmp_dir = Path(tempfile.mkdtemp(prefix="rag_eval_"))
    try:
        settings = _build_settings(
            data_dir=tmp_dir,
            embed_model=embed_model,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            reranker_model=reranker_model,
            recall_top_k=recall_top_k,
            top_k=top_k,
        )

        store = QdrantLlamaIndexVectorStore(settings)
        store.ensure_available()

        def chunker(text: str) -> list[str]:
            return evidence_indexing._chunk_text(
                text,
                chunk_size=getattr(settings, "chunk_size", evidence_indexing.MAX_CHUNK_CHARS),
                chunk_overlap=getattr(settings, "chunk_overlap", 0),
            )

        index_started = time.perf_counter()
        all_documents: list[VectorDocument] = []
        for source in sources:
            text_chunks = chunker(source.text)
            for order, content in enumerate(text_chunks):
                all_documents.append(
                    VectorDocument(
                        chunk_id=f"chunk-{source.source_id}-{order}",
                        source_id=source.source_id,
                        text=content,
                        metadata={
                            "source_id": source.source_id,
                            "source_name": source.name,
                            "source_kind": source.source_kind,
                            "chunk_order": order,
                        },
                    )
                )
        store.upsert("eval-project", all_documents)
        index_seconds = time.perf_counter() - index_started

        per_query = []
        hits_at_k = {1: 0, 3: 0, 6: 0}
        rr_total = 0.0
        query_started = time.perf_counter()
        for case in cases:
            hits = store.query("eval-project", case.query, top_k=top_k)
            ranked_sources = []
            for hit in hits:
                if hit.source_id not in ranked_sources:
                    ranked_sources.append(hit.source_id)

            first_hit_rank = None
            for rank, src in enumerate(ranked_sources, start=1):
                if src in case.expected_sources:
                    first_hit_rank = rank
                    break
            for k in (1, 3, 6):
                if first_hit_rank is not None and first_hit_rank <= k:
                    hits_at_k[k] += 1
            rr_total += (1.0 / first_hit_rank) if first_hit_rank else 0.0

            per_query.append(
                {
                    "query": case.query,
                    "expected": list(case.expected_sources),
                    "ranked_sources": ranked_sources[:6],
                    "first_hit_rank": first_hit_rank,
                }
            )
        query_seconds = time.perf_counter() - query_started

        n = len(cases)
        aggregate = {
            "hit@1": round(hits_at_k[1] / n, 3),
            "hit@3": round(hits_at_k[3] / n, 3),
            "hit@6": round(hits_at_k[6] / n, 3),
            "MRR": round(rr_total / n, 3),
            "n_queries": n,
            "n_chunks": len(all_documents),
        }
        return ConfigResult(
            name=name,
            settings_summary={
                "embed_model": embed_model or "<fastembed default: BAAI/bge-small-en-v1.5>",
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "reranker_model": reranker_model,
                "recall_top_k": recall_top_k,
                "top_k": top_k,
            },
            per_query=per_query,
            aggregate=aggregate,
            timing={
                "index_seconds": round(index_seconds, 2),
                "query_seconds_total": round(query_seconds, 2),
                "query_seconds_avg": round(query_seconds / n, 3),
            },
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", choices=["baseline", "zh", "zh_overlap", "zh_overlap_rerank", "all"], default="all")
    parser.add_argument("--out", type=str, default="reports/rag_eval.json")
    args = parser.parse_args()

    configs = []
    if args.config in ("baseline", "all"):
        configs.append({
            "name": "baseline (bge-small-en, 800/0, no rerank)",
            "embed_model": None,
            "chunk_size": 800,
            "chunk_overlap": 0,
            "reranker_model": None,
            "recall_top_k": 6,
            "top_k": 6,
        })
    if args.config in ("zh", "all"):
        configs.append({
            "name": "zh embed (bge-small-zh, 800/0, no rerank)",
            "embed_model": "BAAI/bge-small-zh-v1.5",
            "chunk_size": 800,
            "chunk_overlap": 0,
            "reranker_model": None,
            "recall_top_k": 6,
            "top_k": 6,
        })
    if args.config in ("zh_overlap", "all"):
        configs.append({
            "name": "zh embed + overlap (bge-small-zh, 500/120, no rerank)",
            "embed_model": "BAAI/bge-small-zh-v1.5",
            "chunk_size": 500,
            "chunk_overlap": 120,
            "reranker_model": None,
            "recall_top_k": 6,
            "top_k": 6,
        })
    if args.config in ("zh_overlap_rerank", "all"):
        configs.append({
            "name": "zh embed + overlap + rerank (recall 20 → top 6)",
            "embed_model": "BAAI/bge-small-zh-v1.5",
            "chunk_size": 500,
            "chunk_overlap": 120,
            "reranker_model": "BAAI/bge-reranker-base",
            "recall_top_k": 20,
            "top_k": 6,
        })

    results: list[ConfigResult] = []
    for cfg in configs:
        print(f"\n=== running: {cfg['name']} ===", flush=True)
        result = run_config(**cfg)
        results.append(result)
        agg = result.aggregate
        print(f"  hit@1={agg['hit@1']}  hit@3={agg['hit@3']}  hit@6={agg['hit@6']}  MRR={agg['MRR']}  chunks={agg['n_chunks']}")
        print(f"  index={result.timing['index_seconds']}s  q_avg={result.timing['query_seconds_avg']}s")

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nresults saved to {out_path}")


if __name__ == "__main__":
    main()
