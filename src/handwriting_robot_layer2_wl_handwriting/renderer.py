from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .storage import SampleStore


@dataclass(frozen=True)
class RenderOptions:
    char_width_mm: float = 8.0
    char_height_mm: float = 8.0
    char_spacing_mm: float = 1.2
    random_seed: int = 0
    scale_jitter: float = 0.03
    slant_jitter: float = 0.025
    position_jitter_mm: float = 0.15


def analyze_coverage(text: str, store: SampleStore) -> Dict[str, Any]:
    required = list(dict.fromkeys(character for character in text if not character.isspace()))
    available = [character for character in required if store.available_variants(character)]
    missing = [character for character in required if character not in available]
    return {
        "required_characters": required,
        "available_characters": available,
        "missing_characters": missing,
        "required_count": len(required),
        "available_count": len(available),
        "coverage": 1.0 if not required else len(available) / len(required),
    }


def _stable_rng(seed: int, character: str, index: int) -> random.Random:
    value = f"{seed}:{character}:{index}".encode("utf-8")
    digest = hashlib.sha256(value).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _select_variant(
    variants: List[Dict[str, Any]], seed: int, character: str, index: int
) -> Dict[str, Any]:
    rng = _stable_rng(seed, character, index)
    return variants[rng.randrange(len(variants))]


def _transform_point(
    x: float,
    y: float,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    slant: float,
) -> List[float]:
    centered_y = y - 0.5
    return [
        round(origin_x + (x + slant * centered_y) * width, 4),
        round(origin_y + y * height, 4),
    ]


def render_text(
    text: str,
    store: SampleStore,
    options: Optional[RenderOptions] = None,
    page_width_mm: float = 210.0,
    page_height_mm: float = 297.0,
    origin_mm: Iterable[float] = (10.0, 10.0),
) -> Dict[str, Any]:
    """Render captured user samples into the repository StrokeDocument v0.1."""

    options = options or RenderOptions()
    origin = list(origin_mm)
    if len(origin) != 2:
        raise ValueError("origin_mm must contain x and y")

    coverage = analyze_coverage(text, store)
    if coverage["missing_characters"]:
        missing = "".join(coverage["missing_characters"])
        raise ValueError(f"missing handwriting samples: {missing}")

    strokes: List[Dict[str, Any]] = []
    cursor_x = float(origin[0])
    baseline_y = float(origin[1])
    order = 1

    for index, character in enumerate(text):
        if character.isspace():
            cursor_x += options.char_width_mm + options.char_spacing_mm
            continue

        variants = store.available_variants(character)
        sample = _select_variant(variants, options.random_seed, character, index)
        rng = _stable_rng(options.random_seed + 1, character, index)
        scale_x = 1.0 + rng.uniform(-options.scale_jitter, options.scale_jitter)
        scale_y = 1.0 + rng.uniform(-options.scale_jitter, options.scale_jitter)
        slant = rng.uniform(-options.slant_jitter, options.slant_jitter)
        offset_x = rng.uniform(-options.position_jitter_mm, options.position_jitter_mm)
        offset_y = rng.uniform(-options.position_jitter_mm, options.position_jitter_mm)
        width = options.char_width_mm * scale_x
        height = options.char_height_mm * scale_y

        for captured_stroke in sample.get("strokes", []):
            points = [
                _transform_point(
                    point["x"],
                    point["y"],
                    cursor_x + offset_x,
                    baseline_y + offset_y,
                    width,
                    height,
                    slant,
                )
                for point in captured_stroke.get("points", [])
            ]
            if not points:
                continue
            strokes.append({"points": points, "pen_down": True, "order": order})
            order += 1
        cursor_x += options.char_width_mm + options.char_spacing_mm

    return {
        "schema_version": "0.1",
        "type": "stroke_document",
        "source": "handwriting",
        "user_id": store.writer_id,
        "page": {"width_mm": float(page_width_mm), "height_mm": float(page_height_mm)},
        "strokes": strokes,
    }
