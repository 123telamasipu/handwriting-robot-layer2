from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .renderer import RenderOptions, analyze_coverage, render_text
from .storage import SampleStore, atomic_write_json


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Export captured handwriting as StrokeDocument v0.1"
    )
    parser.add_argument("request", type=Path, help="UTF-8 JSON render request")
    parser.add_argument("output", type=Path, help="StrokeDocument output path")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    parser.add_argument("--coverage-only", action="store_true")
    return parser


def load_request(path: Path) -> Dict[str, Any]:
    request = json.loads(path.read_text(encoding="utf-8"))
    if not request.get("user_id"):
        raise ValueError("request.user_id is required")
    if "text" not in request:
        raise ValueError("request.text is required")
    return request


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = load_request(args.request)
        store = SampleStore(args.data_dir, request["user_id"])
        if args.coverage_only:
            document = analyze_coverage(request["text"], store)
        else:
            option_values = request.get("options", {})
            options = RenderOptions(
                char_width_mm=float(option_values.get("char_width_mm", 8.0)),
                char_height_mm=float(option_values.get("char_height_mm", 8.0)),
                char_spacing_mm=float(option_values.get("char_spacing_mm", 1.2)),
                random_seed=int(option_values.get("random_seed", 0)),
                scale_jitter=float(option_values.get("scale_jitter", 0.03)),
                slant_jitter=float(option_values.get("slant_jitter", 0.025)),
                position_jitter_mm=float(
                    option_values.get("position_jitter_mm", 0.15)
                ),
            )
            page = request.get("page", {})
            document = render_text(
                request["text"],
                store,
                options,
                page_width_mm=float(page.get("width_mm", 210.0)),
                page_height_mm=float(page.get("height_mm", 297.0)),
                origin_mm=request.get("origin_mm", [10.0, 10.0]),
            )
        atomic_write_json(args.output, document)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"handwriting export failed: {error}")
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
