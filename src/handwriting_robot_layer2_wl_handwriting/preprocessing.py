from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .charset import CharacterEntry, load_style_probe_charset
from .storage import SampleStore, atomic_write_json


PREPROCESSING_SCHEMA_VERSION = "1.0"
NUMERIC_POINT_FIELDS = (
    "x",
    "y",
    "pressure",
    "x_tilt",
    "y_tilt",
    "rotation",
    "tangential_pressure",
)


@dataclass(frozen=True)
class PreprocessingOptions:
    duplicate_distance: float = 0.0005
    resample_spacing: float = 0.004
    smoothing_passes: int = 1
    glyph_margin: float = 0.1

    def validate(self) -> None:
        if not 0.0 <= self.duplicate_distance < 0.1:
            raise ValueError("duplicate_distance must be between 0 and 0.1")
        if not 0.0001 <= self.resample_spacing <= 0.1:
            raise ValueError("resample_spacing must be between 0.0001 and 0.1")
        if not 0 <= self.smoothing_passes <= 5:
            raise ValueError("smoothing_passes must be between 0 and 5")
        if not 0.0 <= self.glyph_margin < 0.5:
            raise ValueError("glyph_margin must be between 0 and 0.5")


def _finite_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _normalized_point(value: Dict[str, Any], time_origin: int) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("each point must be a JSON object")
    point = {
        "x": min(1.0, max(0.0, _finite_float(value.get("x"), "point.x"))),
        "y": min(1.0, max(0.0, _finite_float(value.get("y"), "point.y"))),
        "t_ms": max(0, int(_finite_float(value.get("t_ms", 0), "point.t_ms")) - time_origin),
        "pressure": min(
            1.0,
            max(0.0, _finite_float(value.get("pressure", 0.5), "point.pressure")),
        ),
        "x_tilt": _finite_float(value.get("x_tilt", 0.0), "point.x_tilt"),
        "y_tilt": _finite_float(value.get("y_tilt", 0.0), "point.y_tilt"),
        "rotation": _finite_float(value.get("rotation", 0.0), "point.rotation"),
        "tangential_pressure": _finite_float(
            value.get("tangential_pressure", 0.0), "point.tangential_pressure"
        ),
        "source": str(value.get("source", "tablet")),
    }
    return point


def _distance(first: Dict[str, Any], second: Dict[str, Any]) -> float:
    return math.hypot(second["x"] - first["x"], second["y"] - first["y"])


def _path_length(points: List[Dict[str, Any]]) -> float:
    return sum(_distance(first, second) for first, second in zip(points, points[1:]))


def _same_event(first: Dict[str, Any], second: Dict[str, Any]) -> bool:
    return (
        first["t_ms"] == second["t_ms"]
        and first["source"] == second["source"]
        and all(first[field] == second[field] for field in NUMERIC_POINT_FIELDS)
    )


def _deduplicate_events(
    points: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    if not points:
        return [], 0
    kept = [dict(points[0])]
    removed = 0
    for point in points[1:]:
        if _same_event(kept[-1], point):
            removed += 1
            continue
        kept.append(dict(point))
    return kept, removed


def _deduplicate_geometry(
    points: List[Dict[str, Any]], minimum_distance: float
) -> Tuple[List[Dict[str, Any]], int]:
    if len(points) <= 2:
        return [dict(point) for point in points], 0

    kept = [dict(points[0])]
    removed = 0
    for point in points[1:-1]:
        if _distance(kept[-1], point) <= minimum_distance:
            removed += 1
            continue
        kept.append(dict(point))

    final_point = dict(points[-1])
    if _distance(kept[-1], final_point) <= minimum_distance:
        removed += 1
        if len(kept) == 1:
            kept.append(final_point)
        else:
            kept[-1] = final_point
    else:
        kept.append(final_point)
    return kept, removed


def _smooth_points(
    points: List[Dict[str, Any]], passes: int
) -> List[Dict[str, Any]]:
    result = [dict(point) for point in points]
    for _ in range(passes):
        if len(result) < 3:
            break
        smoothed = [dict(result[0])]
        for previous, current, following in zip(result, result[1:], result[2:]):
            point = dict(current)
            point["x"] = previous["x"] * 0.25 + current["x"] * 0.5 + following["x"] * 0.25
            point["y"] = previous["y"] * 0.25 + current["y"] * 0.5 + following["y"] * 0.25
            smoothed.append(point)
        smoothed.append(dict(result[-1]))
        result = smoothed
    return result


def _interpolate_point(
    first: Dict[str, Any], second: Dict[str, Any], fraction: float
) -> Dict[str, Any]:
    point: Dict[str, Any] = {}
    for field in NUMERIC_POINT_FIELDS:
        point[field] = first[field] + (second[field] - first[field]) * fraction
    point["t_ms"] = round(
        first["t_ms"] + (second["t_ms"] - first["t_ms"]) * fraction
    )
    point["source"] = first["source"] if fraction < 0.5 else second["source"]
    return point


def _round_point(point: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "x": round(float(point["x"]), 6),
        "y": round(float(point["y"]), 6),
        "t_ms": max(0, int(point["t_ms"])),
        "pressure": round(min(1.0, max(0.0, float(point["pressure"]))), 4),
        "x_tilt": round(float(point["x_tilt"]), 2),
        "y_tilt": round(float(point["y_tilt"]), 2),
        "rotation": round(float(point["rotation"]), 2),
        "tangential_pressure": round(float(point["tangential_pressure"]), 4),
        "source": str(point["source"]),
    }


def _resample_points(
    points: List[Dict[str, Any]], spacing: float
) -> List[Dict[str, Any]]:
    if len(points) < 2:
        return [_round_point(point) for point in points]

    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _distance(first, second))
    total_length = cumulative[-1]
    if total_length <= 1e-12:
        return [_round_point(points[0]), _round_point(points[-1])]

    count = max(2, math.ceil(total_length / spacing) + 1)
    targets = [total_length * index / (count - 1) for index in range(count)]
    result: List[Dict[str, Any]] = []
    segment = 0
    for target in targets:
        while segment + 1 < len(cumulative) and cumulative[segment + 1] < target:
            segment += 1
        next_segment = min(segment + 1, len(points) - 1)
        segment_length = cumulative[next_segment] - cumulative[segment]
        fraction = 0.0 if segment_length <= 1e-12 else (
            target - cumulative[segment]
        ) / segment_length
        result.append(
            _round_point(
                _interpolate_point(points[segment], points[next_segment], fraction)
            )
        )

    for previous, current in zip(result, result[1:]):
        if current["t_ms"] < previous["t_ms"]:
            current["t_ms"] = previous["t_ms"]
    return result


def _bounding_box(strokes: List[Dict[str, Any]]) -> Dict[str, float]:
    points = [point for stroke in strokes for point in stroke.get("points", [])]
    if not points:
        raise ValueError("processed sample has no points")
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    return {
        "x_min": round(min(xs), 6),
        "y_min": round(min(ys), 6),
        "x_max": round(max(xs), 6),
        "y_max": round(max(ys), 6),
    }


def _glyph_representation(
    strokes: List[Dict[str, Any]], margin: float
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    bounding_box = _bounding_box(strokes)
    width = bounding_box["x_max"] - bounding_box["x_min"]
    height = bounding_box["y_max"] - bounding_box["y_min"]
    extent = max(width, height)
    if extent <= 1e-12:
        raise ValueError("sample bounding box is too small to normalize")
    scale = (1.0 - 2.0 * margin) / extent
    center_x = (bounding_box["x_min"] + bounding_box["x_max"]) / 2.0
    center_y = (bounding_box["y_min"] + bounding_box["y_max"]) / 2.0

    normalized: List[Dict[str, Any]] = []
    for stroke in strokes:
        normalized_points = []
        for value in stroke.get("points", []):
            point = dict(value)
            point["x"] = round((float(value["x"]) - center_x) * scale + 0.5, 6)
            point["y"] = round((float(value["y"]) - center_y) * scale + 0.5, 6)
            normalized_points.append(point)
        normalized.append({"points": normalized_points})

    return normalized, {
        "method": "uniform_bbox_center",
        "margin": margin,
        "scale": round(scale, 8),
        "source_center": [round(center_x, 6), round(center_y, 6)],
        "source_bounding_box": bounding_box,
        "target_bounding_box": _bounding_box(normalized),
    }


def _source_hash(sample: Dict[str, Any]) -> str:
    canonical = json.dumps(
        sample, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def preprocess_sample(
    sample: Dict[str, Any], options: Optional[PreprocessingOptions] = None
) -> Dict[str, Any]:
    options = options or PreprocessingOptions()
    options.validate()
    raw_strokes = sample.get("strokes", [])
    if not isinstance(raw_strokes, list) or not raw_strokes:
        raise ValueError("sample does not contain strokes")
    raw_points = [
        point
        for stroke in raw_strokes
        for point in stroke.get("points", [])
        if isinstance(stroke, dict)
    ]
    if not raw_points:
        raise ValueError("sample does not contain points")
    time_origin = min(
        int(_finite_float(point.get("t_ms", 0), "point.t_ms"))
        for point in raw_points
    )

    dynamics_strokes: List[Dict[str, Any]] = []
    canvas_strokes: List[Dict[str, Any]] = []
    redundant_events_removed = 0
    geometry_points_removed = 0
    dynamics_point_count = 0
    geometry_point_count = 0
    original_path_length = 0.0
    cleaned_path_length = 0.0
    for stroke in raw_strokes:
        values = stroke.get("points", [])
        points = [_normalized_point(value, time_origin) for value in values]
        if len(points) < 2:
            raise ValueError("each stroke must contain at least two points")
        original_path_length += _path_length(points)
        dynamics, event_removed = _deduplicate_events(points)
        redundant_events_removed += event_removed
        dynamics_point_count += len(dynamics)
        dynamics_strokes.append(
            {"points": [_round_point(point) for point in dynamics]}
        )
        geometry, spatial_removed = _deduplicate_geometry(
            dynamics, options.duplicate_distance
        )
        geometry_points_removed += spatial_removed
        geometry_point_count += len(geometry)
        smoothed = _smooth_points(geometry, options.smoothing_passes)
        cleaned_path_length += _path_length(smoothed)
        resampled = _resample_points(smoothed, options.resample_spacing)
        canvas_strokes.append({"points": resampled})

    glyph_strokes, transform = _glyph_representation(
        canvas_strokes, options.glyph_margin
    )
    canvas_bbox = _bounding_box(canvas_strokes)
    resampled_points = sum(len(stroke["points"]) for stroke in canvas_strokes)
    effective_duration = max(
        point["t_ms"] for stroke in canvas_strokes for point in stroke["points"]
    )

    return {
        "schema_version": PREPROCESSING_SCHEMA_VERSION,
        "type": "processed_handwriting_sample",
        "status": "processed",
        "writer": sample.get("writer", {}),
        "character": sample.get("character", {}),
        "variant": int(sample.get("variant", 1)),
        "source_sample": {
            "schema_version": sample.get("schema_version"),
            "captured_at": sample.get("captured_at"),
            "sha256": _source_hash(sample),
            "input_sources": sample.get("input_sources", []),
            "capture_context": sample.get("capture_context", {}),
        },
        "preprocessing": {
            "options": asdict(options),
            "original_stroke_count": len(raw_strokes),
            "original_point_count": len(raw_points),
            "dynamics_point_count": dynamics_point_count,
            "geometry_point_count": geometry_point_count,
            "resampled_point_count": resampled_points,
            "redundant_events_removed": redundant_events_removed,
            "geometry_points_removed": geometry_points_removed,
            "initial_wait_removed_ms": time_origin,
            "original_duration_ms": int(sample.get("duration_ms", 0)),
            "effective_duration_ms": effective_duration,
            "original_path_length": round(original_path_length, 6),
            "cleaned_path_length": round(cleaned_path_length, 6),
        },
        "representations": {
            "dynamics": {
                "coordinate_system": {
                    "type": "normalized",
                    "origin": "top-left",
                    "x_range": [0.0, 1.0],
                    "y_range": [0.0, 1.0],
                    "preserves_timing_and_sensor_events": True,
                },
                "strokes": dynamics_strokes,
            },
            "canvas": {
                "coordinate_system": {
                    "type": "normalized",
                    "origin": "top-left",
                    "x_range": [0.0, 1.0],
                    "y_range": [0.0, 1.0],
                    "preserves_writer_layout": True,
                },
                "bounding_box": canvas_bbox,
                "strokes": canvas_strokes,
            },
            "glyph": {
                "coordinate_system": {
                    "type": "glyph_normalized",
                    "origin": "top-left",
                    "x_range": [0.0, 1.0],
                    "y_range": [0.0, 1.0],
                    "preserves_aspect_ratio": True,
                },
                "transform": transform,
                "strokes": glyph_strokes,
            },
        },
    }


def preprocess_style_probe(
    store: SampleStore,
    output_dir: Path,
    entries: Optional[Iterable[CharacterEntry]] = None,
    variant: int = 1,
    options: Optional[PreprocessingOptions] = None,
) -> Dict[str, Any]:
    options = options or PreprocessingOptions()
    options.validate()
    requested = list(entries) if entries is not None else load_style_probe_charset()
    output_dir = Path(output_dir)
    missing: List[str] = []
    failed: List[Dict[str, str]] = []
    summaries: List[Dict[str, Any]] = []

    for entry in requested:
        sample = next(
            (
                value
                for value in store.available_variants(entry.character)
                if int(value.get("variant", 0)) == variant
            ),
            None,
        )
        if sample is None:
            missing.append(entry.character)
            continue
        try:
            processed = preprocess_sample(sample, options)
            path = output_dir / entry.unicode / f"v{variant:02d}.json"
            atomic_write_json(path, processed)
            metadata = processed["preprocessing"]
            summaries.append(
                {
                    "character": entry.character,
                    "unicode": entry.unicode,
                    "path": str(path.relative_to(output_dir)).replace("\\", "/"),
                    "original_point_count": metadata["original_point_count"],
                    "resampled_point_count": metadata["resampled_point_count"],
                    "redundant_events_removed": metadata["redundant_events_removed"],
                    "geometry_points_removed": metadata["geometry_points_removed"],
                    "initial_wait_removed_ms": metadata["initial_wait_removed_ms"],
                    "effective_duration_ms": metadata["effective_duration_ms"],
                }
            )
        except (OSError, ValueError) as error:
            failed.append({"character": entry.character, "error": str(error)})

    original_points = sum(item["original_point_count"] for item in summaries)
    resampled_points = sum(item["resampled_point_count"] for item in summaries)
    report = {
        "schema_version": PREPROCESSING_SCHEMA_VERSION,
        "type": "handwriting_preprocessing_report",
        "writer_id": store.writer_id,
        "variant": variant,
        "target_count": len(requested),
        "processed_count": len(summaries),
        "missing_characters": missing,
        "failed_samples": failed,
        "options": asdict(options),
        "statistics": {
            "original_point_count": original_points,
            "resampled_point_count": resampled_points,
            "point_count_ratio": round(
                resampled_points / original_points, 6
            ) if original_points else None,
            "redundant_events_removed": sum(
                item["redundant_events_removed"] for item in summaries
            ),
            "geometry_points_removed": sum(
                item["geometry_points_removed"] for item in summaries
            ),
            "average_initial_wait_removed_ms": round(
                mean(item["initial_wait_removed_ms"] for item in summaries), 3
            ) if summaries else 0.0,
            "maximum_initial_wait_removed_ms": max(
                (item["initial_wait_removed_ms"] for item in summaries), default=0
            ),
            "average_effective_duration_ms": round(
                mean(item["effective_duration_ms"] for item in summaries), 3
            ) if summaries else 0.0,
        },
        "samples": summaries,
    }
    atomic_write_json(output_dir / "preprocessing_report.json", report)
    return report
