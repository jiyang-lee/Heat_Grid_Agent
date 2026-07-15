"""Planned runner for HeatGrid LLM Judge evaluation.

Stage 7.5 step 1 does not perform API calls. This script currently supports
only planning mode. Execution mode should be added after explicit approval.
"""

from __future__ import annotations

import argparse
import json

from llm_judge_utils import JUDGE_PROMPT_VERSION, estimate_prompt_payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan HeatGrid LLM Judge evaluation")
    parser.add_argument("--plan-only", action="store_true", help="Show planned Judge payload count without API calls")
    args = parser.parse_args()

    if not args.plan_only:
        raise SystemExit("LLM Judge API execution is not enabled in stage 7.5 step 1. Use --plan-only.")

    payloads = estimate_prompt_payloads()
    print(json.dumps({
        "planned_case_count": len(payloads),
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "api_calls_per_full_run": len(payloads),
        "api_execution_enabled": False
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
