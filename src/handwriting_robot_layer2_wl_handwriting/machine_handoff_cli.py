from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .machine_handoff import MachineHandoffOptions, build_machine_handoff_package
from .style_generator import StyleGenerationOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build software-preflighted StrokeDocuments for machine integration review"
    )
    parser.add_argument("personal_font_deployment", type=Path)
    parser.add_argument("hanzi_writer_package_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--unseen-candidates", default="好世界的字")
    parser.add_argument("--characters-per-scenario", type=int, default=2)
    parser.add_argument("--random-seed", type=int, default=23)
    parser.add_argument("--max-point-spacing-mm", type=float, default=0.75)
    parser.add_argument("--char-width-mm", type=float, default=8.0)
    parser.add_argument("--char-height-mm", type=float, default=8.0)
    parser.add_argument("--char-spacing-mm", type=float, default=1.2)
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = build_machine_handoff_package(
            args.personal_font_deployment,
            args.hanzi_writer_package_dir,
            args.output_dir,
            unseen_candidates=args.unseen_candidates,
            generation_options=StyleGenerationOptions(
                char_width_mm=args.char_width_mm,
                char_height_mm=args.char_height_mm,
                char_spacing_mm=args.char_spacing_mm,
            ),
            handoff_options=MachineHandoffOptions(
                characters_per_scenario=args.characters_per_scenario,
                random_seed=args.random_seed,
                max_point_spacing_mm=args.max_point_spacing_mm,
            ),
        )
    except (OSError, ValueError, KeyError) as error:
        print(f"machine integration handoff creation failed: {error}")
        return 1
    summary = manifest["software_preflight_summary"]
    print(Path(args.output_dir) / "handoff_manifest.json")
    print(
        f"software preflight: {summary['status']}; artifacts: "
        f"{summary['artifact_count']}; machine ready: false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
