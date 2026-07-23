from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .similarity import build_similarity_report
from .storage import atomic_write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare generated character geometry with processed handwriting samples"
    )
    parser.add_argument("processed_dir", type=Path)
    parser.add_argument("generated_document", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variant", type=int, default=1)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.variant < 1:
            raise ValueError("variant must be at least 1")
        document = json.loads(
            args.generated_document.read_text(encoding="utf-8-sig")
        )
        report = build_similarity_report(
            args.processed_dir, document, variant=args.variant
        )
        atomic_write_json(args.output, report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"geometry similarity evaluation failed: {error}")
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
