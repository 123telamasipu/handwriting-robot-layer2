from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .hanzi_writer_adapter import build_hanzi_writer_library
from .skeleton import skeleton_by_character
from .storage import atomic_write_json


ALIGNMENT_REVIEW_SCHEMA_VERSION = "1.0"
RELATION_TYPES = {
    "one_to_one",
    "observed_joins_standard",
    "observed_splits_standard",
    "many_to_many",
}
REVIEW_STATUSES = {"pending", "in_review", "approved", "rejected"}
CANDIDATE_DECISIONS = {"pending", "allow_ligature", "reject_ligature", "uncertain"}
STROKE_COLORS = (
    "#2563eb",
    "#dc2626",
    "#16a34a",
    "#9333ea",
    "#ea580c",
    "#0891b2",
    "#be123c",
    "#4f46e5",
    "#65a30d",
    "#c026d3",
)


def _canonical_hash(document: Dict[str, Any]) -> str:
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _processed_strokes(document: Dict[str, Any]) -> List[List[List[float]]]:
    if document.get("type") != "processed_handwriting_sample":
        raise ValueError("review source must be a processed handwriting sample")
    result = []
    for stroke in document.get("representations", {}).get("glyph", {}).get("strokes", []):
        points = [
            [float(point["x"]), float(point["y"])]
            for point in stroke.get("points", [])
        ]
        if len(points) < 2:
            raise ValueError("each observed stroke must contain at least two points")
        result.append(points)
    if not result:
        raise ValueError("processed sample has no glyph strokes")
    return result


def _polyline(points: Sequence[Sequence[float]], x: float, y: float, size: float) -> str:
    return " ".join(
        f"{x + float(point[0]) * size:.2f},{y + float(point[1]) * size:.2f}"
        for point in points
    )


def render_alignment_preview_svg(
    character: str,
    observed_strokes: Sequence[Sequence[Sequence[float]]],
    standard_strokes: Sequence[Dict[str, Any]],
    candidates: Sequence[Dict[str, Any]],
) -> str:
    width = 920
    height = 470
    panel_size = 360.0
    panel_y = 70.0
    observed_x = 55.0
    standard_x = 505.0
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#111827}.label{font-size:16px;font-weight:700}.small{font-size:12px}.order{font-size:11px;font-weight:700}</style>',
        f'<text x="20" y="30" class="label">Alignment review: {html.escape(character)}</text>',
        '<text x="55" y="55" class="label">Observed natural handwriting</text>',
        '<text x="505" y="55" class="label">Standard kaishu skeleton reference</text>',
        f'<rect x="{observed_x}" y="{panel_y}" width="{panel_size}" height="{panel_size}" fill="none" stroke="#d1d5db"/>',
        f'<rect x="{standard_x}" y="{panel_y}" width="{panel_size}" height="{panel_size}" fill="none" stroke="#d1d5db"/>',
    ]
    for fraction in (0.25, 0.5, 0.75):
        for panel_x in (observed_x, standard_x):
            coordinate = panel_x + panel_size * fraction
            elements.append(
                f'<line x1="{coordinate}" y1="{panel_y}" x2="{coordinate}" y2="{panel_y + panel_size}" stroke="#eef2f7"/>'
            )
            coordinate_y = panel_y + panel_size * fraction
            elements.append(
                f'<line x1="{panel_x}" y1="{coordinate_y}" x2="{panel_x + panel_size}" y2="{coordinate_y}" stroke="#eef2f7"/>'
            )

    for index, points in enumerate(observed_strokes, start=1):
        color = STROKE_COLORS[(index - 1) % len(STROKE_COLORS)]
        elements.append(
            f'<polyline points="{_polyline(points, observed_x, panel_y, panel_size)}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        start = points[0]
        elements.append(
            f'<text x="{observed_x + float(start[0]) * panel_size + 4:.2f}" y="{panel_y + float(start[1]) * panel_size - 4:.2f}" class="order" fill="{color}">O{index}</text>'
        )

    for index, stroke in enumerate(standard_strokes, start=1):
        points = stroke.get("points", [])
        color = STROKE_COLORS[(index - 1) % len(STROKE_COLORS)]
        elements.append(
            f'<polyline points="{_polyline(points, standard_x, panel_y, panel_size)}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        start = points[0]
        elements.append(
            f'<text x="{standard_x + float(start[0]) * panel_size + 4:.2f}" y="{panel_y + float(start[1]) * panel_size - 4:.2f}" class="order" fill="{color}">K{index}</text>'
        )

    for candidate in candidates:
        first_order = int(candidate["from_observed_stroke_order"])
        second_order = int(candidate["to_observed_stroke_order"])
        first = observed_strokes[first_order - 1][-1]
        second = observed_strokes[second_order - 1][0]
        elements.append(
            f'<line x1="{observed_x + float(first[0]) * panel_size:.2f}" y1="{panel_y + float(first[1]) * panel_size:.2f}" x2="{observed_x + float(second[0]) * panel_size:.2f}" y2="{panel_y + float(second[1]) * panel_size:.2f}" stroke="#111827" stroke-width="1.5" stroke-dasharray="5 5"/>'
        )
    elements.extend(
        [
            '<text x="55" y="452" class="small">O = observed pen-down segment; dashed lines = analysis candidates only.</text>',
            '<text x="505" y="452" class="small">K = standard kaishu stroke; not authoritative calligraphy annotation.</text>',
            "</svg>",
        ]
    )
    return "\n".join(elements)


def _validate_orders(values: Any, maximum: int, field: str) -> List[int]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field} must be a non-empty list")
    orders = [int(value) for value in values]
    if orders != sorted(set(orders)):
        raise ValueError(f"{field} must contain unique ascending orders")
    if orders[0] < 1 or orders[-1] > maximum:
        raise ValueError(f"{field} contains an out-of-range order")
    if orders != list(range(orders[0], orders[-1] + 1)):
        raise ValueError(f"{field} orders must be contiguous")
    return orders


def validate_alignment_review(document: Dict[str, Any]) -> Dict[str, Any]:
    if document.get("schema_version") != ALIGNMENT_REVIEW_SCHEMA_VERSION:
        raise ValueError("alignment review schema_version must be 1.0")
    if document.get("type") != "running_script_alignment_review":
        raise ValueError("alignment review type is invalid")
    if not str(document.get("writer_id", "")).strip():
        raise ValueError("alignment review writer_id is required")
    characters = document.get("characters", [])
    if not isinstance(characters, list) or not characters:
        raise ValueError("alignment review must contain characters")
    seen_characters: Set[str] = set()
    for item in characters:
        character = str(item.get("character", ""))
        if len(character) != 1 or character in seen_characters:
            raise ValueError("review characters must be unique Unicode characters")
        seen_characters.add(character)
        observed_count = int(item.get("observed_stroke_count", 0))
        standard_count = int(item.get("standard_kaishu_stroke_count", 0))
        if observed_count < 1 or standard_count < 1:
            raise ValueError("review stroke counts must be positive")
        review = item.get("review", {})
        status = str(review.get("status", "pending"))
        if status not in REVIEW_STATUSES:
            raise ValueError("character review status is invalid")
        for candidate in item.get("connection_candidates", []):
            first = int(candidate.get("from_observed_stroke_order", 0))
            second = int(candidate.get("to_observed_stroke_order", 0))
            if not (1 <= first < second <= observed_count) or second != first + 1:
                raise ValueError("connection candidate observed orders are invalid")
            decision = str(candidate.get("review_decision", "pending"))
            if decision not in CANDIDATE_DECISIONS:
                raise ValueError("connection candidate review_decision is invalid")

        used_observed: List[int] = []
        used_standard: List[int] = []
        previous_observed = 0
        previous_standard = 0
        for group in item.get("alignment_groups", []):
            relation = str(group.get("relation", ""))
            if relation not in RELATION_TYPES:
                raise ValueError("alignment group relation is invalid")
            observed = _validate_orders(
                group.get("observed_stroke_orders"),
                observed_count,
                "observed_stroke_orders",
            )
            standard = _validate_orders(
                group.get("standard_kaishu_stroke_orders"),
                standard_count,
                "standard_kaishu_stroke_orders",
            )
            expected_relation = (
                "one_to_one"
                if len(observed) == 1 and len(standard) == 1
                else "observed_joins_standard"
                if len(observed) == 1 and len(standard) > 1
                else "observed_splits_standard"
                if len(observed) > 1 and len(standard) == 1
                else "many_to_many"
            )
            if relation != expected_relation:
                raise ValueError("alignment group relation does not match its orders")
            if observed[0] <= previous_observed or standard[0] <= previous_standard:
                raise ValueError("alignment groups must preserve writing order")
            previous_observed = observed[-1]
            previous_standard = standard[-1]
            used_observed.extend(observed)
            used_standard.extend(standard)
        if len(used_observed) != len(set(used_observed)) or len(used_standard) != len(
            set(used_standard)
        ):
            raise ValueError("alignment groups must not reuse strokes")
        if status == "approved":
            if used_observed != list(range(1, observed_count + 1)):
                raise ValueError("approved review must cover all observed strokes")
            if used_standard != list(range(1, standard_count + 1)):
                raise ValueError("approved review must cover all standard strokes")
            if any(
                candidate.get("review_decision", "pending") == "pending"
                for candidate in item.get("connection_candidates", [])
            ):
                raise ValueError("approved review cannot contain pending candidates")
    return document


def _selected_candidates(
    report: Dict[str, Any], confidences: Set[str], characters: Optional[Set[str]]
) -> Dict[str, List[Dict[str, Any]]]:
    selected: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in report.get("candidates", []):
        character = str(candidate.get("character", ""))
        if candidate.get("confidence") not in confidences:
            continue
        if characters is not None and character not in characters:
            continue
        selected.setdefault(character, []).append(candidate)
    if not selected:
        raise ValueError("no connection candidates match the review selection")
    return selected


def build_alignment_review_package(
    connection_report: Dict[str, Any],
    processed_dir: Path,
    hanzi_writer_package_dir: Path,
    output_dir: Path,
    confidences: Iterable[str] = ("high",),
    characters: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    if connection_report.get("type") != "running_script_connection_candidate_report":
        raise ValueError("connection report type is invalid")
    confidence_set = {str(value) for value in confidences}
    if not confidence_set or not confidence_set <= {"high", "medium"}:
        raise ValueError("review confidences must contain high and/or medium")
    character_set = set(characters) if characters is not None else None
    selected = _selected_candidates(connection_report, confidence_set, character_set)
    ordered_characters = sorted(selected, key=ord)
    skeleton_library = build_hanzi_writer_library(
        Path(hanzi_writer_package_dir), ordered_characters
    )
    output_dir = Path(output_dir)
    preview_dir = output_dir / "previews"
    review_items = []
    for character in ordered_characters:
        sample_matches = [
            sample
            for sample in connection_report.get("samples", [])
            if sample.get("character") == character
        ]
        if len(sample_matches) != 1:
            raise ValueError(f"connection report sample is missing or duplicated: {character}")
        sample_summary = sample_matches[0]
        variant = int(sample_summary.get("variant", 1))
        unicode_value = f"U+{ord(character):04X}"
        processed_path = Path(processed_dir) / unicode_value / f"v{variant:02d}.json"
        processed = json.loads(processed_path.read_text(encoding="utf-8-sig"))
        observed_strokes = _processed_strokes(processed)
        glyph = skeleton_by_character(skeleton_library, character)
        if glyph is None:
            raise ValueError(f"standard skeleton is missing: {character}")
        candidate_reviews = []
        for candidate in selected[character]:
            candidate_reviews.append(
                {
                    "candidate_id": (
                        f"{unicode_value}-O{int(candidate['from_observed_stroke_order']):02d}"
                        f"-O{int(candidate['to_observed_stroke_order']):02d}"
                    ),
                    "from_observed_stroke_order": int(
                        candidate["from_observed_stroke_order"]
                    ),
                    "to_observed_stroke_order": int(
                        candidate["to_observed_stroke_order"]
                    ),
                    "confidence": str(candidate.get("confidence", "")),
                    "candidate_score": float(candidate.get("candidate_score", 0.0)),
                    "evidence": {
                        key: candidate.get(key)
                        for key in (
                            "endpoint_distance",
                            "pen_up_pause_ms",
                            "exit_to_connector_turn_deg",
                            "connector_to_entry_turn_deg",
                        )
                    },
                    "review_decision": "pending",
                    "notes": "",
                }
            )
        preview_path = preview_dir / f"{unicode_value}.svg"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(
            render_alignment_preview_svg(
                character, observed_strokes, glyph["strokes"], candidate_reviews
            ),
            encoding="utf-8",
        )
        review_items.append(
            {
                "character": character,
                "unicode": unicode_value,
                "variant": variant,
                "observed_stroke_count": len(observed_strokes),
                "standard_kaishu_stroke_count": int(glyph["stroke_count"]),
                "count_relation": (
                    "observed_fewer_than_standard"
                    if len(observed_strokes) < int(glyph["stroke_count"])
                    else "observed_more_than_standard"
                    if len(observed_strokes) > int(glyph["stroke_count"])
                    else "same_count"
                ),
                "preview_svg": str(preview_path.relative_to(output_dir)).replace(
                    "\\", "/"
                ),
                "source": {
                    "processed_sample_sha256": _canonical_hash(processed),
                    "standard_skeleton_source": skeleton_library.get("source", {}),
                },
                "connection_candidates": candidate_reviews,
                "alignment_groups": [],
                "review": {
                    "status": "pending",
                    "reviewer_id": "",
                    "reviewed_at": "",
                    "notes": "",
                },
            }
        )
    document = {
        "schema_version": ALIGNMENT_REVIEW_SCHEMA_VERSION,
        "type": "running_script_alignment_review",
        "writer_id": str(connection_report.get("writer_id", "")),
        "status": "draft",
        "source": {
            "connection_report_sha256": _canonical_hash(connection_report),
            "skeleton_library_name": skeleton_library.get("name"),
            "skeleton_license": skeleton_library.get("license", {}),
        },
        "selection": {
            "confidences": sorted(confidence_set),
            "character_count": len(review_items),
        },
        "instructions": [
            "Compare O-numbered observed segments with K-numbered standard strokes.",
            "Fill alignment_groups using contiguous, ordered stroke groups.",
            "Review each dashed connection candidate independently.",
            "Do not approve a connection path from endpoint proximity alone.",
        ],
        "characters": review_items,
        "safety": {
            "analysis_only": True,
            "approved_mappings_enable_generation": False,
            "requires_separate_connection_path_model": True,
        },
    }
    validate_alignment_review(document)
    atomic_write_json(output_dir / "alignment_review.json", document)
    return document
