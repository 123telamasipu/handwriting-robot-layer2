from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from .charset import load_style_probe_charset
from .storage import SampleStore, atomic_write_json


@dataclass(frozen=True)
class SampleQualityRules:
    minimum_points: int = 8
    minimum_duration_ms: int = 40
    minimum_extent: float = 0.08


def _quality_issues(
    sample: Dict[str, Any], rules: SampleQualityRules
) -> List[str]:
    issues: List[str] = []
    if int(sample.get("point_count", 0)) < rules.minimum_points:
        issues.append("too_few_points")
    if int(sample.get("duration_ms", 0)) < rules.minimum_duration_ms:
        issues.append("duration_too_short")
    bounding_box = sample.get("bounding_box") or {}
    width = float(bounding_box.get("x_max", 0.0)) - float(
        bounding_box.get("x_min", 0.0)
    )
    height = float(bounding_box.get("y_max", 0.0)) - float(
        bounding_box.get("y_min", 0.0)
    )
    if max(width, height) < rules.minimum_extent:
        issues.append("writing_too_small")
    if "tablet" not in sample.get("input_sources", []):
        issues.append("not_tablet_input")
    return issues


def build_collection_report(
    store: SampleStore,
    characters: Iterable[str],
    variant: int = 1,
    rules: Optional[SampleQualityRules] = None,
) -> Dict[str, Any]:
    rules = rules or SampleQualityRules()
    requested = list(characters)
    samples: List[Dict[str, Any]] = []
    missing: List[str] = []
    review: List[Dict[str, Any]] = []
    pressures: List[float] = []

    for character in requested:
        variants = store.available_variants(character)
        sample = next(
            (item for item in variants if int(item.get("variant", 0)) == variant),
            None,
        )
        if sample is None:
            missing.append(character)
            continue
        samples.append(sample)
        issues = _quality_issues(sample, rules)
        if issues:
            review.append({"character": character, "issues": issues})
        for stroke in sample.get("strokes", []):
            pressures.extend(
                float(point.get("pressure", 0.5))
                for point in stroke.get("points", [])
            )

    point_counts = [int(sample.get("point_count", 0)) for sample in samples]
    durations = [int(sample.get("duration_ms", 0)) for sample in samples]
    stroke_counts = [int(sample.get("stroke_count", 0)) for sample in samples]
    tablet_samples = sum(
        "tablet" in sample.get("input_sources", []) for sample in samples
    )

    return {
        "schema_version": "1.0",
        "type": "handwriting_collection_report",
        "writer_id": store.writer_id,
        "variant": variant,
        "target_count": len(requested),
        "completed_count": len(samples),
        "completion": len(samples) / len(requested) if requested else 1.0,
        "tablet_sample_count": tablet_samples,
        "missing_characters": missing,
        "review_samples": review,
        "statistics": {
            "average_stroke_count": round(mean(stroke_counts), 3)
            if stroke_counts
            else 0.0,
            "average_point_count": round(mean(point_counts), 3)
            if point_counts
            else 0.0,
            "average_duration_ms": round(mean(durations), 3)
            if durations
            else 0.0,
            "pressure_min": round(min(pressures), 4) if pressures else None,
            "pressure_max": round(max(pressures), 4) if pressures else None,
            "pressure_average": round(mean(pressures), 4) if pressures else None,
        },
        "quality_rules": {
            "minimum_points": rules.minimum_points,
            "minimum_duration_ms": rules.minimum_duration_ms,
            "minimum_extent": rules.minimum_extent,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Summarize tablet style-probe samples")
    parser.add_argument("writer_id")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    parser.add_argument("--variant", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.variant <= 5:
        print("variant must be between 1 and 5")
        return 2
    try:
        store = SampleStore(args.data_dir, args.writer_id)
        entries = load_style_probe_charset()
        report = build_collection_report(
            store, (entry.character for entry in entries), variant=args.variant
        )
        if args.output:
            atomic_write_json(args.output, report)
            print(args.output)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        print(f"collection report failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
