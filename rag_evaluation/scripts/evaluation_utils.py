"""Shared helpers for HeatGrid retrieval evaluation.

This module intentionally has no dependency on the production RAG code.
It evaluates retrieved chunk ids against dataset labels only.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSONL row: {exc}") from exc
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, value: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def unique_preserve_order(values: Iterable[str]) -> tuple[list[str], int]:
    seen: set[str] = set()
    unique: list[str] = []
    duplicate_count = 0
    for value in values:
        if value in seen:
            duplicate_count += 1
            continue
        seen.add(value)
        unique.append(value)
    return unique, duplicate_count


def extract_chunk_id(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("chunk_id", "id"):
            value = item.get(key)
            if value:
                return str(value)
    raise ValueError(f"Retrieved item does not contain a chunk id: {item!r}")


def normalize_retrieved_chunk_ids(retrieved_items: Iterable[Any]) -> tuple[list[str], int]:
    raw = [extract_chunk_id(item) for item in retrieved_items]
    return unique_preserve_order(raw)


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    if not relevant_ids:
        return 0.0
    hits = sum(1 for chunk_id in retrieved_ids[:k] if chunk_id in relevant_ids)
    return hits / len(relevant_ids)


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    hits = sum(1 for chunk_id in retrieved_ids[:k] if chunk_id in relevant_ids)
    return hits / k


def hit_rate_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    return 1.0 if any(chunk_id in relevant_ids for chunk_id in retrieved_ids[:k]) else 0.0


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for index, chunk_id in enumerate(retrieved_ids, 1):
        if chunk_id in relevant_ids:
            return 1.0 / index
    return 0.0


def dcg(gains: list[float]) -> float:
    total = 0.0
    for index, gain in enumerate(gains, 1):
        total += gain / math.log2(index + 1)
    return total


def ndcg_at_k(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    partial_ids: set[str],
    k: int,
    relevant_gain: int = 2,
    partial_gain: int = 1,
) -> float:
    if k <= 0:
        return 0.0
    effective_partial_ids = partial_ids - relevant_ids
    gains: list[float] = []
    for chunk_id in retrieved_ids[:k]:
        if chunk_id in relevant_ids:
            gains.append(float(relevant_gain))
        elif chunk_id in effective_partial_ids:
            gains.append(float(partial_gain))
        else:
            gains.append(0.0)
    ideal_gains = [float(relevant_gain)] * len(relevant_ids)
    ideal_gains += [float(partial_gain)] * len(effective_partial_ids)
    ideal_gains = sorted(ideal_gains, reverse=True)[:k]
    ideal = dcg(ideal_gains)
    if ideal == 0:
        return 0.0
    return dcg(gains) / ideal


def mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    if not materialized:
        return None
    return sum(materialized) / len(materialized)


def safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
