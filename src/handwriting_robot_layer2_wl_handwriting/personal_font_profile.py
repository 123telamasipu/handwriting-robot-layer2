from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .automatic_alignment import build_automatic_alignment_profile
from .storage import atomic_write_json
from .style_analysis import StyleAnalysisOptions, extract_style_profile


PERSONAL_FONT_PROFILE_SCHEMA_VERSION = "1.0"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_personal_font_profile(
    writer_id: str,
    processed_dir: Path,
    hanzi_writer_package_dir: Path,
    output_dir: Path,
    probe_path: Optional[Path] = None,
    minimum_samples: int = 20,
) -> Dict[str, Any]:
    writer_id = str(writer_id).strip()
    if not writer_id:
        raise ValueError("writer_id is required")
    output_dir = Path(output_dir)
    style_path = output_dir / "style_profile_v1.json"
    alignment_path = output_dir / "automatic_alignment_v1.json"
    manifest_path = output_dir / "personal_font_profile_v1.json"

    style = extract_style_profile(
        Path(processed_dir),
        output_path=style_path,
        probe_path=probe_path,
        options=StyleAnalysisOptions(minimum_samples=minimum_samples),
    )
    if style["writer_id"] != writer_id:
        raise ValueError("writer_id does not match processed handwriting samples")
    alignment = build_automatic_alignment_profile(
        Path(processed_dir),
        Path(hanzi_writer_package_dir),
        output_path=alignment_path,
    )
    if alignment["writer_id"] != writer_id:
        raise ValueError("writer_id does not match automatic alignment profile")
    if alignment["sample_count"] != style["source"]["sample_count"]:
        raise ValueError("style and alignment profiles use different sample counts")

    summary = alignment["summary"]
    manifest = {
        "schema_version": PERSONAL_FONT_PROFILE_SCHEMA_VERSION,
        "type": "personal_handwriting_font_profile",
        "writer_id": writer_id,
        "status": "ready",
        "source": {
            "processed_sample_count": style["source"]["sample_count"],
            "processed_sample_fingerprint_sha256": style["source"][
                "processed_sample_fingerprint_sha256"
            ],
        },
        "artifacts": {
            "style_profile": {
                "path": style_path.name,
                "sha256": file_sha256(style_path),
            },
            "automatic_alignment": {
                "path": alignment_path.name,
                "sha256": file_sha256(alignment_path),
            },
        },
        "readiness": {
            "character_count": alignment["sample_count"],
            "ready_without_manual_review_count": summary["profile_ready_count"],
            "enhanced_automatic_alignment_count": summary[
                "enhanced_alignment_count"
            ],
            "safe_fallback_count": summary["optional_review_count"],
            "manual_review_required_count": 0,
            "confidence_counts": summary["confidence_counts"],
        },
        "generation_policy": {
            "high_medium_alignment": "use_automatic_correspondence_features",
            "low_alignment": "use_standard_skeleton_without_learned_ligature",
            "manual_review_required": False,
            "ligature_path_generation_enabled": False,
        },
        "optional_quality_improvement": {
            "characters": summary["optional_review_characters"],
            "blocks_profile_creation": False,
            "notes": (
                "Optional review may improve character-specific correspondence, "
                "but the profile is already usable without it."
            ),
        },
        "limitations": [
            "The profile does not yet generate learned pen-down ligature curves.",
            "Low-confidence alignment automatically falls back to explicit pen lifts.",
            "Private style and alignment artifacts must remain outside Git.",
        ],
    }
    atomic_write_json(manifest_path, manifest)
    return manifest


def load_personal_font_profile(path: Path) -> Dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if document.get("schema_version") != PERSONAL_FONT_PROFILE_SCHEMA_VERSION:
        raise ValueError("personal font profile schema_version must be 1.0")
    if document.get("type") != "personal_handwriting_font_profile":
        raise ValueError("personal font profile type is invalid")
    if document.get("status") != "ready":
        raise ValueError("personal font profile is not ready")
    if not str(document.get("writer_id", "")).strip():
        raise ValueError("personal font profile writer_id is required")
    readiness = document.get("readiness", {})
    if int(readiness.get("manual_review_required_count", -1)) != 0:
        raise ValueError("personal font profile unexpectedly requires manual review")
    if int(readiness.get("ready_without_manual_review_count", 0)) != int(
        readiness.get("character_count", -1)
    ):
        raise ValueError("personal font profile readiness count is incomplete")
    return document


def _load_verified_artifact(
    manifest_path: Path,
    artifact: Dict[str, Any],
    artifact_name: str,
) -> tuple[Path, Dict[str, Any]]:
    if not isinstance(artifact, dict):
        raise ValueError(f"personal font artifact {artifact_name} is required")
    relative_path = str(artifact.get("path", "")).strip()
    expected_sha256 = str(artifact.get("sha256", "")).strip().lower()
    if not relative_path or len(expected_sha256) != 64:
        raise ValueError(
            f"personal font artifact {artifact_name} metadata is incomplete"
        )
    artifact_path = Path(relative_path)
    if not artifact_path.is_absolute():
        artifact_path = manifest_path.parent / artifact_path
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(
            f"personal font artifact {artifact_name} not found: {artifact_path}"
        )
    actual_sha256 = file_sha256(artifact_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"personal font artifact {artifact_name} SHA-256 mismatch"
        )
    return artifact_path, json.loads(artifact_path.read_text(encoding="utf-8-sig"))


def load_personal_font_bundle(path: Path) -> Dict[str, Any]:
    from .style_generator import validate_style_profile

    manifest_path = Path(path).resolve()
    manifest = load_personal_font_profile(manifest_path)
    artifacts = manifest.get("artifacts", {})
    style_path, style_profile = _load_verified_artifact(
        manifest_path,
        artifacts.get("style_profile", {}),
        "style_profile",
    )
    alignment_path, alignment_profile = _load_verified_artifact(
        manifest_path,
        artifacts.get("automatic_alignment", {}),
        "automatic_alignment",
    )
    validate_style_profile(style_profile)
    if alignment_profile.get("schema_version") != "1.0":
        raise ValueError("automatic alignment schema_version must be 1.0")
    if alignment_profile.get("type") != "automatic_running_script_alignment_profile":
        raise ValueError("automatic alignment profile type is invalid")
    characters = alignment_profile.get("characters")
    if not isinstance(characters, list) or not characters:
        raise ValueError("automatic alignment characters are required")
    alignment_character_values = []
    for record in characters:
        if not isinstance(record, dict):
            raise ValueError("automatic alignment character record is invalid")
        character = str(record.get("character", ""))
        if len(character) != 1:
            raise ValueError("automatic alignment character is invalid")
        if record.get("confidence") not in {"high", "medium", "low"}:
            raise ValueError("automatic alignment confidence is invalid")
        alignment_character_values.append(character)
    if len(alignment_character_values) != len(set(alignment_character_values)):
        raise ValueError("automatic alignment contains duplicate characters")

    writer_id = manifest["writer_id"]
    if style_profile["writer_id"] != writer_id:
        raise ValueError("personal font and style profile writer_id mismatch")
    if str(alignment_profile.get("writer_id", "")) != writer_id:
        raise ValueError("personal font and alignment profile writer_id mismatch")
    manifest_source = manifest.get("source", {})
    style_source = style_profile.get("source", {})
    manifest_fingerprint = manifest_source.get(
        "processed_sample_fingerprint_sha256"
    )
    if manifest_fingerprint != style_source.get(
        "processed_sample_fingerprint_sha256"
    ):
        raise ValueError("personal font and style profile fingerprint mismatch")
    if int(alignment_profile.get("sample_count", -1)) != len(characters):
        raise ValueError("automatic alignment sample count is inconsistent")
    if int(manifest.get("readiness", {}).get("character_count", -1)) != len(
        characters
    ):
        raise ValueError("personal font and alignment character counts mismatch")
    style_sample_count = style_source.get("sample_count")
    if style_sample_count is not None and int(style_sample_count) != len(characters):
        raise ValueError("style and alignment sample counts mismatch")

    sample_characters = {
        str(sample.get("character", ""))
        for sample in style_profile.get("sample_features", [])
        if isinstance(sample, dict)
    }
    alignment_characters = set(alignment_character_values)
    if alignment_characters - sample_characters:
        raise ValueError("automatic alignment characters are missing style features")

    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_sha256": file_sha256(manifest_path),
        "style_profile": style_profile,
        "style_profile_path": style_path,
        "automatic_alignment": alignment_profile,
        "automatic_alignment_path": alignment_path,
    }
