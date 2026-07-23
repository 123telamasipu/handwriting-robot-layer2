from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .personal_font_evaluation import (
    PersonalFontEvaluationOptions,
    build_personal_font_evaluation,
)
from .storage import atomic_write_json
from .style_generator import StyleGenerationOptions


def _random_seeds(value: str) -> tuple[int, ...]:
    try:
        seeds = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from error
    if not seeds:
        raise argparse.ArgumentTypeError("at least one seed is required")
    return seeds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare global-style and personal-font trajectory generation"
    )
    parser.add_argument("processed_dir", type=Path)
    parser.add_argument("personal_font_profile", type=Path)
    parser.add_argument("hanzi_writer_package_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variant", type=int, default=1)
    parser.add_argument("--seeds", type=_random_seeds, default=(0, 17, 42))
    parser.add_argument("--variation-strength", type=float, default=0.35)
    parser.add_argument("--meaningful-delta", type=float, default=0.005)
    parser.add_argument("--severe-regression-delta", type=float, default=-0.04)
    parser.add_argument("--minimum-overall-delta", type=float, default=-0.005)
    parser.add_argument("--maximum-regression-rate", type=float, default=0.15)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_personal_font_evaluation(
            args.processed_dir,
            args.personal_font_profile,
            args.hanzi_writer_package_dir,
            generation_options=StyleGenerationOptions(
                variation_strength=args.variation_strength
            ),
            evaluation_options=PersonalFontEvaluationOptions(
                random_seeds=args.seeds,
                meaningful_delta=args.meaningful_delta,
                severe_regression_delta=args.severe_regression_delta,
                minimum_overall_delta=args.minimum_overall_delta,
                maximum_regression_rate=args.maximum_regression_rate,
            ),
            variant=args.variant,
        )
        atomic_write_json(args.output, report)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"personal font evaluation failed: {error}")
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
