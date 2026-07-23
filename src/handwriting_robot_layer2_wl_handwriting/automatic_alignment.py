from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .alignment_review import RELATION_TYPES
from .hanzi_writer_adapter import build_hanzi_writer_library
from .skeleton import skeleton_by_character
from .storage import atomic_write_json


AUTOMATIC_ALIGNMENT_SCHEMA_VERSION = "1.0"
Point = Tuple[float, float]


@dataclass(frozen=True)
class AutomaticAlignmentOptions:
    maximum_group_size: int = 2
    samples_per_stroke: int = 20
    merge_gap_penalty: float = 0.18
    relation_complexity_penalty: float = 0.04
    medium_cost_threshold: float = 0.34
    low_cost_threshold: float = 0.52
    high_margin_threshold: float = 0.08
    medium_margin_threshold: float = 0.025

    def validate(self) -> None:
        if self.maximum_group_size < 1 or self.maximum_group_size > 3:
            raise ValueError("maximum_group_size must be between 1 and 3")
        if self.samples_per_stroke < 4:
            raise ValueError("samples_per_stroke must be at least 4")
        for name, value in (
            ("merge_gap_penalty", self.merge_gap_penalty),
            ("relation_complexity_penalty", self.relation_complexity_penalty),
            ("medium_cost_threshold", self.medium_cost_threshold),
            ("low_cost_threshold", self.low_cost_threshold),
            ("high_margin_threshold", self.high_margin_threshold),
            ("medium_margin_threshold", self.medium_margin_threshold),
        ):
            if value < 0.0 or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite non-negative value")
        if self.medium_cost_threshold > self.low_cost_threshold:
            raise ValueError("medium_cost_threshold cannot exceed low_cost_threshold")
        if self.medium_margin_threshold > self.high_margin_threshold:
            raise ValueError("medium_margin_threshold cannot exceed high_margin_threshold")


def _canonical_hash(document: Dict[str, Any]) -> str:
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _observed_strokes(document: Dict[str, Any]) -> List[List[Point]]:
    if document.get("type") != "processed_handwriting_sample":
        raise ValueError("automatic alignment requires a processed handwriting sample")
    result = []
    for stroke in document.get("representations", {}).get("glyph", {}).get("strokes", []):
        points = [
            (float(point["x"]), float(point["y"]))
            for point in stroke.get("points", [])
        ]
        if len(points) < 2:
            raise ValueError("each observed stroke must contain at least two points")
        result.append(points)
    if not result:
        raise ValueError("processed sample has no observed strokes")
    return result


def _standard_strokes(glyph: Dict[str, Any]) -> List[List[Point]]:
    result = []
    for stroke in glyph.get("strokes", []):
        points = [(float(point[0]), float(point[1])) for point in stroke.get("points", [])]
        if len(points) < 2:
            raise ValueError("each standard stroke must contain at least two points")
        result.append(points)
    return result


def _distance(first: Point, second: Point) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _resample(points: Sequence[Point], count: int) -> List[Point]:
    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _distance(first, second))
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
                points[segment][0]
                + (points[following][0] - points[segment][0]) * fraction,
                points[segment][1]
                + (points[following][1] - points[segment][1]) * fraction,
            )
        )
    return result


def _join_strokes(strokes: Sequence[Sequence[Point]]) -> Tuple[List[Point], float]:
    joined: List[Point] = []
    total_gap = 0.0
    for stroke in strokes:
        if joined:
            total_gap += _distance(joined[-1], stroke[0])
        joined.extend(stroke)
    return joined, total_gap


def _normalize_pair(first: Sequence[Point], second: Sequence[Point]) -> Tuple[List[Point], List[Point]]:
    points = list(first) + list(second)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    extent = max(max(xs) - min(xs), max(ys) - min(ys))
    if extent <= 1e-12:
        raise ValueError("alignment group has no spatial extent")
    center_x = (min(xs) + max(xs)) / 2.0
    center_y = (min(ys) + max(ys)) / 2.0

    def normalize(values: Sequence[Point]) -> List[Point]:
        return [
            ((point[0] - center_x) / extent, (point[1] - center_y) / extent)
            for point in values
        ]

    return normalize(first), normalize(second)


def _path_distance(first: Sequence[Point], second: Sequence[Point], count: int) -> float:
    normalized_first, normalized_second = _normalize_pair(first, second)
    sampled_first = _resample(normalized_first, count)
    sampled_second = _resample(normalized_second, count)
    return mean(_distance(a, b) for a, b in zip(sampled_first, sampled_second))


def _relation(observed_count: int, standard_count: int) -> str:
    relation = (
        "one_to_one"
        if observed_count == 1 and standard_count == 1
        else "observed_joins_standard"
        if observed_count == 1
        else "observed_splits_standard"
        if standard_count == 1
        else "many_to_many"
    )
    if relation not in RELATION_TYPES:
        raise ValueError("automatic alignment produced an invalid relation")
    return relation


def _group_cost(
    observed: Sequence[Sequence[Point]],
    standard: Sequence[Sequence[Point]],
    options: AutomaticAlignmentOptions,
) -> Dict[str, float]:
    observed_path, observed_gap = _join_strokes(observed)
    standard_path, standard_gap = _join_strokes(standard)
    geometry = _path_distance(
        observed_path, standard_path, options.samples_per_stroke * max(len(observed), len(standard))
    )
    gap = abs(observed_gap - standard_gap) * options.merge_gap_penalty
    complexity = (
        len(observed) + len(standard) - 2
    ) * options.relation_complexity_penalty
    return {
        "geometry_cost": geometry,
        "gap_cost": gap,
        "complexity_cost": complexity,
        "total_cost": geometry + gap + complexity,
    }


def _insert_path(paths: List[Dict[str, Any]], candidate: Dict[str, Any], limit: int = 2) -> None:
    signature = tuple(
        (tuple(group["observed_stroke_orders"]), tuple(group["standard_kaishu_stroke_orders"]))
        for group in candidate["groups"]
    )
    if any(path["signature"] == signature for path in paths):
        return
    candidate["signature"] = signature
    paths.append(candidate)
    paths.sort(key=lambda path: path["cost"])
    del paths[limit:]


def align_character_strokes(
    observed_strokes: Sequence[Sequence[Point]],
    standard_strokes: Sequence[Sequence[Point]],
    options: Optional[AutomaticAlignmentOptions] = None,
) -> Dict[str, Any]:
    options = options or AutomaticAlignmentOptions()
    options.validate()
    observed_count = len(observed_strokes)
    standard_count = len(standard_strokes)
    if observed_count < 1 or standard_count < 1:
        raise ValueError("automatic alignment requires strokes on both sides")
    states: Dict[Tuple[int, int], List[Dict[str, Any]]] = {
        (0, 0): [{"cost": 0.0, "groups": [], "signature": ()}]
    }
    for observed_index in range(observed_count + 1):
        for standard_index in range(standard_count + 1):
            current_paths = states.get((observed_index, standard_index), [])
            if not current_paths:
                continue
            for observed_size in range(1, options.maximum_group_size + 1):
                next_observed = observed_index + observed_size
                if next_observed > observed_count:
                    break
                for standard_size in range(1, options.maximum_group_size + 1):
                    next_standard = standard_index + standard_size
                    if next_standard > standard_count:
                        break
                    if observed_count == standard_count and (
                        observed_size != 1 or standard_size != 1
                    ):
                        continue
                    if observed_count < standard_count and observed_size != 1:
                        continue
                    if observed_count > standard_count and standard_size != 1:
                        continue
                    costs = _group_cost(
                        observed_strokes[observed_index:next_observed],
                        standard_strokes[standard_index:next_standard],
                        options,
                    )
                    group = {
                        "observed_stroke_orders": list(
                            range(observed_index + 1, next_observed + 1)
                        ),
                        "standard_kaishu_stroke_orders": list(
                            range(standard_index + 1, next_standard + 1)
                        ),
                        "relation": _relation(observed_size, standard_size),
                        "costs": {key: round(value, 6) for key, value in costs.items()},
                    }
                    target = states.setdefault((next_observed, next_standard), [])
                    for path in current_paths:
                        _insert_path(
                            target,
                            {
                                "cost": path["cost"] + costs["total_cost"],
                                "groups": path["groups"] + [group],
                            },
                        )
    final_paths = states.get((observed_count, standard_count), [])
    if not final_paths:
        raise ValueError("automatic alignment could not cover all strokes")
    best = final_paths[0]
    second_cost = final_paths[1]["cost"] if len(final_paths) > 1 else None
    normalized_cost = best["cost"] / max(observed_count, standard_count)
    margin = (
        (second_cost - best["cost"]) / max(1, len(best["groups"]))
        if second_cost is not None
        else 1.0
    )
    unique_path = second_cost is None
    if normalized_cost <= options.medium_cost_threshold and (
        unique_path or margin >= options.high_margin_threshold
    ):
        confidence = "high"
    elif (
        normalized_cost <= options.low_cost_threshold
        and (unique_path or margin >= options.medium_margin_threshold)
    ):
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "observed_stroke_count": observed_count,
        "standard_kaishu_stroke_count": standard_count,
        "alignment_groups": best["groups"],
        "total_cost": round(best["cost"], 6),
        "normalized_cost": round(normalized_cost, 6),
        "second_best_total_cost": round(second_cost, 6) if second_cost is not None else None,
        "path_margin_per_group": round(margin, 6),
        "unique_order_preserving_path": unique_path,
        "confidence": confidence,
        "requires_optional_review": confidence == "low",
    }


def build_automatic_alignment_profile(
    processed_dir: Path,
    hanzi_writer_package_dir: Path,
    output_path: Optional[Path] = None,
    options: Optional[AutomaticAlignmentOptions] = None,
) -> Dict[str, Any]:
    options = options or AutomaticAlignmentOptions()
    options.validate()
    paths = sorted(Path(processed_dir).glob("U+*/v*.json"))
    if not paths:
        raise ValueError(f"no processed handwriting samples found: {processed_dir}")
    documents = [json.loads(path.read_text(encoding="utf-8-sig")) for path in paths]
    characters = [str(document.get("character", {}).get("value", "")) for document in documents]
    if any(len(character) != 1 for character in characters):
        raise ValueError("processed sample character metadata is incomplete")
    library = build_hanzi_writer_library(Path(hanzi_writer_package_dir), characters)
    results = []
    writer_ids = set()
    for document in documents:
        character = str(document["character"]["value"])
        writer_id = str(document.get("writer", {}).get("id", "")).strip()
        if not writer_id:
            raise ValueError("processed sample writer id is missing")
        writer_ids.add(writer_id)
        glyph = skeleton_by_character(library, character)
        if glyph is None:
            raise ValueError(f"standard skeleton is missing: {character}")
        alignment = align_character_strokes(
            _observed_strokes(document), _standard_strokes(glyph), options
        )
        results.append(
            {
                "character": character,
                "unicode": f"U+{ord(character):04X}",
                "variant": int(document.get("variant", 1)),
                "source_processed_sample_sha256": _canonical_hash(document),
                **alignment,
            }
        )
    if len(writer_ids) != 1:
        raise ValueError("processed samples must belong to one writer")
    confidence_counts = {
        confidence: sum(result["confidence"] == confidence for result in results)
        for confidence in ("high", "medium", "low")
    }
    auto_accepted = [
        result["character"] for result in results if result["confidence"] != "low"
    ]
    optional_review = [
        result["character"] for result in results if result["confidence"] == "low"
    ]
    relation_counts = {relation: 0 for relation in sorted(RELATION_TYPES)}
    for result in results:
        for group in result["alignment_groups"]:
            relation_counts[group["relation"]] += 1
    profile = {
        "schema_version": AUTOMATIC_ALIGNMENT_SCHEMA_VERSION,
        "type": "automatic_running_script_alignment_profile",
        "writer_id": next(iter(writer_ids)),
        "sample_count": len(results),
        "method": {
            "name": "ordered_dynamic_programming_alignment",
            "transition_policy": (
                "one_to_one plus one-sided contiguous joins or splits; "
                "many-to-many transitions disabled"
            ),
            "options": asdict(options),
            "standard_reference": library.get("source", {}),
            "skeleton_license": library.get("license", {}),
        },
        "summary": {
            "confidence_counts": confidence_counts,
            "profile_ready_count": len(results),
            "auto_accepted_count": len(auto_accepted),
            "enhanced_alignment_count": len(auto_accepted),
            "optional_review_count": len(optional_review),
            "auto_accepted_characters": auto_accepted,
            "optional_review_characters": optional_review,
            "relation_counts": relation_counts,
        },
        "characters": results,
        "policy": {
            "manual_review_required_for_profile_creation": False,
            "all_characters_available_without_review": True,
            "high_and_medium_alignments_auto_accepted": True,
            "low_confidence_review_is_optional": True,
            "low_confidence_fallback": "standard_skeleton_without_learned_ligature",
            "alignment_enables_ligature_generation": False,
        },
        "limitations": [
            "Alignment is geometric and order-preserving; it does not identify calligraphic stroke names.",
            "Auto-accepted alignment describes correspondence but does not create a safe ligature curve.",
            "Low-confidence characters remain usable through the non-ligature standard skeleton baseline.",
        ],
    }
    if output_path is not None:
        atomic_write_json(Path(output_path), profile)
    return profile
