from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List

from .models import RecordingBuffer, Stroke, StrokePoint


CAPTURE_SCHEMA_VERSION = "1.0"
MAX_STROKES = 256
MAX_POINTS = 50000
VALID_STATUSES = {"draft", "complete"}
SOURCE_ALIASES = {
    "mouse": "mouse",
    "pen": "pen",
    "stylus": "pen",
    "touch": "touch",
    "tablet": "tablet",
}


def _finite_float(value: Any, field: str, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a number") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    if not minimum <= result <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def normalize_input_source(value: Any) -> str:
    source = str(value or "touch").strip().lower()
    if source not in SOURCE_ALIASES:
        raise ValueError(f"unsupported input source: {source}")
    return SOURCE_ALIASES[source]


def point_from_capture(value: Dict[str, Any]) -> StrokePoint:
    if not isinstance(value, dict):
        raise ValueError("each point must be a JSON object")
    return StrokePoint(
        x=_finite_float(value.get("x"), "point.x"),
        y=_finite_float(value.get("y"), "point.y"),
        t_ms=_bounded_int(value.get("t_ms", 0), "point.t_ms", 0, 86400000),
        pressure=_finite_float(value.get("pressure"), "point.pressure", 0.5),
        x_tilt=_finite_float(
            value.get("x_tilt", value.get("tilt_x")), "point.x_tilt", 0.0
        ),
        y_tilt=_finite_float(
            value.get("y_tilt", value.get("tilt_y")), "point.y_tilt", 0.0
        ),
        rotation=_finite_float(
            value.get("rotation", value.get("twist")), "point.rotation", 0.0
        ),
        tangential_pressure=_finite_float(
            value.get("tangential_pressure"),
            "point.tangential_pressure",
            0.0,
        ),
        source=normalize_input_source(value.get("source")),
    )


def buffer_from_capture(strokes_value: Any) -> RecordingBuffer:
    if not isinstance(strokes_value, list):
        raise ValueError("strokes must be a JSON array")
    if len(strokes_value) > MAX_STROKES:
        raise ValueError(f"strokes cannot contain more than {MAX_STROKES} items")

    strokes: List[Stroke] = []
    point_count = 0
    for stroke_value in strokes_value:
        if not isinstance(stroke_value, dict):
            raise ValueError("each stroke must be a JSON object")
        points_value = stroke_value.get("points", [])
        if not isinstance(points_value, list):
            raise ValueError("stroke.points must be a JSON array")
        point_count += len(points_value)
        if point_count > MAX_POINTS:
            raise ValueError(f"capture cannot contain more than {MAX_POINTS} points")
        points = [point_from_capture(point) for point in points_value]
        if points:
            strokes.append(Stroke(points))

    buffer = RecordingBuffer()
    buffer.replace(strokes)
    return buffer


def sanitize_capture_context(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("client must be a JSON object")

    context: Dict[str, Any] = {
        "application": str(value.get("application", "mobile_web"))[:40],
        "user_agent": str(value.get("user_agent", ""))[:300],
    }
    viewport = value.get("viewport")
    if isinstance(viewport, dict):
        context["viewport"] = {
            "width_px": _bounded_int(
                viewport.get("width_px", 1), "client.viewport.width_px", 1, 20000
            ),
            "height_px": _bounded_int(
                viewport.get("height_px", 1),
                "client.viewport.height_px",
                1,
                20000,
            ),
            "device_pixel_ratio": round(
                min(
                    10.0,
                    max(
                        0.1,
                        _finite_float(
                            viewport.get("device_pixel_ratio"),
                            "client.viewport.device_pixel_ratio",
                            1.0,
                        ),
                    ),
                ),
                3,
            ),
        }
    pointer_types = value.get("pointer_types", [])
    if isinstance(pointer_types, list):
        context["pointer_types"] = sorted(
            {normalize_input_source(item) for item in pointer_types}
        )
    return context


@dataclass(frozen=True)
class CaptureSubmission:
    writer_id: str
    writer_name: str
    character: str
    variant: int
    status: str
    buffer: RecordingBuffer
    capture_context: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "CaptureSubmission":
        if not isinstance(value, dict):
            raise ValueError("capture submission must be a JSON object")
        if value.get("schema_version") != CAPTURE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CAPTURE_SCHEMA_VERSION}"
            )

        writer_id = str(value.get("writer_id", "")).strip()
        if not writer_id:
            raise ValueError("writer_id is required")
        writer_name = str(value.get("writer_name", "")).strip()
        character = str(value.get("character", ""))
        if len(character) != 1:
            raise ValueError("character must contain one Unicode code point")
        variant = _bounded_int(value.get("variant", 1), "variant", 1, 5)
        status = str(value.get("status", "draft")).strip().lower()
        if status not in VALID_STATUSES:
            raise ValueError("status must be draft or complete")

        return cls(
            writer_id=writer_id,
            writer_name=writer_name,
            character=character,
            variant=variant,
            status=status,
            buffer=buffer_from_capture(value.get("strokes", [])),
            capture_context=sanitize_capture_context(value.get("client")),
        )
