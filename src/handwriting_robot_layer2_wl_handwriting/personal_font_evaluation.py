from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence

from .hanzi_writer_adapter import build_hanzi_writer_library
from .personal_font_profile import load_personal_font_bundle
from .similarity import build_similarity_report
from .style_generator import StyleGenerationOptions, generate_styled_text


PERSONAL_FONT_EVALUATION_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PersonalFontEvaluationOptions:
    random_seeds: tuple[int, ...] = (0, 17, 42)
    meaningful_delta: float = 0.005
    severe_regression_delta: float = -0.04
    minimum_overall_delta: float = -0.005
    maximum_regression_rate: float = 0.15

    def validate(self) -> None:
        if not self.random_seeds:
            raise ValueError("at least one random seed is required")
        if len(self.random_seeds) != len(set(self.random_seeds)):
            raise ValueError("random seeds must be unique")
        if self.meaningful_delta < 0.0:
            raise ValueError("meaningful_delta must be non-negative")
        if self.severe_regression_delta >= 0.0:
            raise ValueError("severe_regression_delta must be negative")
        if self.minimum_overall_delta > 0.0:
            raise ValueError("minimum_overall_delta cannot be positive")
        if not 0.0 <= self.maximum_regression_rate <= 1.0:
            raise ValueError("maximum_regression_rate must be between 0 and 1")


def _round(value: float) -> float:
    return round(float(value), 6)


def _mean(values: Sequence[float]) -> float:
    return _round(mean(values))


def _score_snapshot(result: Dict[str, Any]) -> Dict[str, float]:
    scores = result.get("scores", {})
    return {
        "strict_kaishu_score": float(result["strict_kaishu_score"]),
        "running_script_score": float(result["running_script_score"]),
        "global_shape_score": float(scores["global_shape_score"]),
        "ordered_stroke_score": float(scores["ordered_stroke_score"]),
        "stroke_count_score": float(scores["stroke_count_score"]),
        "aspect_ratio_score": float(scores["aspect_ratio_score"]),
        "direction_score": float(scores["direction_score"]),
    }


def _average_snapshots(snapshots: Sequence[Dict[str, float]]) -> Dict[str, float]:
    return {
        key: _mean([snapshot[key] for snapshot in snapshots])
        for key in snapshots[0]
    }


def _classify(delta: float, meaningful_delta: float) -> str:
    if delta > meaningful_delta:
        return "improved"
    if delta < -meaningful_delta:
        return "regressed"
    return "stable"


def _character_records(document: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(record.get("character", "")): record
        for record in document.get("generation", {}).get("characters", [])
        if isinstance(record, dict)
    }


def _group_summary(
    characters: Sequence[Dict[str, Any]], field: str
) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for character in characters:
        groups.setdefault(str(character.get(field) or "none"), []).append(character)
    return {
        name: {
            "character_count": len(items),
            "running_script_delta_mean": _mean(
                [item["delta"]["running_script_score"] for item in items]
            ),
            "classification_counts": {
                classification: sum(
                    item["classification"] == classification for item in items
                )
                for classification in ("improved", "stable", "regressed")
            },
        }
        for name, items in sorted(groups.items())
    }


def build_personal_font_evaluation(
    processed_dir: Path,
    personal_font_profile_path: Path,
    hanzi_writer_package_dir: Path,
    generation_options: Optional[StyleGenerationOptions] = None,
    evaluation_options: Optional[PersonalFontEvaluationOptions] = None,
    variant: int = 1,
) -> Dict[str, Any]:
    if variant < 1:
        raise ValueError("variant must be at least 1")
    generation_options = generation_options or StyleGenerationOptions()
    generation_options.validate()
    evaluation_options = evaluation_options or PersonalFontEvaluationOptions()
    evaluation_options.validate()
    bundle = load_personal_font_bundle(Path(personal_font_profile_path))
    profile = bundle["style_profile"]
    alignment = bundle["automatic_alignment"]
    alignment_records = alignment["characters"]
    characters = [str(record["character"]) for record in alignment_records]
    text = "".join(characters)
    skeleton_library = build_hanzi_writer_library(
        Path(hanzi_writer_package_dir), characters
    )
    page_width = max(
        210.0,
        20.0
        + len(characters)
        * (generation_options.char_width_mm + generation_options.char_spacing_mm),
    )
    confidence_map = {
        str(record["character"]): str(record["confidence"])
        for record in alignment_records
    }
    seed_runs = []
    by_character: Dict[str, List[Dict[str, Any]]] = {
        character: [] for character in characters
    }
    invariant_failures = []

    for seed in evaluation_options.random_seeds:
        options = replace(generation_options, random_seed=int(seed))
        baseline_document = generate_styled_text(
            text,
            skeleton_library,
            profile,
            options,
            page_width_mm=page_width,
        )
        personal_document = generate_styled_text(
            text,
            skeleton_library,
            profile,
            options,
            page_width_mm=page_width,
            personal_font_bundle=bundle,
        )
        baseline_report = build_similarity_report(
            Path(processed_dir), baseline_document, variant=variant
        )
        personal_report = build_similarity_report(
            Path(processed_dir), personal_document, variant=variant
        )
        baseline_results = {
            item["character"]: item for item in baseline_report["characters"]
        }
        personal_results = {
            item["character"]: item for item in personal_report["characters"]
        }
        baseline_records = _character_records(baseline_document)
        personal_records = _character_records(personal_document)

        for character in characters:
            baseline_result = baseline_results.get(character)
            personal_result = personal_results.get(character)
            baseline_record = baseline_records.get(character)
            personal_record = personal_records.get(character)
            if not all(
                (baseline_result, personal_result, baseline_record, personal_record)
            ):
                invariant_failures.append(
                    {"seed": seed, "character": character, "reason": "missing_result"}
                )
                continue
            if baseline_record["stroke_orders"] != personal_record["stroke_orders"]:
                invariant_failures.append(
                    {
                        "seed": seed,
                        "character": character,
                        "reason": "stroke_order_or_boundary_changed",
                    }
                )
            if personal_record.get("ligature_applied") is not False:
                invariant_failures.append(
                    {
                        "seed": seed,
                        "character": character,
                        "reason": "unexpected_ligature",
                    }
                )
            baseline_scores = _score_snapshot(baseline_result)
            personal_scores = _score_snapshot(personal_result)
            by_character[character].append(
                {
                    "seed": seed,
                    "baseline": {key: _round(value) for key, value in baseline_scores.items()},
                    "personal_font": {
                        key: _round(value) for key, value in personal_scores.items()
                    },
                    "delta": {
                        key: _round(personal_scores[key] - baseline_scores[key])
                        for key in baseline_scores
                    },
                    "strategy": personal_record.get("personal_font_strategy"),
                }
            )

        seed_runs.append(
            {
                "seed": seed,
                "baseline_document_sha256": baseline_report[
                    "generated_document_sha256"
                ],
                "personal_font_document_sha256": personal_report[
                    "generated_document_sha256"
                ],
                "baseline_summary": baseline_report["summary"],
                "personal_font_summary": personal_report["summary"],
                "baseline_skipped": baseline_report["skipped"],
                "personal_font_skipped": personal_report["skipped"],
            }
        )

    evaluated_characters = []
    skipped_characters = []
    for character in characters:
        runs = by_character[character]
        if not runs:
            skipped_characters.append(character)
            continue
        baseline_average = _average_snapshots([run["baseline"] for run in runs])
        personal_average = _average_snapshots(
            [run["personal_font"] for run in runs]
        )
        delta = {
            key: _round(personal_average[key] - baseline_average[key])
            for key in baseline_average
        }
        strategy = str(runs[0]["strategy"])
        classification = _classify(
            delta["running_script_score"],
            evaluation_options.meaningful_delta,
        )
        recommended_strategy = (
            "automatic_correspondence_features"
            if strategy == "automatic_correspondence_features"
            and classification != "regressed"
            else "safe_standard_skeleton_fallback"
        )
        evaluated_characters.append(
            {
                "character": character,
                "unicode": f"U+{ord(character):04X}",
                "alignment_confidence": confidence_map[character],
                "personal_font_strategy": strategy,
                "baseline": baseline_average,
                "personal_font": personal_average,
                "delta": delta,
                "classification": classification,
                "severe_regression": delta["running_script_score"]
                <= evaluation_options.severe_regression_delta,
                "recommended_strategy": recommended_strategy,
                "seed_results": runs,
            }
        )

    classification_counts = {
        classification: sum(
            item["classification"] == classification
            for item in evaluated_characters
        )
        for classification in ("improved", "stable", "regressed")
    }
    severe_regressions = [
        item for item in evaluated_characters if item["severe_regression"]
    ]
    regression_rate = (
        classification_counts["regressed"] / len(evaluated_characters)
        if evaluated_characters
        else 1.0
    )
    baseline_running_mean = _mean(
        [item["baseline"]["running_script_score"] for item in evaluated_characters]
    )
    personal_running_mean = _mean(
        [item["personal_font"]["running_script_score"] for item in evaluated_characters]
    )
    running_delta_mean = _round(personal_running_mean - baseline_running_mean)
    gate_checks = {
        "all_characters_evaluated": not skipped_characters,
        "stroke_boundaries_preserved": not invariant_failures,
        "overall_delta_acceptable": running_delta_mean
        >= evaluation_options.minimum_overall_delta,
        "regression_rate_acceptable": regression_rate
        <= evaluation_options.maximum_regression_rate,
        "no_severe_regressions": not severe_regressions,
    }
    quality_gate_status = "pass" if all(gate_checks.values()) else "fail"
    enhanced_characters = [
        item["character"]
        for item in evaluated_characters
        if item["recommended_strategy"] == "automatic_correspondence_features"
    ]
    fallback_characters = [
        item["character"]
        for item in evaluated_characters
        if item["recommended_strategy"] == "safe_standard_skeleton_fallback"
    ]
    projected_scores = [
        item["personal_font"]["running_script_score"]
        if item["recommended_strategy"] == "automatic_correspondence_features"
        else item["baseline"]["running_script_score"]
        for item in evaluated_characters
    ]
    projected_running_mean = _mean(projected_scores)
    ranked = sorted(
        evaluated_characters,
        key=lambda item: item["delta"]["running_script_score"],
    )

    return {
        "schema_version": PERSONAL_FONT_EVALUATION_SCHEMA_VERSION,
        "type": "personal_font_generation_comparison_report",
        "writer_id": profile["writer_id"],
        "personal_font_manifest_sha256": bundle["manifest_sha256"],
        "reference_variant": variant,
        "character_count": len(characters),
        "evaluated_character_count": len(evaluated_characters),
        "skipped_characters": skipped_characters,
        "comparison": {
            "baseline": "global_style_only",
            "candidate": "personal_font_character_features",
            "primary_metric": "running_script_score",
            "random_seeds": list(evaluation_options.random_seeds),
            "generation_options": asdict(generation_options),
        },
        "summary": {
            "baseline_running_script_score_mean": baseline_running_mean,
            "personal_font_running_script_score_mean": personal_running_mean,
            "running_script_delta_mean": running_delta_mean,
            "classification_counts": classification_counts,
            "regression_rate": _round(regression_rate),
            "severe_regression_count": len(severe_regressions),
            "by_alignment_confidence": _group_summary(
                evaluated_characters, "alignment_confidence"
            ),
            "by_generation_strategy": _group_summary(
                evaluated_characters, "personal_font_strategy"
            ),
        },
        "quality_gate": {
            "status": quality_gate_status,
            "checks": gate_checks,
            "thresholds": {
                "meaningful_delta": evaluation_options.meaningful_delta,
                "severe_regression_delta": evaluation_options.severe_regression_delta,
                "minimum_overall_delta": evaluation_options.minimum_overall_delta,
                "maximum_regression_rate": evaluation_options.maximum_regression_rate,
            },
            "notes": (
                "This gate evaluates enabling character-level features for every "
                "high/medium-confidence character. A failed gate does not block "
                "personal-font creation or safe per-character fallback."
            ),
        },
        "deployment_recommendation": {
            "status": "ready_with_per_character_fallback"
            if evaluated_characters and not invariant_failures
            else "blocked",
            "selection_method": (
                "Keep automatic correspondence features only when the multi-seed "
                "running-script delta is not classified as regressed."
            ),
            "enhanced_automatic_alignment_count": len(enhanced_characters),
            "safe_fallback_count": len(fallback_characters),
            "enhanced_characters": enhanced_characters,
            "safe_fallback_characters": fallback_characters,
            "projected_running_script_score_mean": projected_running_mean,
            "projected_delta_mean": _round(
                projected_running_mean - baseline_running_mean
            ),
            "manual_review_required": False,
        },
        "largest_improvements": list(reversed(ranked[-10:])),
        "largest_regressions": ranked[:10],
        "characters": evaluated_characters,
        "seed_runs": seed_runs,
        "invariant_failures": invariant_failures,
        "limitations": [
            "Geometry scores do not measure readability or semantic correctness.",
            "The comparison evaluates captured characters only; unseen-character quality requires separate tests.",
            "No running-script ligature is generated or evaluated.",
            "Private processed samples and this report must remain outside Git.",
        ],
    }
