from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .alignment_review import (
    build_alignment_review_package,
    validate_alignment_review,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or validate a private running-script alignment review"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("connection_report", type=Path)
    generate.add_argument("processed_dir", type=Path)
    generate.add_argument("hanzi_writer_package_dir", type=Path)
    generate.add_argument("output_dir", type=Path)
    generate.add_argument(
        "--confidence", action="append", choices=("high", "medium"), default=[]
    )
    validate = subparsers.add_parser("validate")
    validate.add_argument("review", type=Path)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "generate":
            report = json.loads(args.connection_report.read_text(encoding="utf-8-sig"))
            document = build_alignment_review_package(
                report,
                args.processed_dir,
                args.hanzi_writer_package_dir,
                args.output_dir,
                confidences=args.confidence or ("high",),
            )
            print(args.output_dir / "alignment_review.json")
            print(f"characters: {len(document['characters'])}")
        else:
            document = json.loads(args.review.read_text(encoding="utf-8-sig"))
            validate_alignment_review(document)
            print(args.review)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"alignment review failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
