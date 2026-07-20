from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class StrokePoint:
    x: float
    y: float
    t_ms: int
    pressure: float = 0.5
    x_tilt: float = 0.0
    y_tilt: float = 0.0
    rotation: float = 0.0
    tangential_pressure: float = 0.0
    source: str = "mouse"

    def __post_init__(self) -> None:
        self.x = min(1.0, max(0.0, float(self.x)))
        self.y = min(1.0, max(0.0, float(self.y)))
        self.pressure = min(1.0, max(0.0, float(self.pressure)))
        self.t_ms = max(0, int(self.t_ms))

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "StrokePoint":
        return cls(**value)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["x"] = round(self.x, 6)
        value["y"] = round(self.y, 6)
        value["pressure"] = round(self.pressure, 4)
        value["x_tilt"] = round(self.x_tilt, 2)
        value["y_tilt"] = round(self.y_tilt, 2)
        value["rotation"] = round(self.rotation, 2)
        value["tangential_pressure"] = round(self.tangential_pressure, 4)
        return value


@dataclass
class Stroke:
    points: List[StrokePoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Stroke":
        return cls([StrokePoint.from_dict(point) for point in value.get("points", [])])

    def to_dict(self) -> Dict[str, Any]:
        return {"points": [point.to_dict() for point in self.points]}


class RecordingBuffer:
    """Framework-independent buffer that preserves pen-down/pen-up boundaries."""

    def __init__(self) -> None:
        self.strokes: List[Stroke] = []
        self._active: Optional[Stroke] = None
        self._clock_origin = time.monotonic()
        self._time_offset_ms = 0

    @property
    def active(self) -> bool:
        return self._active is not None

    @property
    def point_count(self) -> int:
        return sum(len(stroke.points) for stroke in self.strokes) + (
            len(self._active.points) if self._active else 0
        )

    @property
    def duration_ms(self) -> int:
        return max(
            (point.t_ms for point in self.iter_points(include_active=True)), default=0
        )

    def timestamp_ms(self) -> int:
        return self._time_offset_ms + int((time.monotonic() - self._clock_origin) * 1000)

    def begin_stroke(self, point: StrokePoint) -> None:
        if self._active is not None:
            self.end_stroke()
        self._active = Stroke([point])

    def add_point(self, point: StrokePoint, force: bool = False) -> bool:
        if self._active is None:
            return False
        if not force and self._active.points:
            previous = self._active.points[-1]
            if (
                math.hypot(point.x - previous.x, point.y - previous.y) < 0.0008
                and point.t_ms - previous.t_ms < 5
            ):
                return False
        self._active.points.append(point)
        return True

    def end_stroke(self, point: Optional[StrokePoint] = None) -> bool:
        if self._active is None:
            return False
        if point is not None:
            self.add_point(point, force=True)
        if self._active.points:
            self.strokes.append(self._active)
        self._active = None
        return True

    def undo(self) -> bool:
        if self._active is not None:
            self._active = None
            return True
        if not self.strokes:
            return False
        self.strokes.pop()
        return True

    def clear(self) -> None:
        self.strokes.clear()
        self._active = None
        self._reset_clock(0)

    def replace(self, strokes: Iterable[Stroke]) -> None:
        self.strokes = list(strokes)
        self._active = None
        self._reset_clock(self.duration_ms + 1)

    def iter_points(self, include_active: bool = False) -> Iterable[StrokePoint]:
        for stroke in self.strokes:
            yield from stroke.points
        if include_active and self._active:
            yield from self._active.points

    def all_strokes(self, include_active: bool = False) -> List[Stroke]:
        strokes = list(self.strokes)
        if include_active and self._active:
            strokes.append(self._active)
        return strokes

    def bounding_box(self) -> Optional[Dict[str, float]]:
        points = list(self.iter_points(include_active=True))
        if not points:
            return None
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        return {
            "x_min": round(min(xs), 6),
            "y_min": round(min(ys), 6),
            "x_max": round(max(xs), 6),
            "y_max": round(max(ys), 6),
        }

    def sources(self) -> List[str]:
        return sorted({point.source for point in self.iter_points(include_active=True)})

    def _reset_clock(self, offset_ms: int) -> None:
        self._time_offset_ms = max(0, int(offset_ms))
        self._clock_origin = time.monotonic()


def strokes_from_document(document: Dict[str, Any]) -> List[Stroke]:
    return [Stroke.from_dict(value) for value in document.get("strokes", [])]
