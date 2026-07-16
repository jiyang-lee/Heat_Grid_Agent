from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "rag_evaluation" / "scripts" / "calibrate_runtime_answer_quality.py"


def _load_module():
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("runtime_quality_calibration", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(score: float, target_pass: bool, **features: bool):
    return {
        "case_id": "case-1",
        "score": score,
        "target_pass": target_pass,
        "features": features,
    }


def test_rule_stats_only_adopts_high_precision_supported_rules() -> None:
    module = _load_module()
    rows = [
        _row(40, False, candidate=True),
        _row(45, False, candidate=True),
        _row(50, False, candidate=True),
        _row(80, True, candidate=False),
    ]

    stats = module._rule_stats(rows)

    assert stats["candidate"]["bad_precision"] == 1.0
    assert stats["candidate"]["adopt_as_hard_rule"] is True


def test_threshold_metrics_distinguish_false_pass_and_unnecessary_regeneration() -> None:
    module = _load_module()
    rows = [
        _row(80, True),
        _row(75, True),
        _row(60, False),
        _row(72, False),
    ]

    metrics = module._metrics(rows, 70.0, set())

    assert metrics["tp"] == 2
    assert metrics["fp"] == 1
    assert metrics["tn"] == 1
    assert metrics["fn"] == 0
