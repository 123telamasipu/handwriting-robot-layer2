from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .hanzi_writer_adapter import (
    build_hanzi_writer_library,
    write_hanzi_writer_coverage_report,
)
from .storage import atomic_write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and adapt local Hanzi Writer Data medians"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    report = subparsers.add_parser("coverage", help="check target charset coverage")
    report.add_argument("package_dir", type=Path)
    report.add_argument("output", type=Path)

    convert = subparsers.add_parser("convert", help="convert selected characters")
    convert.add_argument("package_dir", type=Path)
    convert.add_argument("characters")
    convert.add_argument("output", type=Path)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "coverage":
            report = write_hanzi_writer_coverage_report(
                args.package_dir, args.output
            )
            print(args.output)
            return 0 if not report["invalid_characters"] else 1
        library = build_hanzi_writer_library(
            args.package_dir, list(args.characters)
        )
        atomic_write_json(args.output, library)
        print(args.output)
        return 0
    except (OSError, ValueError) as error:
        print(f"Hanzi Writer Data integration failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
