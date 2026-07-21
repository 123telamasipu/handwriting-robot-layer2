from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .charset import default_style_probe_path
from .storage import atomic_write_json


STYLE_PROFILE_SCHEMA_VERSION = "1.0"
DIRECTION_LABELS = (
    "right",
    "down_right",
    "down",
    "down_left",
    "left",
    "up_left",
    "up",
    "up_right",
)


@dataclass(frozen=True)
class StyleAnalysisOptions:
    minimum_samples: int = 20
    vertical_segment_threshold_deg: float = 30.0
    horizontal_segment_threshold_deg: float = 30.0
    direction_class_threshold_deg: float = 22.5
    corner_threshold_deg: float = 30.0

    def validate(self) -> None:
        if self.minimum_samples < 1:
            raise ValueError("minimum_samples must be at least 1")
        for name, value in (
            ("vertical_segment_threshold_deg", self.vertical_segment_threshold_deg),
            ("horizontal_segment_threshold_deg", self.horizontal_segment_threshold_deg),
            ("direction_class_threshold_deg", self.direction_class_threshold_deg),
            ("corner_threshold_deg", self.corner_threshold_deg),
        ):
            if not 0.0 < value < 90.0:
                raise ValueError(f"{name} must be between 0 and 90 degrees")


def _finite_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _quantile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        raise ValueError("cannot calculate a quantile from no values")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return (
        float(sorted_values[lower]) * (1.0 - weight)
        + float(sorted_values[upper]) * weight
    )


def _distribution(values: Iterable[Optional[float]]) -> Dict[str, Any]:
    finite = sorted(
        _finite_float(value, "distribution value")
        for value in values
        if value is not None
    )
    if not finite:
        return {
            "count": 0,
            "minimum": None,
            "q10": None,
            "q25": None,
            "median": None,
            "q75": None,
            "q90": None,
            "maximum": None,
            "mean": None,
            "std": None,
        }
    average = sum(finite) / len(finite)
    deviation = math.sqrt(
        sum((value - average) ** 2 for value in finite) / len(finite)
    )
    return {
        "count": len(finite),
        "minimum": _round(finite[0]),
        "q10": _round(_quantile(finite, 0.10)),
        "q25": _round(_quantile(finite, 0.25)),
        "median": _round(_quantile(finite, 0.50)),
        "q75": _round(_quantile(finite, 0.75)),
        "q90": _round(_quantile(finite, 0.90)),
        "maximum": _round(finite[-1]),
        "mean": _round(average),
        "std": _round(deviation),
    }


def _canonical_hash(document: Dict[str, Any]) -> str:
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _strokes(document: Dict[str, Any], name: str) -> List[Dict[str, Any]]:
    representations = document.get("representations", {})
    representation = representations.get(name, {})
    strokes = representation.get("strokes", [])
    if not isinstance(strokes, list) or not strokes:
        raise ValueError(f"processed sample does not contain {name} strokes")
    return strokes


def _points(strokes: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = [point for stroke in strokes for point in stroke.get("points", [])]
    if not result:
        raise ValueError("processed representation does not contain points")
    return result


def _xy(point: Dict[str, Any]) -> Tuple[float, float]:
    return (
        _finite_float(point.get("x"), "point.x"),
        _finite_float(point.get("y"), "point.y"),
    )


def _segment_values(
    strokes: Iterable[Dict[str, Any]],
) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any], float, float, float]]:
    for stroke in strokes:
        values = stroke.get("points", [])
        for first, second in zip(values, values[1:]):
            first_x, first_y = _xy(first)
            second_x, second_y = _xy(second)
            delta_x = second_x - first_x
            delta_y = second_y - first_y
            length = math.hypot(delta_x, delta_y)
            if length > 1e-12:
                yield first, second, delta_x, delta_y, length


def _mean_or_none(values: Iterable[float]) -> Optional[float]:
    finite = list(values)
    return sum(finite) / len(finite) if finite else None


def _layout_features(document: Dict[str, Any]) -> Dict[str, Any]:
    canvas = document.get("representations", {}).get("canvas", {})
    bounding_box = canvas.get("bounding_box", {})
    x_min = _finite_float(bounding_box.get("x_min"), "canvas.x_min")
    y_min = _finite_float(bounding_box.get("y_min"), "canvas.y_min")
    x_max = _finite_float(bounding_box.get("x_max"), "canvas.x_max")
    y_max = _finite_float(bounding_box.get("y_max"), "canvas.y_max")
    width = x_max - x_min
    height = y_max - y_min
    if width <= 0.0 or height <= 0.0:
        raise ValueError("canvas bounding box must have positive width and height")

    canvas_points = _points(_strokes(document, "canvas"))
    xs = [_xy(point)[0] for point in canvas_points]
    ys = [_xy(point)[1] for point in canvas_points]
    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0
    ink_center_x = sum(xs) / len(xs)
    ink_center_y = sum(ys) / len(ys)
    return {
        "width": _round(width),
        "height": _round(height),
        "aspect_ratio": _round(width / height),
        "bounding_box_area": _round(width * height),
        "bounding_box_center_x": _round(center_x),
        "bounding_box_center_y": _round(center_y),
        "ink_center_x": _round(ink_center_x),
        "ink_center_y": _round(ink_center_y),
        "ink_offset_x": _round(ink_center_x - 0.5),
        "ink_offset_y": _round(ink_center_y - 0.5),
    }


def _dynamics_features(document: Dict[str, Any]) -> Dict[str, Any]:
    strokes = _strokes(document, "dynamics")
    all_points = _points(strokes)
    path_length = 0.0
    segment_speeds: List[float] = []
    stroke_durations: List[float] = []
    pauses: List[float] = []

    previous_end: Optional[int] = None
    for stroke in strokes:
        points = stroke.get("points", [])
        if not points:
            continue
        start_time = int(_finite_float(points[0].get("t_ms", 0), "point.t_ms"))
        end_time = int(_finite_float(points[-1].get("t_ms", 0), "point.t_ms"))
        if end_time < start_time:
            raise ValueError("stroke timestamps must be monotonic")
        stroke_durations.append(float(end_time - start_time))
        if previous_end is not None:
            pauses.append(float(max(0, start_time - previous_end)))
        previous_end = end_time

        for first, second, _, _, length in _segment_values([stroke]):
            first_time = int(
                _finite_float(first.get("t_ms", 0), "point.t_ms")
            )
            second_time = int(
                _finite_float(second.get("t_ms", 0), "point.t_ms")
            )
            delta_ms = second_time - first_time
            if delta_ms < 0:
                raise ValueError("point timestamps must be monotonic")
            path_length += length
            if delta_ms > 0:
                segment_speeds.append(length / (delta_ms / 1000.0))

    effective_duration = max(
        int(_finite_float(point.get("t_ms", 0), "point.t_ms"))
        for point in all_points
    )
    pen_down_duration = sum(stroke_durations)
    pressures = [
        _finite_float(point.get("pressure", 0.5), "point.pressure")
        for point in all_points
    ]
    starts = [
        _finite_float(stroke["points"][0].get("pressure", 0.5), "point.pressure")
        for stroke in strokes
        if stroke.get("points")
    ]
    ends = [
        _finite_float(stroke["points"][-1].get("pressure", 0.5), "point.pressure")
        for stroke in strokes
        if stroke.get("points")
    ]
    x_tilts = [
        _finite_float(point.get("x_tilt", 0.0), "point.x_tilt")
        for point in all_points
    ]
    y_tilts = [
        _finite_float(point.get("y_tilt", 0.0), "point.y_tilt")
        for point in all_points
    ]
    tilt_magnitudes = [
        math.hypot(x_tilt, y_tilt)
        for x_tilt, y_tilt in zip(x_tilts, y_tilts)
    ]
    pressure_mean = sum(pressures) / len(pressures)
    pressure_std = math.sqrt(
        sum((pressure - pressure_mean) ** 2 for pressure in pressures)
        / len(pressures)
    )
    speed_distribution = _distribution(segment_speeds)
    return {
        "effective_duration_ms": effective_duration,
        "pen_down_duration_ms": _round(pen_down_duration),
        "pen_up_pause_total_ms": _round(sum(pauses)),
        "stroke_duration_mean_ms": _round(_mean_or_none(stroke_durations) or 0.0),
        "pen_up_pause_mean_ms": _round(_mean_or_none(pauses) or 0.0),
        "path_length": _round(path_length),
        "active_speed": _round(
            path_length / (pen_down_duration / 1000.0)
            if pen_down_duration > 0.0
            else 0.0
        ),
        "segment_speed_median": speed_distribution["median"],
        "segment_speed_q90": speed_distribution["q90"],
        "pressure_mean": _round(pressure_mean),
        "pressure_std": _round(pressure_std),
        "pressure_start_mean": _round(_mean_or_none(starts) or 0.0),
        "pressure_end_mean": _round(_mean_or_none(ends) or 0.0),
        "pressure_change": _round(
            (_mean_or_none(ends) or 0.0) - (_mean_or_none(starts) or 0.0)
        ),
        "x_tilt_mean": _round(_mean_or_none(x_tilts) or 0.0),
        "y_tilt_mean": _round(_mean_or_none(y_tilts) or 0.0),
        "tilt_magnitude_mean": _round(_mean_or_none(tilt_magnitudes) or 0.0),
    }


def _geometry_features(
    document: Dict[str, Any], options: StyleAnalysisOptions
) -> Dict[str, Any]:
    strokes = _strokes(document, "glyph")
    direction_lengths = [0.0] * len(DIRECTION_LABELS)
    horizontal_length = 0.0
    vertical_length = 0.0
    diagonal_length = 0.0
    vertical_slants: List[float] = []
    horizontal_angles: List[float] = []
    stroke_lengths: List[float] = []
    stroke_straightness: List[float] = []
    turns: List[float] = []
    start_xs: List[float] = []
    start_ys: List[float] = []
    end_xs: List[float] = []
    end_ys: List[float] = []

    for stroke in strokes:
        points = stroke.get("points", [])
        if not points:
            continue
        start_x, start_y = _xy(points[0])
        end_x, end_y = _xy(points[-1])
        start_xs.append(start_x)
        start_ys.append(start_y)
        end_xs.append(end_x)
        end_ys.append(end_y)
        segments = list(_segment_values([stroke]))
        stroke_length = sum(segment[4] for segment in segments)
        stroke_lengths.append(stroke_length)
        chord = math.hypot(end_x - start_x, end_y - start_y)
        stroke_straightness.append(
            min(1.0, chord / stroke_length) if stroke_length > 1e-12 else 1.0
        )

        segment_angles = [math.atan2(segment[3], segment[2]) for segment in segments]
        for angle, (_, _, _, _, length) in zip(segment_angles, segments):
            bin_index = int(math.floor((angle + math.pi / 8.0) / (math.pi / 4.0))) % 8
            direction_lengths[bin_index] += length
            orientation = math.degrees(angle) % 180.0
            vertical_slant = orientation - 90.0
            horizontal_angle = orientation if orientation <= 90.0 else orientation - 180.0
            if abs(vertical_slant) <= options.vertical_segment_threshold_deg:
                vertical_slants.append(vertical_slant)
            if abs(horizontal_angle) <= options.horizontal_segment_threshold_deg:
                horizontal_angles.append(horizontal_angle)
            if abs(horizontal_angle) <= options.direction_class_threshold_deg:
                horizontal_length += length
            elif abs(vertical_slant) <= options.direction_class_threshold_deg:
                vertical_length += length
            else:
                diagonal_length += length

        for first_angle, second_angle in zip(segment_angles, segment_angles[1:]):
            delta = math.atan2(
                math.sin(second_angle - first_angle),
                math.cos(second_angle - first_angle),
            )
            turns.append(abs(math.degrees(delta)))

    total_length = sum(stroke_lengths)
    if total_length <= 1e-12:
        raise ValueError("glyph path length is too small for style analysis")
    direction_histogram = {
        label: _round(length / total_length)
        for label, length in zip(DIRECTION_LABELS, direction_lengths)
    }
    total_turn = sum(turns)
    return {
        "stroke_count": len(strokes),
        "path_length": _round(total_length),
        "stroke_length_mean": _round(_mean_or_none(stroke_lengths) or 0.0),
        "straightness": _round(_mean_or_none(stroke_straightness) or 0.0),
        "mean_absolute_turn_deg": _round(_mean_or_none(turns) or 0.0),
        "turn_deg_per_path_unit": _round(total_turn / total_length),
        "corner_ratio": _round(
            sum(turn >= options.corner_threshold_deg for turn in turns) / len(turns)
            if turns
            else 0.0
        ),
        "vertical_slant_deg": (
            _distribution(vertical_slants)["median"] if vertical_slants else None
        ),
        "horizontal_angle_deg": (
            _distribution(horizontal_angles)["median"] if horizontal_angles else None
        ),
        "horizontal_share": _round(horizontal_length / total_length),
        "vertical_share": _round(vertical_length / total_length),
        "diagonal_share": _round(diagonal_length / total_length),
        "stroke_start_center_x": _round(_mean_or_none(start_xs) or 0.0),
        "stroke_start_center_y": _round(_mean_or_none(start_ys) or 0.0),
        "stroke_end_center_x": _round(_mean_or_none(end_xs) or 0.0),
        "stroke_end_center_y": _round(_mean_or_none(end_ys) or 0.0),
        "direction_histogram": direction_histogram,
    }


def analyze_processed_sample(
    document: Dict[str, Any],
    options: Optional[StyleAnalysisOptions] = None,
) -> Dict[str, Any]:
    options = options or StyleAnalysisOptions()
    options.validate()
    if document.get("type") != "processed_handwriting_sample":
        raise ValueError("style analysis requires a processed handwriting sample")
    character = document.get("character", {})
    value = str(character.get("value", ""))
    unicode_value = str(character.get("unicode", ""))
    if len(value) != 1 or not unicode_value:
        raise ValueError("processed sample character metadata is incomplete")
    writer_id = str(document.get("writer", {}).get("id", "")).strip()
    if not writer_id:
        raise ValueError("processed sample writer id is missing")
    return {
        "character": value,
        "unicode": unicode_value,
        "writer_id": writer_id,
        "source_sha256": document.get("source_sample", {}).get("sha256"),
        "processed_sha256": _canonical_hash(document),
        "layout": _layout_features(document),
        "dynamics": _dynamics_features(document),
        "geometry": _geometry_features(document, options),
    }


def _load_probe_groups(path: Optional[Path]) -> List[Dict[str, Any]]:
    probe_path = Path(path) if path else default_style_probe_path()
    document = json.loads(probe_path.read_text(encoding="utf-8"))
    groups = document.get("groups", [])
    if not isinstance(groups, list) or not groups:
        raise ValueError(f"style probe groups are missing: {probe_path}")
    result = []
    for group in groups:
        result.append(
            {
                "id": str(group.get("id", "")).strip(),
                "label": str(group.get("label", "")).strip(),
                "analysis_focus": str(group.get("analysis_focus", "")).strip(),
                "characters": list(str(group.get("characters", ""))),
            }
        )
    if any(not group["id"] for group in result):
        raise ValueError("each style probe group must have an id")
    characters = [
        character for group in result for character in group["characters"]
    ]
    if len(characters) != len(set(characters)):
        raise ValueError("style probe groups contain duplicate characters")
    return result


def _metric_distribution(
    samples: Iterable[Dict[str, Any]], section: str, metric: str
) -> Dict[str, Any]:
    return _distribution(
        sample.get(section, {}).get(metric)
        for sample in samples
    )


def _aggregate_samples(samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    layout_metrics = (
        "width",
        "height",
        "aspect_ratio",
        "bounding_box_area",
        "bounding_box_center_x",
        "bounding_box_center_y",
        "ink_center_x",
        "ink_center_y",
        "ink_offset_x",
        "ink_offset_y",
    )
    timing_metrics = (
        "effective_duration_ms",
        "pen_down_duration_ms",
        "pen_up_pause_total_ms",
        "stroke_duration_mean_ms",
        "pen_up_pause_mean_ms",
        "path_length",
        "active_speed",
        "segment_speed_median",
        "segment_speed_q90",
    )
    pressure_metrics = (
        "pressure_mean",
        "pressure_std",
        "pressure_start_mean",
        "pressure_end_mean",
        "pressure_change",
    )
    tilt_metrics = ("x_tilt_mean", "y_tilt_mean", "tilt_magnitude_mean")
    geometry_metrics = (
        "stroke_count",
        "path_length",
        "stroke_length_mean",
        "straightness",
        "mean_absolute_turn_deg",
        "turn_deg_per_path_unit",
        "corner_ratio",
        "vertical_slant_deg",
        "horizontal_angle_deg",
        "horizontal_share",
        "vertical_share",
        "diagonal_share",
        "stroke_start_center_x",
        "stroke_start_center_y",
        "stroke_end_center_x",
        "stroke_end_center_y",
    )
    directions = {
        label: _round(
            sum(sample["geometry"]["direction_histogram"][label] for sample in samples)
            / len(samples)
        )
        for label in DIRECTION_LABELS
    }
    return {
        "layout": {
            metric: _metric_distribution(samples, "layout", metric)
            for metric in layout_metrics
        },
        "timing": {
            metric: _metric_distribution(samples, "dynamics", metric)
            for metric in timing_metrics
        },
        "pressure": {
            metric: _metric_distribution(samples, "dynamics", metric)
            for metric in pressure_metrics
        },
        "tilt": {
            metric: _metric_distribution(samples, "dynamics", metric)
            for metric in tilt_metrics
        },
        "geometry": {
            **{
                metric: _metric_distribution(samples, "geometry", metric)
                for metric in geometry_metrics
            },
            "direction_histogram": directions,
        },
    }


def _median(aggregates: Dict[str, Any], section: str, metric: str) -> Any:
    return aggregates[section][metric]["median"]


def _std(aggregates: Dict[str, Any], section: str, metric: str) -> Any:
    return aggregates[section][metric]["std"]


def _generation_priors(aggregates: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "layout": {
            "canvas_width": _median(aggregates, "layout", "width"),
            "canvas_height": _median(aggregates, "layout", "height"),
            "aspect_ratio": _median(aggregates, "layout", "aspect_ratio"),
            "center_x": _median(aggregates, "layout", "bounding_box_center_x"),
            "center_y": _median(aggregates, "layout", "bounding_box_center_y"),
            "ink_offset_x": _median(aggregates, "layout", "ink_offset_x"),
            "ink_offset_y": _median(aggregates, "layout", "ink_offset_y"),
        },
        "deformation": {
            "vertical_slant_deg": _median(
                aggregates, "geometry", "vertical_slant_deg"
            ),
            "horizontal_angle_deg": _median(
                aggregates, "geometry", "horizontal_angle_deg"
            ),
            "straightness": _median(aggregates, "geometry", "straightness"),
            "mean_absolute_turn_deg": _median(
                aggregates, "geometry", "mean_absolute_turn_deg"
            ),
            "corner_ratio": _median(aggregates, "geometry", "corner_ratio"),
        },
        "motion": {
            "active_speed": _median(aggregates, "timing", "active_speed"),
            "stroke_duration_mean_ms": _median(
                aggregates, "timing", "stroke_duration_mean_ms"
            ),
            "pen_up_pause_mean_ms": _median(
                aggregates, "timing", "pen_up_pause_mean_ms"
            ),
        },
        "pressure": {
            "mean": _median(aggregates, "pressure", "pressure_mean"),
            "start": _median(aggregates, "pressure", "pressure_start_mean"),
            "end": _median(aggregates, "pressure", "pressure_end_mean"),
            "change": _median(aggregates, "pressure", "pressure_change"),
        },
        "variability": {
            "canvas_width_std": _std(aggregates, "layout", "width"),
            "canvas_height_std": _std(aggregates, "layout", "height"),
            "center_x_std": _std(
                aggregates, "layout", "bounding_box_center_x"
            ),
            "center_y_std": _std(
                aggregates, "layout", "bounding_box_center_y"
            ),
            "vertical_slant_std": _std(
                aggregates, "geometry", "vertical_slant_deg"
            ),
            "active_speed_std": _std(aggregates, "timing", "active_speed"),
            "pressure_mean_std": _std(
                aggregates, "pressure", "pressure_mean"
            ),
        },
    }


def build_style_profile(
    processed_documents: Iterable[Dict[str, Any]],
    probe_path: Optional[Path] = None,
    options: Optional[StyleAnalysisOptions] = None,
) -> Dict[str, Any]:
    options = options or StyleAnalysisOptions()
    options.validate()
    documents = list(processed_documents)
    if len(documents) < options.minimum_samples:
        raise ValueError(
            f"style analysis needs at least {options.minimum_samples} processed samples"
        )

    samples = [analyze_processed_sample(document, options) for document in documents]
    writer_ids = {sample["writer_id"] for sample in samples}
    if len(writer_ids) != 1:
        raise ValueError("processed samples must belong to one writer")
    characters = [sample["character"] for sample in samples]
    if len(characters) != len(set(characters)):
        raise ValueError("processed samples contain duplicate characters")
    preprocessing_options = {
        json.dumps(
            document.get("preprocessing", {}).get("options", {}),
            sort_keys=True,
            separators=(",", ":"),
        )
        for document in documents
    }
    if len(preprocessing_options) != 1:
        raise ValueError("processed samples use inconsistent preprocessing options")
    samples.sort(key=lambda sample: sample["unicode"])

    groups = _load_probe_groups(probe_path)
    group_by_character = {
        character: group for group in groups for character in group["characters"]
    }
    for sample in samples:
        group = group_by_character.get(sample["character"])
        sample["group_id"] = group["id"] if group else "ungrouped"

    aggregates = _aggregate_samples(samples)
    group_profiles = []
    for group in groups:
        group_samples = [
            sample for sample in samples if sample["group_id"] == group["id"]
        ]
        group_profiles.append(
            {
                "id": group["id"],
                "label": group["label"],
                "analysis_focus": group["analysis_focus"],
                "expected_count": len(group["characters"]),
                "analyzed_count": len(group_samples),
                "missing_characters": [
                    character
                    for character in group["characters"]
                    if character not in characters
                ],
                "features": _aggregate_samples(group_samples)
                if group_samples
                else None,
            }
        )

    expected_characters = [
        character for group in groups for character in group["characters"]
    ]
    expected_set = set(expected_characters)
    analyzed_expected = sum(character in expected_set for character in characters)
    coverage = analyzed_expected / len(expected_characters) if expected_characters else 1.0
    warnings: List[str] = []
    if coverage < 1.0:
        warnings.append("style_probe_incomplete")
    if aggregates["tilt"]["tilt_magnitude_mean"]["maximum"] == 0.0:
        warnings.append("tilt_signal_unavailable")
    fingerprint_source = "".join(
        f'{sample["unicode"]}:{sample["processed_sha256"]}\n' for sample in samples
    ).encode("utf-8")
    profile = {
        "schema_version": STYLE_PROFILE_SCHEMA_VERSION,
        "type": "handwriting_style_profile",
        "writer_id": next(iter(writer_ids)),
        "source": {
            "sample_count": len(samples),
            "expected_style_probe_count": len(expected_characters),
            "processed_sample_fingerprint_sha256": hashlib.sha256(
                fingerprint_source
            ).hexdigest(),
            "preprocessing_options": documents[0].get("preprocessing", {}).get(
                "options", {}
            ),
        },
        "analysis_options": asdict(options),
        "quality": {
            "style_probe_coverage": _round(coverage),
            "analyzed_expected_count": analyzed_expected,
            "unexpected_character_count": len(samples) - analyzed_expected,
            "feature_estimation_confidence": (
                "high" if coverage >= 0.9 else "medium" if coverage >= 0.5 else "low"
            ),
            "warnings": warnings,
        },
        "style_features": aggregates,
        "generation_priors": _generation_priors(aggregates),
        "group_profiles": group_profiles,
        "sample_features": samples,
        "limitations": [
            "This profile describes one writer but does not generate missing characters by itself.",
            "Applying the profile to unseen characters requires a standard ordered stroke skeleton.",
            "Generation quality must be evaluated separately from feature estimation coverage.",
        ],
    }
    return profile


def extract_style_profile(
    processed_dir: Path,
    output_path: Optional[Path] = None,
    probe_path: Optional[Path] = None,
    options: Optional[StyleAnalysisOptions] = None,
) -> Dict[str, Any]:
    processed_dir = Path(processed_dir)
    paths = sorted(processed_dir.glob("U+*/v*.json"))
    if not paths:
        raise ValueError(f"no processed handwriting samples found: {processed_dir}")
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    profile = build_style_profile(documents, probe_path=probe_path, options=options)
    if output_path is not None:
        atomic_write_json(Path(output_path), profile)
    return profile
