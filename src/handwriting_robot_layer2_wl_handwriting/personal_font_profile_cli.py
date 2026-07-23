from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .personal_font_profile import build_personal_font_profile


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Build a ready personal handwriting profile without mandatory review"
    )
    parser.add_argument("writer_id")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    parser.add_argument("--processed-dir", type=Path)
    parser.add_argument("--hanzi-writer-package-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--probe-path", type=Path)
    parser.add_argument("--minimum-samples", type=int, default=20)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    processed_dir = args.processed_dir or (
        args.data_dir / "processed" / args.writer_id / "style_probe_v1"
    )
    output_dir = args.output_dir or (
        args.data_dir / "style_profiles" / args.writer_id
    )
    package_dir = args.hanzi_writer_package_dir or (
        args.data_dir.parent / "external" / "hanzi-writer-data-2.0.1"
    )
    try:
        manifest = build_personal_font_profile(
            args.writer_id,
            processed_dir,
            package_dir,
            output_dir,
            probe_path=args.probe_path,
            minimum_samples=args.minimum_samples,
        )
    except (OSError, ValueError) as error:
        print(f"personal handwriting profile creation failed: {error}")
        return 1
    readiness = manifest["readiness"]
    print(output_dir / "personal_font_profile_v1.json")
    print(
        f"ready without review: {readiness['ready_without_manual_review_count']}/"
        f"{readiness['character_count']}; enhanced: "
        f"{readiness['enhanced_automatic_alignment_count']}; safe fallback: "
        f"{readiness['safe_fallback_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
