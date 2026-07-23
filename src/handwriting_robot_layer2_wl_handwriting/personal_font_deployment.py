from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .personal_font_profile import file_sha256, load_personal_font_bundle
from .storage import atomic_write_json


PERSONAL_FONT_DEPLOYMENT_SCHEMA_VERSION = "1.0"
DEPLOYMENT_STRATEGIES = {
    "automatic_correspondence_features",
    "safe_standard_skeleton_fallback",
}


def _relative_artifact_path(artifact_path: Path, output_path: Path) -> str:
    return Path(
        os.path.relpath(Path(artifact_path).resolve(), Path(output_path).parent.resolve())
    ).as_posix()


def _load_evaluation_report(path: Path) -> Dict[str, Any]:
    report = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if report.get("schema_version") != "1.0":
        raise ValueError("personal font evaluation schema_version must be 1.0")
    if report.get("type") != "personal_font_generation_comparison_report":
        raise ValueError("personal font evaluation report type is invalid")
    recommendation = report.get("deployment_recommendation", {})
    if recommendation.get("status") != "ready_with_per_character_fallback":
        raise ValueError("personal font evaluation is not ready for deployment")
    if bool(recommendation.get("manual_review_required", True)):
        raise ValueError("personal font evaluation unexpectedly requires review")
    if report.get("skipped_characters"):
        raise ValueError("personal font evaluation skipped characters")
    if report.get("invariant_failures"):
        raise ValueError("personal font evaluation has invariant failures")
    return report


def _evaluation_character_map(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for record in report.get("characters", []):
        if not isinstance(record, dict):
            raise ValueError("personal font evaluation character record is invalid")
        character = str(record.get("character", ""))
        if len(character) != 1 or character in result:
            raise ValueError("personal font evaluation characters are invalid")
        strategy = record.get("recommended_strategy")
        if strategy not in DEPLOYMENT_STRATEGIES:
            raise ValueError("personal font evaluation strategy is invalid")
        result[character] = record
    if not result:
        raise ValueError("personal font evaluation characters are required")
    return result


def _validate_evaluation_against_bundle(
    report: Dict[str, Any], bundle: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    writer_id = bundle["manifest"]["writer_id"]
    if report.get("writer_id") != writer_id:
        raise ValueError("deployment evaluation writer_id mismatch")
    if report.get("personal_font_manifest_sha256") != bundle["manifest_sha256"]:
        raise ValueError("deployment evaluation personal font fingerprint mismatch")
    evaluation_map = _evaluation_character_map(report)
    alignment_map = {
        str(record["character"]): record
        for record in bundle["automatic_alignment"]["characters"]
    }
    if set(evaluation_map) != set(alignment_map):
        raise ValueError("deployment evaluation character coverage mismatch")
    if int(report.get("evaluated_character_count", -1)) != len(evaluation_map):
        raise ValueError("deployment evaluation character count mismatch")
    for character, evaluation in evaluation_map.items():
        confidence = str(evaluation.get("alignment_confidence", ""))
        if confidence != str(alignment_map[character].get("confidence", "")):
            raise ValueError("deployment evaluation alignment confidence mismatch")
        if confidence == "low" and evaluation.get("recommended_strategy") != (
            "safe_standard_skeleton_fallback"
        ):
            raise ValueError("low-confidence character cannot enable enhanced features")
    return evaluation_map


def build_personal_font_deployment(
    personal_font_profile_path: Path,
    evaluation_report_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    profile_path = Path(personal_font_profile_path).resolve()
    report_path = Path(evaluation_report_path).resolve()
    output_path = Path(output_path).resolve()
    bundle = load_personal_font_bundle(profile_path)
    report = _load_evaluation_report(report_path)
    evaluation_map = _validate_evaluation_against_bundle(report, bundle)
    alignment_characters = [
        str(record["character"])
        for record in bundle["automatic_alignment"]["characters"]
    ]
    characters = []
    for character in alignment_characters:
        evaluation = evaluation_map[character]
        characters.append(
            {
                "character": character,
                "unicode": f"U+{ord(character):04X}",
                "alignment_confidence": evaluation["alignment_confidence"],
                "evaluation_classification": evaluation["classification"],
                "running_script_delta": evaluation["delta"][
                    "running_script_score"
                ],
                "strategy": evaluation["recommended_strategy"],
            }
        )
    enhanced = [
        record["character"]
        for record in characters
        if record["strategy"] == "automatic_correspondence_features"
    ]
    fallback = [
        record["character"]
        for record in characters
        if record["strategy"] == "safe_standard_skeleton_fallback"
    ]
    recommendation = report["deployment_recommendation"]
    if enhanced != recommendation.get("enhanced_characters"):
        raise ValueError("deployment enhanced-character recommendation mismatch")
    if fallback != recommendation.get("safe_fallback_characters"):
        raise ValueError("deployment fallback-character recommendation mismatch")

    document = {
        "schema_version": PERSONAL_FONT_DEPLOYMENT_SCHEMA_VERSION,
        "type": "personal_font_generation_deployment_policy",
        "writer_id": bundle["manifest"]["writer_id"],
        "status": "ready",
        "artifacts": {
            "personal_font_profile": {
                "path": _relative_artifact_path(profile_path, output_path),
                "sha256": bundle["manifest_sha256"],
            },
            "evaluation_report": {
                "path": _relative_artifact_path(report_path, output_path),
                "sha256": file_sha256(report_path),
            },
        },
        "selection_policy": {
            "method": "multi_seed_running_script_score_quality_gate",
            "enhanced_strategy": "automatic_correspondence_features",
            "fallback_strategy": "safe_standard_skeleton_fallback",
            "unseen_character_strategy": "global_style_unseen_character_fallback",
            "manual_review_required": False,
        },
        "summary": {
            "character_count": len(characters),
            "enhanced_automatic_alignment_count": len(enhanced),
            "safe_fallback_count": len(fallback),
            "projected_running_script_score_mean": recommendation[
                "projected_running_script_score_mean"
            ],
            "projected_delta_mean": recommendation["projected_delta_mean"],
        },
        "characters": characters,
        "safety": {
            "preserves_standard_stroke_boundaries": True,
            "ligature_path_generation_enabled": False,
            "device_control_enabled": False,
        },
        "limitations": [
            "The policy is valid only for the hashed personal-font profile and evaluation report.",
            "Unseen characters use global writer style because no captured reference exists.",
            "The policy does not synthesize running-script ligature curves.",
        ],
    }
    atomic_write_json(output_path, document)
    return document


def load_personal_font_deployment(path: Path) -> Dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if document.get("schema_version") != PERSONAL_FONT_DEPLOYMENT_SCHEMA_VERSION:
        raise ValueError("personal font deployment schema_version must be 1.0")
    if document.get("type") != "personal_font_generation_deployment_policy":
        raise ValueError("personal font deployment type is invalid")
    if document.get("status") != "ready":
        raise ValueError("personal font deployment is not ready")
    if not str(document.get("writer_id", "")).strip():
        raise ValueError("personal font deployment writer_id is required")
    policy = document.get("selection_policy", {})
    if bool(policy.get("manual_review_required", True)):
        raise ValueError("personal font deployment unexpectedly requires review")
    safety = document.get("safety", {})
    if safety.get("preserves_standard_stroke_boundaries") is not True:
        raise ValueError("personal font deployment must preserve stroke boundaries")
    if safety.get("ligature_path_generation_enabled") is not False:
        raise ValueError("personal font deployment cannot enable ligature paths")
    if safety.get("device_control_enabled") is not False:
        raise ValueError("personal font deployment cannot enable device control")
    characters = document.get("characters", [])
    seen = set()
    for record in characters:
        character = str(record.get("character", "")) if isinstance(record, dict) else ""
        if len(character) != 1 or character in seen:
            raise ValueError("personal font deployment characters are invalid")
        if record.get("strategy") not in DEPLOYMENT_STRATEGIES:
            raise ValueError("personal font deployment strategy is invalid")
        seen.add(character)
    if not seen:
        raise ValueError("personal font deployment characters are required")
    summary = document.get("summary", {})
    enhanced_count = sum(
        record["strategy"] == "automatic_correspondence_features"
        for record in characters
    )
    fallback_count = len(characters) - enhanced_count
    if int(summary.get("character_count", -1)) != len(characters):
        raise ValueError("personal font deployment character count mismatch")
    if int(summary.get("enhanced_automatic_alignment_count", -1)) != enhanced_count:
        raise ValueError("personal font deployment enhanced count mismatch")
    if int(summary.get("safe_fallback_count", -1)) != fallback_count:
        raise ValueError("personal font deployment fallback count mismatch")
    return document


def _load_hashed_json_artifact(
    deployment_path: Path,
    artifact: Dict[str, Any],
    artifact_name: str,
) -> tuple[Path, Dict[str, Any]]:
    if not isinstance(artifact, dict):
        raise ValueError(f"deployment artifact {artifact_name} is required")
    relative_path = str(artifact.get("path", "")).strip()
    expected_sha256 = str(artifact.get("sha256", "")).strip().lower()
    if not relative_path or len(expected_sha256) != 64:
        raise ValueError(f"deployment artifact {artifact_name} metadata is incomplete")
    artifact_path = Path(relative_path)
    if not artifact_path.is_absolute():
        artifact_path = deployment_path.parent / artifact_path
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(
            f"deployment artifact {artifact_name} not found: {artifact_path}"
        )
    if file_sha256(artifact_path) != expected_sha256:
        raise ValueError(f"deployment artifact {artifact_name} SHA-256 mismatch")
    return artifact_path, json.loads(artifact_path.read_text(encoding="utf-8-sig"))


def load_personal_font_deployment_bundle(path: Path) -> Dict[str, Any]:
    deployment_path = Path(path).resolve()
    deployment = load_personal_font_deployment(deployment_path)
    artifacts = deployment.get("artifacts", {})
    profile_path, _ = _load_hashed_json_artifact(
        deployment_path,
        artifacts.get("personal_font_profile", {}),
        "personal_font_profile",
    )
    report_path, report = _load_hashed_json_artifact(
        deployment_path,
        artifacts.get("evaluation_report", {}),
        "evaluation_report",
    )
    bundle = load_personal_font_bundle(profile_path)
    if bundle["manifest_sha256"] != artifacts["personal_font_profile"]["sha256"]:
        raise ValueError("deployment personal font fingerprint mismatch")
    evaluation_map = _validate_evaluation_against_bundle(report, bundle)
    if deployment["writer_id"] != bundle["manifest"]["writer_id"]:
        raise ValueError("deployment and personal font writer_id mismatch")
    deployment_map = {
        str(record["character"]): record for record in deployment["characters"]
    }
    if set(deployment_map) != set(evaluation_map):
        raise ValueError("deployment character coverage mismatch")
    for character, record in deployment_map.items():
        evaluation = evaluation_map[character]
        if record.get("strategy") != evaluation.get("recommended_strategy"):
            raise ValueError("deployment strategy does not match evaluation")
        if record.get("alignment_confidence") != evaluation.get(
            "alignment_confidence"
        ):
            raise ValueError("deployment confidence does not match evaluation")
    result = dict(bundle)
    result.update(
        {
            "deployment": deployment,
            "deployment_path": deployment_path,
            "deployment_sha256": file_sha256(deployment_path),
            "evaluation_report": report,
            "evaluation_report_path": report_path,
            "evaluation_report_sha256": file_sha256(report_path),
        }
    )
    return result
