from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .style_analysis import StyleAnalysisOptions, extract_style_profile


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Extract a reusable handwriting style profile"
    )
    parser.add_argument("writer_id")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    parser.add_argument("--processed-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--probe-path", type=Path)
    parser.add_argument("--minimum-samples", type=int, default=20)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    processed_dir = args.processed_dir or (
        args.data_dir / "processed" / args.writer_id / "style_probe_v1"
    )
    output_path = args.output or (
        args.data_dir / "style_profiles" / args.writer_id / "style_profile_v1.json"
    )
    try:
        profile = extract_style_profile(
            processed_dir,
            output_path=output_path,
            probe_path=args.probe_path,
            options=StyleAnalysisOptions(minimum_samples=args.minimum_samples),
        )
    except (OSError, ValueError) as error:
        print(f"handwriting style analysis failed: {error}")
        return 1
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
