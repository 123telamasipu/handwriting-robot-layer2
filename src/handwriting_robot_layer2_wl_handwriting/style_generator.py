from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .skeleton import analyze_skeleton_coverage, skeleton_by_character


STYLE_GENERATOR_VERSION = "1.0"


@dataclass(frozen=True)
class StyleGenerationOptions:
    char_width_mm: float = 8.0
    char_height_mm: float = 8.0
    char_spacing_mm: float = 1.2
    random_seed: int = 0
    variation_strength: float = 0.35
    curvature_strength: float = 1.0
    glyph_occupancy: float = 0.78
    skeleton_resample_spacing: float = 0.025

    def validate(self) -> None:
        if self.char_width_mm <= 0.0 or self.char_height_mm <= 0.0:
            raise ValueError("character width and height must be positive")
        if self.char_spacing_mm < 0.0:
            raise ValueError("character spacing cannot be negative")
        if not 0.0 <= self.variation_strength <= 2.0:
            raise ValueError("variation_strength must be between 0 and 2")
        if not 0.0 <= self.curvature_strength <= 2.0:
            raise ValueError("curvature_strength must be between 0 and 2")
        if not 0.2 <= self.glyph_occupancy <= 1.0:
            raise ValueError("glyph_occupancy must be between 0.2 and 1")
        if not 0.002 <= self.skeleton_resample_spacing <= 0.2:
            raise ValueError(
                "skeleton_resample_spacing must be between 0.002 and 0.2"
            )


def _finite_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _stable_rng(seed: int, character: str, index: int, purpose: str) -> random.Random:
    value = f"{seed}:{character}:{index}:{purpose}".encode("utf-8")
    digest = hashlib.sha256(value).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _profile_value(
    profile: Dict[str, Any], section: str, field: str, default: float
) -> float:
    value = profile.get("generation_priors", {}).get(section, {}).get(field, default)
    if value is None:
        return default
    return _finite_float(value, f"generation_priors.{section}.{field}")


def validate_style_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("style profile must be a JSON object")
    if profile.get("type") != "handwriting_style_profile":
        raise ValueError("style profile type is invalid")
    if profile.get("schema_version") != "1.0":
        raise ValueError("style profile schema_version must be 1.0")
    writer_id = str(profile.get("writer_id", "")).strip()
    if not writer_id:
        raise ValueError("style profile writer_id is required")
    priors = profile.get("generation_priors", {})
    for section in ("layout", "deformation", "motion", "pressure", "variability"):
        if not isinstance(priors.get(section), dict):
            raise ValueError(f"style profile generation_priors.{section} is required")

    capture_width = _profile_value(profile, "layout", "canvas_width", 0.7)
    capture_height = _profile_value(profile, "layout", "canvas_height", 0.7)
    aspect_ratio = _profile_value(
        profile,
        "layout",
        "aspect_ratio",
        capture_width / capture_height,
    )
    center_x = _profile_value(profile, "layout", "center_x", 0.5)
    center_y = _profile_value(profile, "layout", "center_y", 0.5)
    if not 0.02 <= capture_width <= 1.0 or not 0.02 <= capture_height <= 1.0:
        raise ValueError("style profile canvas size is outside the normalized canvas")
    if aspect_ratio <= 0.0:
        raise ValueError("style profile aspect_ratio must be positive")
    if not 0.0 <= center_x <= 1.0 or not 0.0 <= center_y <= 1.0:
        raise ValueError("style profile center is outside the normalized canvas")
    if not profile.get("source", {}).get("processed_sample_fingerprint_sha256"):
        raise ValueError("style profile source fingerprint is required")
    return profile


def load_style_profile(path: Path) -> Dict[str, Any]:
    profile_path = Path(path)
    if not profile_path.exists():
        raise FileNotFoundError(f"style profile not found: {profile_path}")
    return validate_style_profile(
        json.loads(profile_path.read_text(encoding="utf-8"))
    )


def _distance(first: Sequence[float], second: Sequence[float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _resample_polyline(
    points: Sequence[Sequence[float]], spacing: float
) -> List[Tuple[float, float]]:
    if len(points) < 2:
        raise ValueError("skeleton stroke must contain at least two points")
    values = [(float(point[0]), float(point[1])) for point in points]
    cumulative = [0.0]
    for first, second in zip(values, values[1:]):
        cumulative.append(cumulative[-1] + _distance(first, second))
    total = cumulative[-1]
    if total <= 1e-12:
        raise ValueError("skeleton stroke path is too short")
    count = max(2, math.ceil(total / spacing) + 1)
    targets = [total * index / (count - 1) for index in range(count)]
    result = []
    segment = 0
    for target in targets:
        while segment + 1 < len(cumulative) and cumulative[segment + 1] < target:
            segment += 1
        next_segment = min(segment + 1, len(values) - 1)
        segment_length = cumulative[next_segment] - cumulative[segment]
        fraction = (
            0.0
            if segment_length <= 1e-12
            else (target - cumulative[segment]) / segment_length
        )
        result.append(
            (
                values[segment][0]
                + (values[next_segment][0] - values[segment][0]) * fraction,
                values[segment][1]
                + (values[next_segment][1] - values[segment][1]) * fraction,
            )
        )
    return result


def _glyph_bounding_box(glyph: Dict[str, Any]) -> Tuple[float, float, float, float]:
    points = [
        point
        for stroke in glyph.get("strokes", [])
        for point in stroke.get("points", [])
    ]
    if not points:
        raise ValueError("skeleton glyph contains no points")
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if max(x_max - x_min, y_max - y_min) <= 1e-12:
        raise ValueError("skeleton glyph bounding box is too small")
    return x_min, y_min, x_max, y_max


def _normalize_glyph_point(
    point: Sequence[float], bounding_box: Tuple[float, float, float, float]
) -> Tuple[float, float]:
    x_min, y_min, x_max, y_max = bounding_box
    extent = max(x_max - x_min, y_max - y_min)
    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0
    return (
        (float(point[0]) - center_x) / extent,
        (float(point[1]) - center_y) / extent,
    )


def _deform_point(
    x: float,
    y: float,
    vertical_slant_deg: float,
    horizontal_angle_deg: float,
) -> Tuple[float, float]:
    horizontal_slope = math.tan(math.radians(horizontal_angle_deg))
    vertical_slope = -math.tan(math.radians(vertical_slant_deg))
    deformed_y = y + horizontal_slope * x
    deformed_x = x + vertical_slope * y
    return deformed_x, deformed_y


def _normal_vector(
    points: Sequence[Tuple[float, float]], index: int
) -> Tuple[float, float]:
    previous = points[max(0, index - 1)]
    following = points[min(len(points) - 1, index + 1)]
    delta_x = following[0] - previous[0]
    delta_y = following[1] - previous[1]
    length = math.hypot(delta_x, delta_y)
    if length <= 1e-12:
        return 0.0, 0.0
    return -delta_y / length, delta_x / length


def _styled_stroke(
    points: Sequence[Sequence[float]],
    bounding_box: Tuple[float, float, float, float],
    profile: Dict[str, Any],
    options: StyleGenerationOptions,
    rng: random.Random,
    target_width: float,
    target_height: float,
    target_center_x: float,
    target_center_y: float,
    vertical_slant_deg: float,
    horizontal_angle_deg: float,
) -> List[Tuple[float, float]]:
    resampled = _resample_polyline(points, options.skeleton_resample_spacing)
    normalized = [
        _normalize_glyph_point(point, bounding_box) for point in resampled
    ]
    deformed = [
        _deform_point(
            point[0],
            point[1],
            vertical_slant_deg,
            horizontal_angle_deg,
        )
        for point in normalized
    ]

    straightness = _clamp(
        _profile_value(profile, "deformation", "straightness", 0.75),
        0.0,
        1.0,
    )
    base_curve = (1.0 - straightness) * 0.022 * options.curvature_strength
    curve_amplitude = base_curve * rng.uniform(-1.0, 1.0)
    second_amplitude = base_curve * 0.4 * rng.uniform(-1.0, 1.0)
    styled = []
    last_index = max(1, len(deformed) - 1)
    for index, (x, y) in enumerate(deformed):
        fraction = index / last_index
        normal_x, normal_y = _normal_vector(deformed, index)
        envelope = math.sin(math.pi * fraction)
        displacement = envelope * (
            curve_amplitude * math.sin(math.pi * fraction)
            + second_amplitude * math.sin(2.0 * math.pi * fraction)
        )
        x += normal_x * displacement
        y += normal_y * displacement
        canvas_x = target_center_x + x * target_width
        canvas_y = target_center_y + y * target_height
        styled.append(
            (
                _clamp(canvas_x, 0.0, 1.0),
                _clamp(canvas_y, 0.0, 1.0),
            )
        )
    return styled


def _path_length(points: Sequence[Tuple[float, float]]) -> float:
    return sum(_distance(first, second) for first, second in zip(points, points[1:]))


def _character_style_parameters(
    profile: Dict[str, Any],
    options: StyleGenerationOptions,
    character: str,
    character_index: int,
) -> Dict[str, float]:
    rng = _stable_rng(options.random_seed, character, character_index, "layout")
    strength = options.variation_strength
    capture_width = _profile_value(profile, "layout", "canvas_width", 0.7)
    capture_height = _profile_value(profile, "layout", "canvas_height", 0.7)
    aspect_ratio = _profile_value(
        profile,
        "layout",
        "aspect_ratio",
        capture_width / capture_height,
    )
    center_x = _profile_value(profile, "layout", "center_x", 0.5)
    center_y = _profile_value(profile, "layout", "center_y", 0.5)
    width_std = _profile_value(profile, "variability", "canvas_width_std", 0.0)
    height_std = _profile_value(profile, "variability", "canvas_height_std", 0.0)
    center_x_std = _profile_value(profile, "variability", "center_x_std", 0.0)
    center_y_std = _profile_value(profile, "variability", "center_y_std", 0.0)
    vertical_slant = _profile_value(
        profile, "deformation", "vertical_slant_deg", 0.0
    )
    vertical_slant_std = _profile_value(
        profile, "variability", "vertical_slant_std", 0.0
    )
    horizontal_angle = _profile_value(
        profile, "deformation", "horizontal_angle_deg", 0.0
    )
    if aspect_ratio <= 0.0:
        raise ValueError("style profile aspect_ratio must be positive")
    if aspect_ratio <= 1.0:
        base_width = options.glyph_occupancy * aspect_ratio
        base_height = options.glyph_occupancy
    else:
        base_width = options.glyph_occupancy
        base_height = options.glyph_occupancy / aspect_ratio
    width_variation = width_std / max(capture_width, 1e-6)
    height_variation = height_std / max(capture_height, 1e-6)
    parameters = {
        "width": _clamp(
            base_width
            * (1.0 + rng.uniform(-1.0, 1.0) * width_variation * strength),
            0.04,
            0.96,
        ),
        "height": _clamp(
            base_height
            * (1.0 + rng.uniform(-1.0, 1.0) * height_variation * strength),
            0.04,
            0.96,
        ),
        "center_x": _clamp(
            center_x + rng.uniform(-1.0, 1.0) * center_x_std * strength,
            0.02,
            0.98,
        ),
        "center_y": _clamp(
            center_y + rng.uniform(-1.0, 1.0) * center_y_std * strength,
            0.02,
            0.98,
        ),
        "vertical_slant_deg": _clamp(
            vertical_slant
            + rng.uniform(-1.0, 1.0) * vertical_slant_std * strength,
            -25.0,
            25.0,
        ),
        "horizontal_angle_deg": _clamp(
            horizontal_angle
            + rng.uniform(-1.0, 1.0) * vertical_slant_std * 0.35 * strength,
            -25.0,
            25.0,
        ),
    }
    half_width = parameters["width"] / 2.0
    half_height = parameters["height"] / 2.0
    parameters["center_x"] = _clamp(
        parameters["center_x"], half_width, 1.0 - half_width
    )
    parameters["center_y"] = _clamp(
        parameters["center_y"], half_height, 1.0 - half_height
    )
    return parameters


def generate_styled_text(
    text: str,
    skeleton_library: Dict[str, Any],
    style_profile: Dict[str, Any],
    options: Optional[StyleGenerationOptions] = None,
    page_width_mm: float = 210.0,
    page_height_mm: float = 297.0,
    origin_mm: Iterable[float] = (10.0, 10.0),
) -> Dict[str, Any]:
    options = options or StyleGenerationOptions()
    options.validate()
    profile = validate_style_profile(style_profile)
    if not isinstance(text, str) or not text:
        raise ValueError("text must not be empty")
    origin = list(origin_mm)
    if len(origin) != 2:
        raise ValueError("origin_mm must contain x and y")
    origin_x = _finite_float(origin[0], "origin_mm[0]")
    origin_y = _finite_float(origin[1], "origin_mm[1]")
    page_width = _finite_float(page_width_mm, "page_width_mm")
    page_height = _finite_float(page_height_mm, "page_height_mm")
    if page_width <= 0.0 or page_height <= 0.0:
        raise ValueError("page width and height must be positive")

    coverage = analyze_skeleton_coverage(text, skeleton_library)
    if coverage["missing_characters"]:
        missing = "".join(coverage["missing_characters"])
        raise ValueError(f"missing ordered stroke skeletons: {missing}")

    strokes: List[Dict[str, Any]] = []
    timings: List[Dict[str, Any]] = []
    character_records: List[Dict[str, Any]] = []
    cursor_x = origin_x
    order = 1
    non_space_index = 0
    active_speed = max(
        0.01, _profile_value(profile, "motion", "active_speed", 0.8)
    )
    pen_up_pause = max(
        0.0, _profile_value(profile, "motion", "pen_up_pause_mean_ms", 120.0)
    )

    for text_index, character in enumerate(text):
        if character.isspace():
            cursor_x += options.char_width_mm + options.char_spacing_mm
            continue
        glyph = skeleton_by_character(skeleton_library, character)
        if glyph is None:
            raise ValueError(f"missing ordered stroke skeleton: {character}")
        parameters = _character_style_parameters(
            profile, options, character, non_space_index
        )
        bounding_box = _glyph_bounding_box(glyph)
        character_orders = []
        for stroke_index, skeleton_stroke in enumerate(glyph["strokes"]):
            rng = _stable_rng(
                options.random_seed,
                character,
                non_space_index,
                f"stroke:{stroke_index}",
            )
            styled = _styled_stroke(
                skeleton_stroke["points"],
                bounding_box,
                profile,
                options,
                rng,
                parameters["width"],
                parameters["height"],
                parameters["center_x"],
                parameters["center_y"],
                parameters["vertical_slant_deg"],
                parameters["horizontal_angle_deg"],
            )
            millimeter_points = [
                [
                    round(cursor_x + point[0] * options.char_width_mm, 4),
                    round(origin_y + point[1] * options.char_height_mm, 4),
                ]
                for point in styled
            ]
            strokes.append(
                {
                    "points": millimeter_points,
                    "pen_down": True,
                    "order": order,
                }
            )
            normalized_length = _path_length(styled)
            timings.append(
                {
                    "order": order,
                    "character": character,
                    "stroke_type": skeleton_stroke.get("stroke_type", "unknown"),
                    "estimated_duration_ms": round(
                        normalized_length / active_speed * 1000.0
                    ),
                    "pen_up_after_ms": round(pen_up_pause)
                    if stroke_index + 1 < len(glyph["strokes"])
                    else 0,
                }
            )
            character_orders.append(order)
            order += 1
        character_records.append(
            {
                "text_index": text_index,
                "character": character,
                "unicode": glyph["unicode"],
                "stroke_orders": character_orders,
                "style_parameters": {
                    key: round(value, 6) for key, value in parameters.items()
                },
            }
        )
        cursor_x += options.char_width_mm + options.char_spacing_mm
        non_space_index += 1

    maximum_x = max(
        (point[0] for stroke in strokes for point in stroke["points"]),
        default=origin_x,
    )
    maximum_y = max(
        (point[1] for stroke in strokes for point in stroke["points"]),
        default=origin_y,
    )
    warnings = []
    if not skeleton_library.get("authoritative", False):
        warnings.append("non_authoritative_skeleton_library")
    if maximum_x > page_width or maximum_y > page_height:
        warnings.append("trajectory_exceeds_page_bounds")

    return {
        "schema_version": "0.1",
        "type": "stroke_document",
        "source": "handwriting",
        "user_id": profile["writer_id"],
        "page": {"width_mm": page_width, "height_mm": page_height},
        "strokes": strokes,
        "generation": {
            "method": "ordered_skeleton_style_transform",
            "method_version": STYLE_GENERATOR_VERSION,
            "style_profile_fingerprint_sha256": profile["source"][
                "processed_sample_fingerprint_sha256"
            ],
            "skeleton_library": {
                "name": skeleton_library.get("name"),
                "quality_level": skeleton_library.get("quality_level"),
                "authoritative": bool(skeleton_library.get("authoritative", False)),
                "source": skeleton_library.get("source", {}),
                "license": skeleton_library.get("license", {}),
            },
            "options": asdict(options),
            "characters": character_records,
            "motion_hints": {
                "unit": "milliseconds",
                "notes": "Advisory only; the device module must enforce machine limits.",
                "strokes": timings,
            },
            "warnings": warnings,
            "limitations": [
                "This is a deterministic geometric baseline, not a trained handwriting generation model.",
                "Output quality depends on ordered stroke skeleton quality and coverage.",
                "Motion hints are normalized writer-style estimates, not direct machine commands.",
            ],
        },
    }
