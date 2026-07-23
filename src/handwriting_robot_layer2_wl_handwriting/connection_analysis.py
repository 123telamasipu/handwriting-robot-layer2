from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .storage import atomic_write_json


CONNECTION_ANALYSIS_SCHEMA_VERSION = "1.0"
Point = Tuple[float, float]


@dataclass(frozen=True)
class ConnectionAnalysisOptions:
    maximum_endpoint_distance: float = 0.12
    maximum_pen_up_pause_ms: int = 120
    maximum_exit_turn_deg: float = 60.0
    maximum_entry_turn_deg: float = 90.0
    tangent_point_window: int = 5

    def validate(self) -> None:
        if not 0.0 < self.maximum_endpoint_distance <= 1.0:
            raise ValueError("maximum_endpoint_distance must be between 0 and 1")
        if self.maximum_pen_up_pause_ms < 1:
            raise ValueError("maximum_pen_up_pause_ms must be positive")
        for name, value in (
            ("maximum_exit_turn_deg", self.maximum_exit_turn_deg),
            ("maximum_entry_turn_deg", self.maximum_entry_turn_deg),
        ):
            if not 0.0 < value <= 180.0:
                raise ValueError(f"{name} must be between 0 and 180")
        if self.tangent_point_window < 1:
            raise ValueError("tangent_point_window must be at least 1")


def _finite(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _xy(point: Dict[str, Any]) -> Point:
    return _finite(point.get("x"), "point.x"), _finite(point.get("y"), "point.y")


def _vector(first: Point, second: Point) -> Point:
    return second[0] - first[0], second[1] - first[1]


def _length(vector: Point) -> float:
    return math.hypot(vector[0], vector[1])


def _turn_degrees(first: Point, second: Point) -> Optional[float]:
    if _length(first) <= 1e-12 or _length(second) <= 1e-12:
        return None
    first_angle = math.atan2(first[1], first[0])
    second_angle = math.atan2(second[1], second[0])
    difference = math.atan2(
        math.sin(second_angle - first_angle), math.cos(second_angle - first_angle)
    )
    return abs(math.degrees(difference))


def _tangent(points: Sequence[Dict[str, Any]], at_end: bool, window: int) -> Point:
    if len(points) < 2:
        return 0.0, 0.0
    if at_end:
        first = _xy(points[max(0, len(points) - 1 - window)])
        second = _xy(points[-1])
    else:
        first = _xy(points[0])
        second = _xy(points[min(len(points) - 1, window)])
    return _vector(first, second)


def _score(value: float, maximum: float) -> float:
    return max(0.0, 1.0 - value / maximum)


def _expected_stroke_count(document: Dict[str, Any]) -> Optional[int]:
    value = document.get("character", {}).get("expected_stroke_count")
    if value in (None, ""):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("expected stroke count must be an integer") from error
    return count if count > 0 else None


def analyze_sample_connections(
    document: Dict[str, Any],
    options: Optional[ConnectionAnalysisOptions] = None,
) -> Dict[str, Any]:
    options = options or ConnectionAnalysisOptions()
    options.validate()
    if document.get("type") != "processed_handwriting_sample":
        raise ValueError("connection analysis requires a processed handwriting sample")
    character = str(document.get("character", {}).get("value", ""))
    unicode_value = str(document.get("character", {}).get("unicode", ""))
    writer_id = str(document.get("writer", {}).get("id", "")).strip()
    if len(character) != 1 or not unicode_value or not writer_id:
        raise ValueError("processed sample metadata is incomplete")

    representations = document.get("representations", {})
    glyph_strokes = representations.get("glyph", {}).get("strokes", [])
    dynamics_strokes = representations.get("dynamics", {}).get("strokes", [])
    if not glyph_strokes or len(glyph_strokes) != len(dynamics_strokes):
        raise ValueError("glyph and dynamics stroke counts must match")

    boundaries = []
    for index in range(len(glyph_strokes) - 1):
        current = glyph_strokes[index].get("points", [])
        following = glyph_strokes[index + 1].get("points", [])
        current_dynamics = dynamics_strokes[index].get("points", [])
        following_dynamics = dynamics_strokes[index + 1].get("points", [])
        if min(len(current), len(following), len(current_dynamics), len(following_dynamics)) < 2:
            raise ValueError("each analyzed stroke must contain at least two points")

        end = _xy(current[-1])
        start = _xy(following[0])
        connector = _vector(end, start)
        distance = _length(connector)
        exit_turn = _turn_degrees(
            _tangent(current, True, options.tangent_point_window), connector
        )
        entry_turn = _turn_degrees(
            connector, _tangent(following, False, options.tangent_point_window)
        )
        end_time = int(_finite(current_dynamics[-1].get("t_ms", 0), "point.t_ms"))
        start_time = int(
            _finite(following_dynamics[0].get("t_ms", 0), "point.t_ms")
        )
        pause = max(0, start_time - end_time)
        direction_available = exit_turn is not None and entry_turn is not None
        candidate = (
            direction_available
            and distance <= options.maximum_endpoint_distance
            and pause <= options.maximum_pen_up_pause_ms
            and exit_turn <= options.maximum_exit_turn_deg
            and entry_turn <= options.maximum_entry_turn_deg
        )
        if direction_available:
            candidate_score = mean(
                (
                    _score(distance, options.maximum_endpoint_distance),
                    _score(float(pause), float(options.maximum_pen_up_pause_ms)),
                    _score(exit_turn, options.maximum_exit_turn_deg),
                    _score(entry_turn, options.maximum_entry_turn_deg),
                )
            )
        else:
            candidate_score = 0.0
        confidence = (
            "high"
            if candidate
            and distance <= options.maximum_endpoint_distance * 0.5
            and pause <= options.maximum_pen_up_pause_ms * 0.67
            and exit_turn <= options.maximum_exit_turn_deg * 0.67
            and entry_turn <= options.maximum_entry_turn_deg * 0.67
            else "medium"
            if candidate
            else "not_candidate"
        )
        boundaries.append(
            {
                "from_observed_stroke_order": index + 1,
                "to_observed_stroke_order": index + 2,
                "from_endpoint": [round(end[0], 6), round(end[1], 6)],
                "to_startpoint": [round(start[0], 6), round(start[1], 6)],
                "endpoint_distance": round(distance, 6),
                "pen_up_pause_ms": pause,
                "exit_to_connector_turn_deg": (
                    round(exit_turn, 3) if exit_turn is not None else None
                ),
                "connector_to_entry_turn_deg": (
                    round(entry_turn, 3) if entry_turn is not None else None
                ),
                "candidate": candidate,
                "candidate_score": round(candidate_score, 6),
                "confidence": confidence,
                "safety_status": "analysis_only_no_pen_down_path",
            }
        )

    expected = _expected_stroke_count(document)
    observed = len(glyph_strokes)
    return {
        "character": character,
        "unicode": unicode_value,
        "writer_id": writer_id,
        "variant": int(document.get("variant", 1)),
        "standard_kaishu_stroke_count": expected,
        "observed_pen_down_stroke_count": observed,
        "script_interpretation": (
            "observed_strokes_join_standard_kaishu_strokes"
            if expected is not None and observed < expected
            else "observed_strokes_split_standard_kaishu_strokes"
            if expected is not None and observed > expected
            else "same_stroke_count_or_unknown"
        ),
        "boundary_count": len(boundaries),
        "candidate_count": sum(boundary["candidate"] for boundary in boundaries),
        "boundaries": boundaries,
    }


def _distribution(values: Iterable[float]) -> Dict[str, Optional[float]]:
    items = sorted(float(value) for value in values)
    if not items:
        return {"minimum": None, "median": None, "mean": None, "maximum": None}
    return {
        "minimum": round(items[0], 6),
        "median": round(median(items), 6),
        "mean": round(mean(items), 6),
        "maximum": round(items[-1], 6),
    }


def build_connection_candidate_report(
    processed_dir: Path,
    output_path: Optional[Path] = None,
    options: Optional[ConnectionAnalysisOptions] = None,
) -> Dict[str, Any]:
    options = options or ConnectionAnalysisOptions()
    options.validate()
    paths = sorted(Path(processed_dir).glob("U+*/v*.json"))
    if not paths:
        raise ValueError(f"no processed handwriting samples found: {processed_dir}")
    samples = [
        analyze_sample_connections(
            json.loads(path.read_text(encoding="utf-8-sig")), options
        )
        for path in paths
    ]
    writer_ids = {sample["writer_id"] for sample in samples}
    if len(writer_ids) != 1:
        raise ValueError("processed samples must belong to one writer")
    boundaries = [
        {"character": sample["character"], **boundary}
        for sample in samples
        for boundary in sample["boundaries"]
    ]
    candidates = sorted(
        (boundary for boundary in boundaries if boundary["candidate"]),
        key=lambda boundary: (-boundary["candidate_score"], boundary["character"]),
    )
    joined_characters = [
        sample["character"]
        for sample in samples
        if sample["script_interpretation"]
        == "observed_strokes_join_standard_kaishu_strokes"
    ]
    split_characters = [
        sample["character"]
        for sample in samples
        if sample["script_interpretation"]
        == "observed_strokes_split_standard_kaishu_strokes"
    ]
    report = {
        "schema_version": CONNECTION_ANALYSIS_SCHEMA_VERSION,
        "type": "running_script_connection_candidate_report",
        "writer_id": next(iter(writer_ids)),
        "sample_count": len(samples),
        "boundary_count": len(boundaries),
        "candidate_count": len(candidates),
        "candidate_rate": round(len(candidates) / len(boundaries), 6)
        if boundaries
        else 0.0,
        "options": asdict(options),
        "script_behavior": {
            "joined_stroke_character_count": len(joined_characters),
            "joined_stroke_characters": joined_characters,
            "split_stroke_character_count": len(split_characters),
            "split_stroke_characters": split_characters,
        },
        "boundary_statistics": {
            "endpoint_distance": _distribution(
                boundary["endpoint_distance"] for boundary in boundaries
            ),
            "pen_up_pause_ms": _distribution(
                boundary["pen_up_pause_ms"] for boundary in boundaries
            ),
            "exit_to_connector_turn_deg": _distribution(
                boundary["exit_to_connector_turn_deg"]
                for boundary in boundaries
                if boundary["exit_to_connector_turn_deg"] is not None
            ),
            "connector_to_entry_turn_deg": _distribution(
                boundary["connector_to_entry_turn_deg"]
                for boundary in boundaries
                if boundary["connector_to_entry_turn_deg"] is not None
            ),
        },
        "candidates": candidates,
        "samples": samples,
        "safety": {
            "mode": "analysis_only",
            "generates_pen_down_connections": False,
            "notes": [
                "A candidate is not proof that two standard strokes may be joined.",
                "The report does not align observed strokes to semantic standard-stroke labels.",
                "Do not convert candidate endpoint pairs directly into writing-machine paths.",
            ],
        },
    }
    if output_path is not None:
        atomic_write_json(Path(output_path), report)
    return report
