from __future__ import annotations

import json
import math
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional


SKELETON_SCHEMA_VERSION = "1.0"


def default_demo_skeleton_path() -> Path:
    return Path(
        resources.files(__package__).joinpath(
            "resources/demo_ordered_stroke_skeletons.json"
        )
    )


def _finite_coordinate(value: Any, field: str) -> float:
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(coordinate):
        raise ValueError(f"{field} must be finite")
    if not 0.0 <= coordinate <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return round(coordinate, 6)


def validate_skeleton_library(document: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("skeleton library must be a JSON object")
    if document.get("schema_version") != SKELETON_SCHEMA_VERSION:
        raise ValueError(
            f"skeleton library schema_version must be {SKELETON_SCHEMA_VERSION}"
        )
    if document.get("type") != "ordered_stroke_skeleton_library":
        raise ValueError("skeleton library type is invalid")

    name = str(document.get("name", "")).strip()
    if not name:
        raise ValueError("skeleton library name is required")
    source = document.get("source", {})
    license_value = document.get("license", {})
    if not isinstance(source, dict) or not str(source.get("name", "")).strip():
        raise ValueError("skeleton library source.name is required")
    if not isinstance(license_value, dict) or not str(
        license_value.get("name", "")
    ).strip():
        raise ValueError("skeleton library license.name is required")

    coordinate_system = document.get("coordinate_system", {})
    if coordinate_system.get("type") != "glyph_normalized":
        raise ValueError("skeleton coordinates must use glyph_normalized")
    if coordinate_system.get("origin") != "top-left":
        raise ValueError("skeleton coordinate origin must be top-left")

    glyphs = document.get("glyphs", [])
    if not isinstance(glyphs, list) or not glyphs:
        raise ValueError("skeleton library must contain glyphs")
    normalized_glyphs: List[Dict[str, Any]] = []
    seen_characters = set()
    for glyph_index, glyph in enumerate(glyphs):
        if not isinstance(glyph, dict):
            raise ValueError("each skeleton glyph must be a JSON object")
        character = str(glyph.get("character", ""))
        if len(character) != 1:
            raise ValueError("skeleton glyph character must contain one code point")
        if character in seen_characters:
            raise ValueError(f"duplicate skeleton character: {character}")
        seen_characters.add(character)
        unicode_value = str(glyph.get("unicode", ""))
        expected_unicode = f"U+{ord(character):04X}"
        if unicode_value != expected_unicode:
            raise ValueError(
                f"skeleton unicode mismatch for {character}: expected {expected_unicode}"
            )
        strokes = glyph.get("strokes", [])
        if not isinstance(strokes, list) or not strokes:
            raise ValueError(f"skeleton glyph has no strokes: {character}")
        if int(glyph.get("stroke_count", -1)) != len(strokes):
            raise ValueError(f"skeleton stroke_count mismatch: {character}")

        normalized_strokes = []
        for stroke_index, stroke in enumerate(strokes, start=1):
            if not isinstance(stroke, dict):
                raise ValueError("each skeleton stroke must be a JSON object")
            if int(stroke.get("order", -1)) != stroke_index:
                raise ValueError(
                    f"skeleton stroke order must be consecutive: {character}"
                )
            stroke_type = str(stroke.get("stroke_type", "unknown")).strip()
            if not stroke_type:
                raise ValueError("skeleton stroke_type cannot be empty")
            points = stroke.get("points", [])
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError(
                    f"each skeleton stroke needs at least two points: {character}"
                )
            normalized_points = []
            for point_index, point in enumerate(points):
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("skeleton point must be [x, y]")
                normalized_points.append(
                    [
                        _finite_coordinate(
                            point[0],
                            f"glyphs[{glyph_index}].strokes[{stroke_index - 1}]"
                            f".points[{point_index}].x",
                        ),
                        _finite_coordinate(
                            point[1],
                            f"glyphs[{glyph_index}].strokes[{stroke_index - 1}]"
                            f".points[{point_index}].y",
                        ),
                    ]
                )
            normalized_strokes.append(
                {
                    "order": stroke_index,
                    "stroke_type": stroke_type,
                    "points": normalized_points,
                }
            )
        normalized_glyphs.append(
            {
                "character": character,
                "unicode": unicode_value,
                "stroke_count": len(normalized_strokes),
                "strokes": normalized_strokes,
                "notes": str(glyph.get("notes", "")).strip(),
            }
        )

    return {
        "schema_version": SKELETON_SCHEMA_VERSION,
        "type": "ordered_stroke_skeleton_library",
        "name": name,
        "description": str(document.get("description", "")).strip(),
        "quality_level": str(document.get("quality_level", "unspecified")).strip(),
        "authoritative": bool(document.get("authoritative", False)),
        "source": {
            "name": str(source.get("name", "")).strip(),
            "url": str(source.get("url", "")).strip(),
            "notes": str(source.get("notes", "")).strip(),
        },
        "license": {
            "name": str(license_value.get("name", "")).strip(),
            "url": str(license_value.get("url", "")).strip(),
        },
        "coordinate_system": {
            "type": "glyph_normalized",
            "origin": "top-left",
            "x_range": [0.0, 1.0],
            "y_range": [0.0, 1.0],
        },
        "glyphs": normalized_glyphs,
    }


def load_skeleton_library(path: Optional[Path] = None) -> Dict[str, Any]:
    skeleton_path = Path(path) if path else default_demo_skeleton_path()
    if not skeleton_path.exists():
        raise FileNotFoundError(f"skeleton library not found: {skeleton_path}")
    return validate_skeleton_library(
        json.loads(skeleton_path.read_text(encoding="utf-8"))
    )


def skeleton_by_character(
    library: Dict[str, Any], character: str
) -> Optional[Dict[str, Any]]:
    return next(
        (
            glyph
            for glyph in library.get("glyphs", [])
            if glyph.get("character") == character
        ),
        None,
    )


def analyze_skeleton_coverage(
    text: str, library: Dict[str, Any]
) -> Dict[str, Any]:
    required = list(
        dict.fromkeys(character for character in text if not character.isspace())
    )
    available_set = {
        glyph.get("character") for glyph in library.get("glyphs", [])
    }
    available = [character for character in required if character in available_set]
    missing = [character for character in required if character not in available_set]
    return {
        "required_characters": required,
        "available_characters": available,
        "missing_characters": missing,
        "required_count": len(required),
        "available_count": len(available),
        "coverage": 1.0 if not required else len(available) / len(required),
        "library_name": library.get("name"),
        "library_authoritative": bool(library.get("authoritative", False)),
    }
