from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .charset import CharacterEntry, load_target_charset
from .skeleton import SKELETON_SCHEMA_VERSION, validate_skeleton_library
from .storage import atomic_write_json


HANZI_WRITER_PACKAGE_NAME = "hanzi-writer-data"
HANZI_WRITER_TESTED_VERSION = "2.0.1"
HANZI_WRITER_COORDINATE_EXTENT = 1024.0
NORMALIZED_GLYPH_OCCUPANCY = 0.9


def _finite_coordinate(value: Any, field: str) -> float:
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(coordinate):
        raise ValueError(f"{field} must be finite")
    return coordinate


def locate_hanzi_writer_package(path: Path) -> Path:
    root = Path(path)
    candidates = [root, root / "package"]
    for candidate in candidates:
        if (candidate / "package.json").exists() and (
            candidate / "ARPHICPL.TXT"
        ).exists():
            return candidate
    raise FileNotFoundError(
        f"Hanzi Writer Data package.json and ARPHICPL.TXT not found: {root}"
    )


def read_hanzi_writer_metadata(package_dir: Path) -> Dict[str, Any]:
    package_dir = locate_hanzi_writer_package(package_dir)
    package = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != HANZI_WRITER_PACKAGE_NAME:
        raise ValueError("unexpected Hanzi Writer Data package name")
    version = str(package.get("version", "")).strip()
    if not version:
        raise ValueError("Hanzi Writer Data package version is missing")
    license_text = (package_dir / "ARPHICPL.TXT").read_text(encoding="utf-8")
    if "ARPHIC PUBLIC LICENSE" not in license_text:
        raise ValueError("ARPHICPL.TXT does not contain the expected license")
    return {
        "package_dir": package_dir,
        "name": package["name"],
        "version": version,
        "tested_version": HANZI_WRITER_TESTED_VERSION,
        "license_name": "Arphic Public License",
        "license_file": "ARPHICPL.TXT",
        "repository": str(package.get("repository", "")),
        "description": str(package.get("description", "")),
    }


def _character_path(package_dir: Path, character: str) -> Path:
    return Path(package_dir) / f"{character}.json"


def convert_hanzi_writer_character(
    character: str, source_document: Dict[str, Any]
) -> Dict[str, Any]:
    if len(character) != 1:
        raise ValueError("character must contain one Unicode code point")
    medians = source_document.get("medians")
    strokes = source_document.get("strokes")
    if not isinstance(medians, list) or not medians:
        raise ValueError(f"Hanzi Writer character has no medians: {character}")
    if not isinstance(strokes, list) or len(strokes) != len(medians):
        raise ValueError(f"Hanzi Writer stroke and median counts differ: {character}")

    raw_strokes = []
    for stroke_index, median in enumerate(medians, start=1):
        if not isinstance(median, list) or len(median) < 2:
            raise ValueError(
                f"Hanzi Writer median needs at least two points: {character}"
            )
        points = []
        for point_index, point in enumerate(median):
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Hanzi Writer median point must be [x, y]")
            x = _finite_coordinate(
                point[0], f"{character}.medians[{stroke_index - 1}][{point_index}].x"
            )
            source_y = _finite_coordinate(
                point[1], f"{character}.medians[{stroke_index - 1}][{point_index}].y"
            )
            points.append([x, -source_y])
        raw_strokes.append(
            {
                "order": stroke_index,
                "stroke_type": "unknown",
                "points": points,
            }
        )

    all_points = [
        point for stroke in raw_strokes for point in stroke["points"]
    ]
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    extent = max(x_max - x_min, y_max - y_min)
    if extent <= 1e-12:
        raise ValueError(f"Hanzi Writer medians have no spatial extent: {character}")
    center_x = (x_min + x_max) / 2.0
    center_y = (y_min + y_max) / 2.0
    scale = NORMALIZED_GLYPH_OCCUPANCY / extent
    converted_strokes = []
    for stroke in raw_strokes:
        converted_strokes.append(
            {
                "order": stroke["order"],
                "stroke_type": stroke["stroke_type"],
                "points": [
                    [
                        round((point[0] - center_x) * scale + 0.5, 6),
                        round((point[1] - center_y) * scale + 0.5, 6),
                    ]
                    for point in stroke["points"]
                ],
            }
        )
    return {
        "character": character,
        "unicode": f"U+{ord(character):04X}",
        "stroke_count": len(converted_strokes),
        "strokes": converted_strokes,
        "notes": (
            "Converted from Hanzi Writer Data medians with uniform bounding-box "
            "normalization; stroke_type is not provided."
        ),
    }


def load_hanzi_writer_glyph(package_dir: Path, character: str) -> Dict[str, Any]:
    package_dir = locate_hanzi_writer_package(package_dir)
    path = _character_path(package_dir, character)
    if not path.exists():
        raise FileNotFoundError(f"Hanzi Writer character not found: {character}")
    source = json.loads(path.read_text(encoding="utf-8"))
    return convert_hanzi_writer_character(character, source)


def build_hanzi_writer_library(
    package_dir: Path,
    characters: Iterable[str],
) -> Dict[str, Any]:
    metadata = read_hanzi_writer_metadata(package_dir)
    requested = list(dict.fromkeys(characters))
    if not requested:
        raise ValueError("at least one Hanzi Writer character is required")
    glyphs = [
        load_hanzi_writer_glyph(metadata["package_dir"], character)
        for character in requested
    ]
    library = {
        "schema_version": SKELETON_SCHEMA_VERSION,
        "type": "ordered_stroke_skeleton_library",
        "name": f"hanzi_writer_data_{metadata['version']}",
        "description": (
            "Ordered centerline strokes converted at runtime from Hanzi Writer Data "
            "medians. The source data is derived from Make Me a Hanzi."
        ),
        "quality_level": "third_party_ordered_medians",
        "authoritative": False,
        "source": {
            "name": f"Hanzi Writer Data {metadata['version']}",
            "url": "https://www.npmjs.com/package/hanzi-writer-data",
            "notes": (
                "Converted from medians. The source package and ARPHICPL.TXT must "
                "remain available when redistributing derived data."
            ),
        },
        "license": {
            "name": metadata["license_name"],
            "url": (
                "https://raw.githubusercontent.com/chanind/hanzi-writer-data/"
                "master/ARPHICPL.TXT"
            ),
        },
        "coordinate_system": {
            "type": "glyph_normalized",
            "origin": "top-left",
            "x_range": [0.0, 1.0],
            "y_range": [0.0, 1.0],
        },
        "glyphs": glyphs,
    }
    return validate_skeleton_library(library)


def build_hanzi_writer_coverage_report(
    package_dir: Path,
    entries: Optional[Iterable[CharacterEntry]] = None,
) -> Dict[str, Any]:
    metadata = read_hanzi_writer_metadata(package_dir)
    entries = list(entries) if entries is not None else load_target_charset()
    categories: Dict[str, Dict[str, Any]] = {}
    missing_entries = []
    invalid_entries = []
    available_count = 0
    for entry in entries:
        category = categories.setdefault(
            entry.category,
            {
                "target_count": 0,
                "available_count": 0,
                "missing_characters": [],
                "invalid_characters": [],
            },
        )
        category["target_count"] += 1
        path = _character_path(metadata["package_dir"], entry.character)
        if not path.exists():
            category["missing_characters"].append(entry.character)
            missing_entries.append(entry.character)
            continue
        try:
            load_hanzi_writer_glyph(metadata["package_dir"], entry.character)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            category["invalid_characters"].append(entry.character)
            invalid_entries.append(
                {"character": entry.character, "error": str(error)}
            )
            continue
        category["available_count"] += 1
        available_count += 1

    for category in categories.values():
        target_count = category["target_count"]
        category["coverage"] = round(
            category["available_count"] / target_count if target_count else 1.0,
            6,
        )
        category["missing_count"] = len(category["missing_characters"])
        category["invalid_count"] = len(category["invalid_characters"])

    hanzi_categories = {"hanzi_frequency", "hanzi_domain"}
    hanzi_entries = [entry for entry in entries if entry.category in hanzi_categories]
    hanzi_available = sum(
        categories.get(category, {}).get("available_count", 0)
        for category in hanzi_categories
    )
    return {
        "schema_version": "1.0",
        "type": "hanzi_writer_coverage_report",
        "source": {
            "package": metadata["name"],
            "version": metadata["version"],
            "tested_version": metadata["tested_version"],
            "license": metadata["license_name"],
            "license_file": metadata["license_file"],
            "repository": metadata["repository"],
        },
        "target_count": len(entries),
        "available_count": available_count,
        "coverage": round(available_count / len(entries) if entries else 1.0, 6),
        "hanzi_target_count": len(hanzi_entries),
        "hanzi_available_count": hanzi_available,
        "hanzi_coverage": round(
            hanzi_available / len(hanzi_entries) if hanzi_entries else 1.0,
            6,
        ),
        "missing_characters": missing_entries,
        "invalid_characters": invalid_entries,
        "categories": categories,
        "integration_policy": {
            "runtime_only_source_data": True,
            "commit_third_party_dataset": False,
            "retain_license_file": True,
            "derived_dataset_redistribution_requires_license_review": True,
        },
    }


def write_hanzi_writer_coverage_report(
    package_dir: Path,
    output_path: Path,
    entries: Optional[Iterable[CharacterEntry]] = None,
) -> Dict[str, Any]:
    report = build_hanzi_writer_coverage_report(package_dir, entries=entries)
    atomic_write_json(Path(output_path), report)
    return report
