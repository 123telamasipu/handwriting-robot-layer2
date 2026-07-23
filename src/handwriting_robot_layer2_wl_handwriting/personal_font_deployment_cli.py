from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .personal_font_deployment import build_personal_font_deployment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a hash-verified per-character personal-font deployment policy"
    )
    parser.add_argument("personal_font_profile", type=Path)
    parser.add_argument("evaluation_report", type=Path)
    parser.add_argument("output", type=Path)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        document = build_personal_font_deployment(
            args.personal_font_profile,
            args.evaluation_report,
            args.output,
        )
    except (OSError, ValueError, KeyError) as error:
        print(f"personal font deployment creation failed: {error}")
        return 1
    summary = document["summary"]
    print(args.output)
    print(
        f"enhanced: {summary['enhanced_automatic_alignment_count']}; "
        f"safe fallback: {summary['safe_fallback_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
