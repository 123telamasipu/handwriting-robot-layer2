from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .automatic_alignment import build_automatic_alignment_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automatically align natural handwriting segments to ordered kaishu strokes"
    )
    parser.add_argument("processed_dir", type=Path)
    parser.add_argument("hanzi_writer_package_dir", type=Path)
    parser.add_argument("output", type=Path)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = build_automatic_alignment_profile(
            args.processed_dir, args.hanzi_writer_package_dir, args.output
        )
    except (OSError, ValueError) as error:
        print(f"automatic running-script alignment failed: {error}")
        return 1
    print(args.output)
    summary = profile["summary"]
    print(
        f"profile ready: {summary['profile_ready_count']}/{profile['sample_count']}; "
        f"enhanced alignment: {summary['enhanced_alignment_count']}; "
        f"optional review: {summary['optional_review_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
