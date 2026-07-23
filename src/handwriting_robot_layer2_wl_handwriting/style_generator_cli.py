from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .hanzi_writer_adapter import build_hanzi_writer_library
from .personal_font_profile import load_personal_font_bundle
from .personal_font_deployment import load_personal_font_deployment_bundle
from .skeleton import load_skeleton_library
from .storage import atomic_write_json
from .style_generator import (
    StyleGenerationOptions,
    generate_styled_text,
    load_style_profile,
)


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Generate StrokeDocument trajectories from ordered skeletons"
    )
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    return parser


def load_request(path: Path) -> Dict[str, Any]:
    request = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not str(request.get("user_id", "")).strip():
        raise ValueError("request.user_id is required")
    if not str(request.get("text", "")):
        raise ValueError("request.text is required")
    return request


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = load_request(args.request)
        writer_id = str(request["user_id"])
        profile_path = Path(
            request.get("style_profile_path")
            or args.data_dir
            / "style_profiles"
            / writer_id
            / "style_profile_v1.json"
        )
        explicit_manifest_path = request.get("personal_font_profile_path")
        explicit_deployment_path = request.get("personal_font_deployment_path")
        if explicit_deployment_path and (
            explicit_manifest_path or request.get("style_profile_path")
        ):
            raise ValueError(
                "request.personal_font_deployment_path cannot be combined with "
                "personal_font_profile_path or style_profile_path"
            )
        if explicit_manifest_path and request.get("style_profile_path"):
            raise ValueError(
                "request must not set both personal_font_profile_path and "
                "style_profile_path"
            )
        auto_detect_manifest = not request.get("style_profile_path")
        manifest_path = Path(
            explicit_manifest_path
            or profile_path.parent / "personal_font_profile_v1.json"
        )
        deployment_path = Path(
            explicit_deployment_path
            or profile_path.parent / "personal_font_deployment_v1.json"
        )
        skeleton_path = request.get("skeleton_library_path")
        hanzi_writer_package_dir = request.get("hanzi_writer_package_dir")
        if skeleton_path and hanzi_writer_package_dir:
            raise ValueError(
                "request must not set both skeleton_library_path and "
                "hanzi_writer_package_dir"
            )
        personal_font_bundle = None
        if explicit_deployment_path or (
            auto_detect_manifest and deployment_path.is_file()
        ):
            personal_font_bundle = load_personal_font_deployment_bundle(
                deployment_path
            )
            profile = personal_font_bundle["style_profile"]
        elif explicit_manifest_path or (
            auto_detect_manifest and manifest_path.is_file()
        ):
            personal_font_bundle = load_personal_font_bundle(manifest_path)
            profile = personal_font_bundle["style_profile"]
        else:
            profile = load_style_profile(profile_path)
        if profile["writer_id"] != writer_id:
            raise ValueError("request.user_id does not match the style profile")
        if hanzi_writer_package_dir:
            characters = list(
                dict.fromkeys(
                    character
                    for character in request["text"]
                    if not character.isspace()
                )
            )
            skeleton_library = build_hanzi_writer_library(
                Path(hanzi_writer_package_dir), characters
            )
        else:
            skeleton_library = load_skeleton_library(
                Path(skeleton_path) if skeleton_path else None
            )
        option_values = request.get("options", {})
        options = StyleGenerationOptions(
            char_width_mm=float(option_values.get("char_width_mm", 8.0)),
            char_height_mm=float(option_values.get("char_height_mm", 8.0)),
            char_spacing_mm=float(option_values.get("char_spacing_mm", 1.2)),
            random_seed=int(option_values.get("random_seed", 0)),
            variation_strength=float(
                option_values.get("variation_strength", 0.35)
            ),
            curvature_strength=float(
                option_values.get("curvature_strength", 1.0)
            ),
            glyph_occupancy=float(option_values.get("glyph_occupancy", 0.78)),
            skeleton_resample_spacing=float(
                option_values.get("skeleton_resample_spacing", 0.025)
            ),
        )
        page = request.get("page", {})
        document = generate_styled_text(
            request["text"],
            skeleton_library,
            profile,
            options,
            page_width_mm=float(page.get("width_mm", 210.0)),
            page_height_mm=float(page.get("height_mm", 297.0)),
            origin_mm=request.get("origin_mm", [10.0, 10.0]),
            personal_font_bundle=personal_font_bundle,
        )
        atomic_write_json(args.output, document)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"style trajectory generation failed: {error}")
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
