from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import orjson

from heatgrid_ops.reports.graph import ReportJson, ReportGraphOptions

REPORT_GENERATOR_SRC: Final = (
    Path(__file__).resolve().parents[3]
    / "v0_ops_handoff_package"
    / "report_generator_hsj"
    / "report_generator"
    / "src"
)


def ensure_legacy_report_src_path() -> None:
    report_src = str(REPORT_GENERATOR_SRC)
    if report_src not in sys.path:
        sys.path.insert(0, report_src)


def write_report_json(report: ReportJson, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(
        orjson.dumps(report, option=orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE)
    )


__all__ = [
    "ReportJson",
    "ReportGraphOptions",
    "ensure_legacy_report_src_path",
    "write_report_json",
]
