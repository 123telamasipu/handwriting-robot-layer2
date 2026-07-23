from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from .hanzi_writer_adapter import build_hanzi_writer_library
from .personal_font_deployment import load_personal_font_deployment_bundle
from .personal_font_profile import file_sha256
from .storage import atomic_write_json
from .style_generator import StyleGenerationOptions, generate_styled_text


MACHINE_HANDOFF_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class MachineHandoffOptions:
    characters_per_scenario: int = 2
    random_seed: int = 23
    max_point_spacing_mm: float = 0.75
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    origin_x_mm: float = 10.0
    origin_y_mm: float = 10.0

    def validate(self) -> None:
        if self.characters_per_scenario < 1 or self.characters_per_scenario > 5:
            raise ValueError("characters_per_scenario must be between 1 and 5")
        if not math.isfinite(self.max_point_spacing_mm) or self.max_point_spacing_mm <= 0:
            raise ValueError("max_point_spacing_mm must be positive")
        for name, value in (
            ("page_width_mm", self.page_width_mm),
            ("page_height_mm", self.page_height_mm),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive")
        for name, value in (
            ("origin_x_mm", self.origin_x_mm),
            ("origin_y_mm", self.origin_y_mm),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be non-negative")


def _finite_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _path_length(points: Sequence[Sequence[float]]) -> float:
    return sum(
        math.hypot(
            float(second[0]) - float(first[0]),
            float(second[1]) - float(first[1]),
        )
        for first, second in zip(points, points[1:])
    )


def validate_stroke_document_preflight(
    document: Dict[str, Any],
    expected_strategies: Optional[Dict[str, str]] = None,
    max_point_spacing_mm: float = 0.75,
) -> Dict[str, Any]:
    if document.get("schema_version") != "0.1":
        raise ValueError("StrokeDocument schema_version must be 0.1")
    if document.get("type") != "stroke_document":
        raise ValueError("handoff artifact must be a StrokeDocument")
    if document.get("source") != "handwriting":
        raise ValueError("handoff StrokeDocument source must be handwriting")
    if not str(document.get("user_id", "")).strip():
        raise ValueError("handoff StrokeDocument user_id is required")
    page = document.get("page", {})
    page_width = _finite_float(page.get("width_mm"), "page.width_mm")
    page_height = _finite_float(page.get("height_mm"), "page.height_mm")
    if page_width <= 0 or page_height <= 0:
        raise ValueError("handoff page dimensions must be positive")
    strokes = document.get("strokes", [])
    if not isinstance(strokes, list) or not strokes:
        raise ValueError("handoff StrokeDocument must contain strokes")

    orders = []
    point_count = 0
    maximum_spacing = 0.0
    total_path_length = 0.0
    xs = []
    ys = []
    for index, stroke in enumerate(strokes, start=1):
        if not isinstance(stroke, dict):
            raise ValueError("handoff stroke must be an object")
        order = int(stroke.get("order", 0))
        orders.append(order)
        if stroke.get("pen_down") is not True:
            raise ValueError("handoff strokes must be explicit pen-down segments")
        points = stroke.get("points", [])
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("each handoff stroke must contain at least two points")
        parsed = []
        for point_index, point in enumerate(points):
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                raise ValueError("handoff point must contain x and y")
            x = _finite_float(point[0], f"strokes[{index}].points[{point_index}].x")
            y = _finite_float(point[1], f"strokes[{index}].points[{point_index}].y")
            if not 0.0 <= x <= page_width or not 0.0 <= y <= page_height:
                raise ValueError("handoff point is outside page bounds")
            parsed.append((x, y))
            xs.append(x)
            ys.append(y)
        for first, second in zip(parsed, parsed[1:]):
            maximum_spacing = max(
                maximum_spacing,
                math.hypot(second[0] - first[0], second[1] - first[1]),
            )
        total_path_length += _path_length(parsed)
        point_count += len(parsed)
    if orders != list(range(1, len(strokes) + 1)):
        raise ValueError("handoff stroke orders must be continuous from 1")
    if maximum_spacing > max_point_spacing_mm:
        raise ValueError(
            "handoff point spacing exceeds software preflight threshold"
        )

    generation = document.get("generation", {})
    characters = generation.get("characters", [])
    if not isinstance(characters, list) or not characters:
        raise ValueError("handoff generation character metadata is required")
    mapped_orders = [
        int(order)
        for character in characters
        for order in character.get("stroke_orders", [])
    ]
    if mapped_orders != orders:
        raise ValueError("handoff character-to-stroke mapping is incomplete")
    if any(character.get("ligature_applied") is not False for character in characters):
        raise ValueError("handoff package cannot contain generated ligatures")
    if expected_strategies is not None:
        actual = {
            str(character.get("character", "")): str(
                character.get("personal_font_strategy", "")
            )
            for character in characters
        }
        if actual != expected_strategies:
            raise ValueError("handoff character strategies do not match selection")

    motion_hints = generation.get("motion_hints", {})
    timing_records = motion_hints.get("strokes", [])
    if len(timing_records) != len(strokes):
        raise ValueError("handoff motion hints must cover every stroke")
    if [int(record.get("order", 0)) for record in timing_records] != orders:
        raise ValueError("handoff motion hint orders are inconsistent")
    durations = []
    pauses = []
    for record in timing_records:
        duration = _finite_float(
            record.get("estimated_duration_ms"), "estimated_duration_ms"
        )
        pause = _finite_float(record.get("pen_up_after_ms"), "pen_up_after_ms")
        if duration <= 0 or pause < 0:
            raise ValueError("handoff motion hints contain invalid timing")
        durations.append(duration)
        pauses.append(pause)
    warnings = generation.get("warnings", [])
    if "trajectory_exceeds_page_bounds" in warnings:
        raise ValueError("handoff generator reported page overflow")
    personal_font = generation.get("personal_font", {})
    deployment = personal_font.get("deployment", {})
    if not deployment.get("policy_fingerprint_sha256"):
        raise ValueError("handoff document must use a verified deployment policy")
    if deployment.get("manual_review_required") is not False:
        raise ValueError("handoff deployment unexpectedly requires manual review")

    return {
        "status": "pass",
        "checks": {
            "schema_and_identity_valid": True,
            "coordinates_finite_and_within_page": True,
            "stroke_orders_continuous": True,
            "character_mapping_complete": True,
            "explicit_pen_down_segments_only": True,
            "no_generated_ligatures": True,
            "motion_hints_complete": True,
            "verified_deployment_policy_used": True,
        },
        "statistics": {
            "character_count": len(characters),
            "stroke_count": len(strokes),
            "point_count": point_count,
            "total_path_length_mm": round(total_path_length, 4),
            "maximum_point_spacing_mm": round(maximum_spacing, 4),
            "estimated_pen_down_duration_ms": round(sum(durations)),
            "advisory_pen_up_pause_ms": round(sum(pauses)),
            "trajectory_bounding_box_mm": {
                "x_min": round(min(xs), 4),
                "y_min": round(min(ys), 4),
                "x_max": round(max(xs), 4),
                "y_max": round(max(ys), 4),
            },
        },
        "scope": (
            "Software interface and geometry preflight only; this is not machine "
            "authorization or a device command."
        ),
    }


def _select_records(
    records: Iterable[Dict[str, Any]],
    count: int,
    descending: bool,
) -> list[Dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            float(record.get("running_script_delta", 0.0)),
            str(record.get("character", "")),
        ),
        reverse=descending,
    )[:count]


def _select_handoff_characters(
    deployment: Dict[str, Any],
    unseen_candidates: str,
    count: int,
) -> Dict[str, list[str]]:
    records = deployment["characters"]
    enhanced = _select_records(
        (
            record
            for record in records
            if record["strategy"] == "automatic_correspondence_features"
        ),
        count,
        descending=True,
    )
    high_fallback = _select_records(
        (
            record
            for record in records
            if record["strategy"] == "safe_standard_skeleton_fallback"
            and record["alignment_confidence"] in {"high", "medium"}
        ),
        count,
        descending=False,
    )
    low_fallback = _select_records(
        (
            record
            for record in records
            if record["strategy"] == "safe_standard_skeleton_fallback"
            and record["alignment_confidence"] == "low"
        ),
        count,
        descending=False,
    )
    captured = {str(record["character"]) for record in records}
    unseen = [
        character
        for character in dict.fromkeys(unseen_candidates)
        if not character.isspace() and character not in captured
    ][:count]
    selections = {
        "enhanced": [record["character"] for record in enhanced],
        "evaluated_fallback": [record["character"] for record in high_fallback],
        "low_confidence_fallback": [record["character"] for record in low_fallback],
        "unseen_global_style": unseen,
    }
    incomplete = [name for name, values in selections.items() if len(values) < count]
    if incomplete:
        raise ValueError(
            "not enough handoff characters for scenarios: " + ", ".join(incomplete)
        )
    return selections


def _expected_strategy(
    character: str,
    deployment_map: Dict[str, Dict[str, Any]],
) -> str:
    record = deployment_map.get(character)
    return (
        str(record["strategy"])
        if record is not None
        else "global_style_unseen_character_fallback"
    )


def build_machine_handoff_package(
    personal_font_deployment_path: Path,
    hanzi_writer_package_dir: Path,
    output_dir: Path,
    unseen_candidates: str = "好世界的字",
    generation_options: Optional[StyleGenerationOptions] = None,
    handoff_options: Optional[MachineHandoffOptions] = None,
) -> Dict[str, Any]:
    handoff_options = handoff_options or MachineHandoffOptions()
    handoff_options.validate()
    base_generation_options = generation_options or StyleGenerationOptions()
    base_generation_options.validate()
    generation_options = StyleGenerationOptions(
        **{
            **asdict(base_generation_options),
            "random_seed": handoff_options.random_seed,
        }
    )
    bundle = load_personal_font_deployment_bundle(
        Path(personal_font_deployment_path)
    )
    deployment = bundle["deployment"]
    selections = _select_handoff_characters(
        deployment,
        unseen_candidates,
        handoff_options.characters_per_scenario,
    )
    mixed = [values[0] for values in selections.values()]
    scenario_characters = {**selections, "mixed_smoke": mixed}
    all_characters = list(
        dict.fromkeys(
            character
            for values in scenario_characters.values()
            for character in values
        )
    )
    skeleton_library = build_hanzi_writer_library(
        Path(hanzi_writer_package_dir), all_characters
    )
    deployment_map = {
        str(record["character"]): record for record in deployment["characters"]
    }
    output_dir = Path(output_dir).resolve()
    artifact_dir = output_dir / "stroke_documents"
    artifacts = {}
    total_strokes = 0
    total_points = 0
    for scenario, characters in scenario_characters.items():
        text = "".join(characters)
        document = generate_styled_text(
            text,
            skeleton_library,
            bundle["style_profile"],
            generation_options,
            page_width_mm=handoff_options.page_width_mm,
            page_height_mm=handoff_options.page_height_mm,
            origin_mm=[handoff_options.origin_x_mm, handoff_options.origin_y_mm],
            personal_font_bundle=bundle,
        )
        expected_strategies = {
            character: _expected_strategy(character, deployment_map)
            for character in characters
        }
        preflight = validate_stroke_document_preflight(
            document,
            expected_strategies=expected_strategies,
            max_point_spacing_mm=handoff_options.max_point_spacing_mm,
        )
        artifact_path = artifact_dir / f"{scenario}.json"
        atomic_write_json(artifact_path, document)
        total_strokes += preflight["statistics"]["stroke_count"]
        total_points += preflight["statistics"]["point_count"]
        artifacts[scenario] = {
            "path": artifact_path.relative_to(output_dir).as_posix(),
            "sha256": file_sha256(artifact_path),
            "characters": characters,
            "text": text,
            "expected_strategies": expected_strategies,
            "software_preflight": preflight,
        }

    manifest = {
        "schema_version": MACHINE_HANDOFF_SCHEMA_VERSION,
        "type": "handwriting_machine_integration_handoff_package",
        "writer_id": deployment["writer_id"],
        "status": "ready_for_layout_and_device_review",
        "machine_ready": False,
        "source": {
            "personal_font_deployment_path": Path(
                os.path.relpath(
                    Path(personal_font_deployment_path).resolve(), output_dir
                )
            ).as_posix(),
            "personal_font_deployment_sha256": bundle["deployment_sha256"],
            "personal_font_profile_sha256": bundle["manifest_sha256"],
            "evaluation_report_sha256": bundle["evaluation_report_sha256"],
        },
        "selection": {
            "method": "deterministic_risk_coverage",
            "scenarios": selections,
            "unseen_candidates": unseen_candidates,
        },
        "generation_options": asdict(generation_options),
        "handoff_options": asdict(handoff_options),
        "artifacts": artifacts,
        "software_preflight_summary": {
            "status": "pass",
            "artifact_count": len(artifacts),
            "total_stroke_count": total_strokes,
            "total_point_count": total_points,
            "all_coordinates_within_page": True,
            "all_stroke_orders_continuous": True,
            "all_deployment_strategies_verified": True,
            "generated_ligature_count": 0,
        },
        "required_external_review": {
            "status": "pending",
            "integration_owner": "member_1",
            "device_owner": "member_5",
            "checks": [
                "Place module-local trajectories into the final page region and add origin_mm, scale, rotation_deg and region metadata.",
                "Apply calibrated page-to-machine coordinate mapping and verify travel limits.",
                "Convert advisory motion_hints into device-specific speed, acceleration and pen-lift commands.",
                "Run pen-up dry motion before any pen-down test and confirm emergency-stop behavior.",
                "Start with low device speed and one expendable sheet; inspect readability, drift and mechanical vibration.",
            ],
        },
        "safety_boundary": {
            "controls_device": False,
            "contains_device_commands": False,
            "contains_final_page_layout": False,
            "preserves_standard_stroke_boundaries": True,
            "ligature_path_generation_enabled": False,
        },
    }
    atomic_write_json(output_dir / "handoff_manifest.json", manifest)
    return manifest
