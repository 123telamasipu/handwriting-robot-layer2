from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .preprocessing import PreprocessingOptions, preprocess_style_probe
from .storage import SampleStore


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Clean and normalize tablet handwriting style-probe samples"
    )
    parser.add_argument("writer_id")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--variant", type=int, default=1)
    parser.add_argument("--duplicate-distance", type=float, default=0.0005)
    parser.add_argument("--resample-spacing", type=float, default=0.004)
    parser.add_argument("--smoothing-passes", type=int, default=1)
    parser.add_argument("--glyph-margin", type=float, default=0.1)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.variant <= 5:
        print("variant must be between 1 and 5")
        return 2
    output_dir = args.output_dir or (
        args.data_dir / "processed" / args.writer_id / "style_probe_v1"
    )
    options = PreprocessingOptions(
        duplicate_distance=args.duplicate_distance,
        resample_spacing=args.resample_spacing,
        smoothing_passes=args.smoothing_passes,
        glyph_margin=args.glyph_margin,
    )
    try:
        store = SampleStore(args.data_dir, args.writer_id)
        report = preprocess_style_probe(
            store,
            output_dir,
            variant=args.variant,
            options=options,
        )
    except (OSError, ValueError) as error:
        print(f"handwriting preprocessing failed: {error}")
        return 1
    print(output_dir / "preprocessing_report.json")
    return 0 if not report["missing_characters"] and not report["failed_samples"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
