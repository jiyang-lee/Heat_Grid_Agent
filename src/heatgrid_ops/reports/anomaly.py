from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from heatgrid_ops.reports.graph import ReportJson
from heatgrid_ops.reports.utils import ensure_legacy_report_src_path, write_report_json

type LLMCaller = Callable[[str, ReportJson], ReportJson]


def generate_anomaly_report_from_input(
    input_data: ReportJson,
    *,
    mock: bool = False,
    llm_caller: LLMCaller | None = None,
    with_rag: bool = False,
    rag_url: str | None = None,
    rag_top_k: int = 5,
    force_rag: bool = False,
    enrich_only: bool = False,
) -> ReportJson:
    ensure_legacy_report_src_path()
    from generate_anomaly_report import generate_anomaly_report_from_input as generate

    return generate(
        input_data,
        mock=mock,
        llm_caller=llm_caller,
        with_rag=with_rag,
        rag_url=rag_url,
        rag_top_k=rag_top_k,
        force_rag=force_rag,
        enrich_only=enrich_only,
    )


def write_anomaly_report_json(
    input_data: ReportJson,
    output_path: Path,
    *,
    mock: bool = False,
    llm_caller: LLMCaller | None = None,
    api_key: str | None = None,
    model: str | None = None,
    with_rag: bool = False,
    rag_url: str | None = None,
    rag_top_k: int = 5,
    force_rag: bool = False,
) -> ReportJson:
    if llm_caller is None and api_key is not None and model is not None:
        ensure_legacy_report_src_path()
        from report_utils import call_llm_json_with_config

        llm_caller = partial(
            call_llm_json_with_config,
            api_key=api_key,
            model=model,
        )
    report = generate_anomaly_report_from_input(
        input_data,
        mock=mock,
        llm_caller=llm_caller,
        with_rag=with_rag,
        rag_url=rag_url,
        rag_top_k=rag_top_k,
        force_rag=force_rag,
    )
    write_report_json(report, output_path)
    return report


__all__ = ["generate_anomaly_report_from_input", "write_anomaly_report_json"]
