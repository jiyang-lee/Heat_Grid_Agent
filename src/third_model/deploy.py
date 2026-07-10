from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import config
from .m1_specialist import build_m1_specialist_outputs
from .operational import build_agent_card


def export_agent_columns(output_path: Path | None = None) -> pd.DataFrame:
    """Deployment helper: emit only the columns intended for the agent layer."""
    if not config.MERGED_SCORES_PATH.exists():
        raise FileNotFoundError(
            f"Missing merged scores: {config.MERGED_SCORES_PATH}. Run pipeline steps through merge first."
        )
    build_agent_card()
    agent = build_m1_specialist_outputs()
    agent = pd.read_csv(config.AGENT_CARD_PATH)
    target = output_path or config.AGENT_CARD_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    agent.to_csv(target, index=False, encoding="utf-8-sig", float_format=config.CSV_FLOAT_FORMAT, lineterminator=config.CSV_LINE_TERMINATOR)
    return agent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the agent handoff CSV from 3rd_model merged scores.")
    parser.add_argument("--output", default=str(config.AGENT_CARD_PATH), help="Output CSV path.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    frame = export_agent_columns(Path(args.output))
    print(args.output)
    print(f"rows={len(frame)} columns={len(frame.columns)}")


if __name__ == "__main__":
    main()
