from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from heatgrid_ops.reports.graph import (
    ReportGraphOptions,
    ReportGraphSpec,
    ReportJson,
    run_report_graph,
)

ROOT: Final = Path(__file__).resolve().parents[1]
REPORT_SRC: Final = (
    ROOT / "v0_ops_handoff_package" / "report_generator_hsj" / "report_generator" / "src"
)


def test_report_graph_returns_enriched_input_when_enrich_only() -> None:
    def normalize(data: ReportJson) -> ReportJson:
        return {**data, "normalized": True}

    def enrich(data: ReportJson, _: ReportGraphOptions) -> ReportJson:
        return {**data, "rag_evidence": [{"ref_id": "rag-test"}]}

    def generate(_: ReportJson, __: ReportGraphOptions) -> ReportJson:
        raise AssertionError("generate should not run in enrich-only mode")

    result = run_report_graph(
        ReportGraphSpec(normalize=normalize, enrich=enrich, generate=generate),
        {"report_context": {"report_id": "test"}},
        ReportGraphOptions(with_rag=True, enrich_only=True),
    )

    assert result["normalized"] is True
    assert result["rag_evidence"] == [{"ref_id": "rag-test"}]


def test_report_graph_runs_validation_stage_after_llm_call() -> None:
    def normalize(data: ReportJson) -> ReportJson:
        return data

    def enrich(data: ReportJson, _: ReportGraphOptions) -> ReportJson:
        return data

    def generate(_: ReportJson, __: ReportGraphOptions) -> ReportJson:
        return {"report_metadata": {"report_type": "bad"}}

    def validate(report: ReportJson, _: ReportGraphOptions) -> ReportJson:
        raise RuntimeError(f"invalid report: {report['report_metadata']}")

    with pytest.raises(RuntimeError, match="invalid report"):
        run_report_graph(
            ReportGraphSpec(
                normalize=normalize,
                enrich=enrich,
                generate=generate,
                validate_schema=validate,
            ),
            {"report_context": {"report_id": "test"}},
            ReportGraphOptions(),
        )


def test_legacy_anomaly_generator_keeps_mock_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPORT_SRC))
    module = load_legacy_module("legacy_generate_anomaly_report", "generate_anomaly_report.py")

    report = module.generate_anomaly_report_from_input({}, mock=True)

    metadata = report["report_metadata"]
    assert isinstance(metadata, dict)
    assert metadata["report_type"] == "anomaly_report"


def load_legacy_module(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, REPORT_SRC / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{filename} 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
