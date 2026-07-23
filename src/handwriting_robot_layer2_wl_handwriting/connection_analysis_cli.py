from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .connection_analysis import (
    ConnectionAnalysisOptions,
    build_connection_candidate_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze running-script connection candidates without generating paths"
    )
    parser.add_argument("processed_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--maximum-distance", type=float, default=0.12)
    parser.add_argument("--maximum-pause-ms", type=int, default=120)
    parser.add_argument("--maximum-exit-turn-deg", type=float, default=60.0)
    parser.add_argument("--maximum-entry-turn-deg", type=float, default=90.0)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_connection_candidate_report(
            args.processed_dir,
            output_path=args.output,
            options=ConnectionAnalysisOptions(
                maximum_endpoint_distance=args.maximum_distance,
                maximum_pen_up_pause_ms=args.maximum_pause_ms,
                maximum_exit_turn_deg=args.maximum_exit_turn_deg,
                maximum_entry_turn_deg=args.maximum_entry_turn_deg,
            ),
        )
    except (OSError, ValueError) as error:
        print(f"running-script connection analysis failed: {error}")
        return 1
    print(args.output)
    print(f"candidates: {report['candidate_count']}/{report['boundary_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
