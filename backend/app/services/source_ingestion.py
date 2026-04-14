from dataclasses import dataclass


@dataclass
class NormalizedSource:
    parse_status: str
    parse_summary: str
    normalized_path: str | None = None


def normalize_source(name: str, source_kind: str) -> NormalizedSource:
    # 这里先给出最小占位，后续接真实抽取、转写和表格标准化逻辑。
    return NormalizedSource(
        parse_status="queued",
        parse_summary=f"{name} 已入库，等待 {source_kind} 标准化处理。"
    )
