from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence, Tuple


SIMILARITY_SCHEMA_VERSION = "1.0"
Point = Tuple[float, float]

GLOBAL_SHAPE_WARNING_THRESHOLD = 0.75
ORDERED_STROKE_WARNING_THRESHOLD = 0.68
ASPECT_RATIO_WARNING_THRESHOLD = 0.70
DIRECTION_WARNING_THRESHOLD = 0.68
LIKELY_SEGMENTATION_SHAPE_THRESHOLD = 0.78


def _finite_point(value: Sequence[Any]) -> Point:
    if len(value) < 2:
        raise ValueError("trajectory point must contain x and y")
    point = float(value[0]), float(value[1])
    if not all(math.isfinite(coordinate) for coordinate in point):
        raise ValueError("trajectory coordinates must be finite")
    return point


def _extract_processed_strokes(sample: Dict[str, Any]) -> List[List[Point]]:
    if sample.get("type") != "processed_handwriting_sample":
        raise ValueError("reference must be a processed handwriting sample")
    strokes = []
    for stroke in sample.get("representations", {}).get("glyph", {}).get("strokes", []):
        points = [
            (float(point["x"]), float(point["y"]))
            for point in stroke.get("points", [])
        ]
        if len(points) >= 2:
            strokes.append(points)
    if not strokes:
        raise ValueError("processed sample has no glyph strokes")
    return strokes


def _extract_generated_strokes(
    document: Dict[str, Any], character_record: Dict[str, Any]
) -> List[List[Point]]:
    by_order = {
        int(stroke.get("order", 0)): [
            _finite_point(point) for point in stroke.get("points", [])
        ]
        for stroke in document.get("strokes", [])
    }
    strokes = [
        by_order[int(order)]
        for order in character_record.get("stroke_orders", [])
        if int(order) in by_order and len(by_order[int(order)]) >= 2
    ]
    if not strokes:
        raise ValueError("generated character has no trajectory strokes")
    return strokes


def _normalize(strokes: List[List[Point]]) -> Tuple[List[List[Point]], Dict[str, float]]:
    points = [point for stroke in strokes for point in stroke]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    width = x_max - x_min
    height = y_max - y_min
    extent = max(width, height)
    if extent <= 1e-12:
        raise ValueError("trajectory bounding box is too small")
    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0
    normalized = [
        [
            ((point[0] - center_x) / extent + 0.5, (point[1] - center_y) / extent + 0.5)
            for point in stroke
        ]
        for stroke in strokes
    ]
    return normalized, {
        "width": width,
        "height": height,
        "aspect_ratio": width / max(height, 1e-12),
    }


def _resample(points: Sequence[Point], count: int) -> List[Point]:
    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(
            cumulative[-1] + math.hypot(second[0] - first[0], second[1] - first[1])
        )
    total = cumulative[-1]
    if total <= 1e-12:
        return [points[0]] * count
    targets = [total * index / max(1, count - 1) for index in range(count)]
    result = []
    segment = 0
    for target in targets:
        while segment + 1 < len(cumulative) and cumulative[segment + 1] < target:
            segment += 1
        following = min(segment + 1, len(points) - 1)
        length = cumulative[following] - cumulative[segment]
        fraction = 0.0 if length <= 1e-12 else (target - cumulative[segment]) / length
        result.append(
            (
                points[segment][0] + (points[following][0] - points[segment][0]) * fraction,
                points[segment][1] + (points[following][1] - points[segment][1]) * fraction,
            )
        )
    return result


def _sample_cloud(strokes: List[List[Point]], per_stroke: int = 24) -> List[Point]:
    return [point for stroke in strokes for point in _resample(stroke, per_stroke)]


def _chamfer_distance(first: Sequence[Point], second: Sequence[Point]) -> float:
    def directed(source: Sequence[Point], target: Sequence[Point]) -> float:
        return mean(
            min(math.hypot(point[0] - other[0], point[1] - other[1]) for other in target)
            for point in source
        )

    return (directed(first, second) + directed(second, first)) / 2.0


def _direction_histogram(strokes: List[List[Point]], bins: int = 8) -> List[float]:
    histogram = [0.0] * bins
    total = 0.0
    for stroke in strokes:
        for first, second in zip(stroke, stroke[1:]):
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            length = math.hypot(dx, dy)
            if length <= 1e-12:
                continue
            angle = math.atan2(dy, dx) % (2.0 * math.pi)
            index = min(bins - 1, int(angle / (2.0 * math.pi) * bins))
            histogram[index] += length
            total += length
    return [value / total for value in histogram] if total else histogram


def _histogram_score(first: Sequence[float], second: Sequence[float]) -> float:
    return max(0.0, 1.0 - sum(abs(a - b) for a, b in zip(first, second)) / 2.0)


def _round_metrics(metrics: Dict[str, float]) -> Dict[str, float]:
    return {key: round(value, 6) for key, value in metrics.items()}


def compare_character_geometry(
    reference_sample: Dict[str, Any],
    generated_document: Dict[str, Any],
    character_record: Dict[str, Any],
) -> Dict[str, Any]:
    character = str(character_record.get("character", ""))
    character_metadata = reference_sample.get("character", {})
    reference_character = str(
        character_metadata.get("value") or character_metadata.get("character") or ""
    )
    if not character or character != reference_character:
        raise ValueError("reference and generated characters do not match")
    reference_raw = _extract_processed_strokes(reference_sample)
    generated_raw = _extract_generated_strokes(generated_document, character_record)
    reference, reference_box = _normalize(reference_raw)
    generated, generated_box = _normalize(generated_raw)

    global_distance = _chamfer_distance(
        _sample_cloud(reference), _sample_cloud(generated)
    )
    global_shape_score = math.exp(-4.0 * global_distance)
    if len(reference) == len(generated):
        ordered_distance = mean(
            _chamfer_distance(_resample(first, 24), _resample(second, 24))
            for first, second in zip(reference, generated)
        )
        ordered_stroke_score = math.exp(-4.0 * ordered_distance)
    else:
        ordered_distance = None
        ordered_stroke_score = 0.0
    stroke_count_score = min(len(reference), len(generated)) / max(
        len(reference), len(generated)
    )
    aspect_score = math.exp(
        -abs(math.log(reference_box["aspect_ratio"] / generated_box["aspect_ratio"]))
    )
    direction_score = _histogram_score(
        _direction_histogram(reference), _direction_histogram(generated)
    )
    metrics = {
        "global_shape_score": global_shape_score,
        "ordered_stroke_score": ordered_stroke_score,
        "stroke_count_score": stroke_count_score,
        "aspect_ratio_score": aspect_score,
        "direction_score": direction_score,
    }
    strict_kaishu_score = (
        metrics["global_shape_score"] * 0.35
        + metrics["ordered_stroke_score"] * 0.30
        + metrics["stroke_count_score"] * 0.15
        + metrics["aspect_ratio_score"] * 0.10
        + metrics["direction_score"] * 0.10
    )
    running_script_score = (
        metrics["global_shape_score"] * 0.65
        + metrics["aspect_ratio_score"] * 0.15
        + metrics["direction_score"] * 0.20
    )
    return {
        "character": character,
        "unicode": f"U+{ord(character):04X}",
        "reference_variant": int(reference_sample.get("variant", 1)),
        "reference_stroke_count": len(reference),
        "generated_stroke_count": len(generated),
        "distances": {
            "global_chamfer": round(global_distance, 6),
            "ordered_stroke_chamfer": (
                round(ordered_distance, 6) if ordered_distance is not None else None
            ),
        },
        "scores": _round_metrics(metrics),
        "strict_kaishu_score": round(strict_kaishu_score, 6),
        "running_script_score": round(running_script_score, 6),
        "overall_score": round(strict_kaishu_score, 6),
    }


def _document_fingerprint(document: Dict[str, Any]) -> str:
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def diagnose_character_result(result: Dict[str, Any]) -> Dict[str, Any]:
    scores = result.get("scores", {})
    global_shape = float(scores.get("global_shape_score", 0.0))
    ordered_stroke = float(scores.get("ordered_stroke_score", 0.0))
    aspect_ratio = float(scores.get("aspect_ratio_score", 0.0))
    direction = float(scores.get("direction_score", 0.0))
    reference_count = int(result.get("reference_stroke_count", 0))
    generated_count = int(result.get("generated_stroke_count", 0))
    count_mismatch = reference_count != generated_count
    running_script_score = float(
        result.get(
            "running_script_score",
            global_shape * 0.65 + aspect_ratio * 0.15 + direction * 0.20,
        )
    )
    shape_alignment = (
        global_shape * 0.65 + aspect_ratio * 0.15 + direction * 0.20
    )

    issues = []
    if count_mismatch:
        issues.append("stroke_segmentation_differs_from_standard_kaishu")
    if global_shape < GLOBAL_SHAPE_WARNING_THRESHOLD:
        issues.append("global_shape_deviation")
    if aspect_ratio < ASPECT_RATIO_WARNING_THRESHOLD:
        issues.append("aspect_ratio_deviation")
    if direction < DIRECTION_WARNING_THRESHOLD:
        issues.append("direction_distribution_deviation")
    if not count_mismatch and ordered_stroke < ORDERED_STROKE_WARNING_THRESHOLD:
        issues.append("ordered_stroke_geometry_deviation")

    if count_mismatch:
        if shape_alignment >= LIKELY_SEGMENTATION_SHAPE_THRESHOLD:
            category = "likely_running_script_variant"
            priority = "low"
        else:
            category = "running_script_variant_and_shape_difference"
            priority = "high" if shape_alignment < 0.75 else "medium"
    elif issues:
        category = "shape_difference"
        priority = "high" if shape_alignment < 0.72 else "medium"
    else:
        category = "no_major_geometry_issue"
        priority = "low"

    return {
        "primary_category": category,
        "review_priority": priority,
        "issues": issues,
        "stroke_count_delta": generated_count - reference_count,
        "shape_alignment_score": round(shape_alignment, 6),
        "running_script_score": round(running_script_score, 6),
        "script_interpretation": (
            "reference_may_join_standard_strokes"
            if generated_count > reference_count
            else "reference_may_split_standard_strokes"
            if generated_count < reference_count
            else "same_pen_down_stroke_count"
        ),
        "notes": (
            "Standard kaishu stroke boundaries are references, not mandatory boundaries for natural handwriting. Confirm with visual review."
        ),
    }


def build_report_diagnosis(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    diagnosed = []
    for result in results:
        diagnosis = diagnose_character_result(result)
        diagnosed.append(
            {
                "character": result.get("character"),
                "overall_score": result.get("overall_score"),
                **diagnosis,
            }
        )

    category_counts: Dict[str, int] = {}
    priority_counts: Dict[str, int] = {}
    issue_counts: Dict[str, int] = {}
    for item in diagnosed:
        category = str(item["primary_category"])
        priority = str(item["review_priority"])
        category_counts[category] = category_counts.get(category, 0) + 1
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        for issue in item["issues"]:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

    priority_order = {"high": 0, "medium": 1, "low": 2}
    review_queue = sorted(
        diagnosed,
        key=lambda item: (
            priority_order[str(item["review_priority"])],
            float(item["shape_alignment_score"]),
            float(item["overall_score"]),
        ),
    )
    return {
        "category_counts": category_counts,
        "review_priority_counts": priority_counts,
        "issue_counts": issue_counts,
        "review_queue": review_queue,
        "thresholds": {
            "global_shape_warning": GLOBAL_SHAPE_WARNING_THRESHOLD,
            "ordered_stroke_warning": ORDERED_STROKE_WARNING_THRESHOLD,
            "aspect_ratio_warning": ASPECT_RATIO_WARNING_THRESHOLD,
            "direction_warning": DIRECTION_WARNING_THRESHOLD,
            "likely_segmentation_shape": LIKELY_SEGMENTATION_SHAPE_THRESHOLD,
        },
        "guidance": [
            "Review high-priority characters visually before changing the generator.",
            "A likely running-script variant may join or split standard kaishu strokes and is not automatically an error.",
            "Do not compare scores produced by different thresholds as one continuous series.",
        ],
    }


def build_similarity_report(
    processed_dir: Path,
    generated_document: Dict[str, Any],
    variant: int = 1,
) -> Dict[str, Any]:
    if generated_document.get("type") != "stroke_document":
        raise ValueError("generated input must be a StrokeDocument")
    records = generated_document.get("generation", {}).get("characters", [])
    if not records:
        raise ValueError("StrokeDocument does not contain generation character metadata")
    results = []
    skipped = []
    for record in records:
        character = str(record.get("character", ""))
        if len(character) != 1:
            skipped.append({"character": character, "reason": "invalid_character"})
            continue
        path = Path(processed_dir) / f"U+{ord(character):04X}" / f"v{variant:02d}.json"
        if not path.exists():
            skipped.append({"character": character, "reason": "reference_not_found"})
            continue
        try:
            sample = json.loads(path.read_text(encoding="utf-8-sig"))
            results.append(compare_character_geometry(sample, generated_document, record))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            skipped.append({"character": character, "reason": str(error)})

    averages = {
        name: round(mean(item["scores"][name] for item in results), 6)
        for name in (
            "global_shape_score",
            "ordered_stroke_score",
            "stroke_count_score",
            "aspect_ratio_score",
            "direction_score",
        )
    } if results else {}
    diagnosis = build_report_diagnosis(results)
    running_script_scores = [item["running_script_score"] for item in results]
    strict_kaishu_scores = [item["strict_kaishu_score"] for item in results]
    return {
        "schema_version": SIMILARITY_SCHEMA_VERSION,
        "type": "handwriting_geometry_similarity_report",
        "writer_id": generated_document.get("user_id"),
        "generated_document_sha256": _document_fingerprint(generated_document),
        "reference_variant": variant,
        "requested_character_count": len(records),
        "evaluated_character_count": len(results),
        "skipped_character_count": len(skipped),
        "summary": {
            "overall_score_mean": round(
                mean(item["overall_score"] for item in results), 6
            ) if results else None,
            "strict_kaishu_score_mean": round(mean(strict_kaishu_scores), 6)
            if strict_kaishu_scores
            else None,
            "running_script_score_mean": round(mean(running_script_scores), 6)
            if running_script_scores
            else None,
            "metric_means": averages,
            "interpretation": "Use running_script_score for natural handwriting similarity. Strict kaishu score is retained for skeleton diagnostics only.",
        },
        "characters": results,
        "skipped": skipped,
        "diagnosis": diagnosis,
        "method": {
            "normalization": "uniform bounding-box centering per character",
            "weights": {
                "strict_kaishu": {
                    "global_shape_score": 0.35,
                    "ordered_stroke_score": 0.30,
                    "stroke_count_score": 0.15,
                    "aspect_ratio_score": 0.10,
                    "direction_score": 0.10,
                },
                "running_script": {
                    "global_shape_score": 0.65,
                    "aspect_ratio_score": 0.15,
                    "direction_score": 0.20,
                },
            },
            "limitations": [
                "This baseline does not measure readability or semantic correctness.",
                "Strict ordered-stroke score is zero when reference and generated stroke counts differ.",
                "Running-script score tolerates stroke joining but does not yet model the connection trajectory itself.",
                "Use the same dataset and settings when comparing generator versions.",
            ],
        },
    }
