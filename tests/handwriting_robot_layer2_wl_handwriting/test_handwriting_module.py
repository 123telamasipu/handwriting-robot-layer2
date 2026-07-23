from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.handwriting_robot_layer2_wl_handwriting import (
    AutomaticAlignmentOptions,
    ConnectionAnalysisOptions,
    MachineHandoffOptions,
    PersonalFontEvaluationOptions,
    RecordingBuffer,
    RenderOptions,
    SampleStore,
    StrokePoint,
    PreprocessingOptions,
    StyleAnalysisOptions,
    StyleGenerationOptions,
    analyze_coverage,
    analyze_sample_connections,
    align_character_strokes,
    build_alignment_review_package,
    build_automatic_alignment_profile,
    analyze_processed_sample,
    build_style_profile,
    build_hanzi_writer_coverage_report,
    build_hanzi_writer_library,
    build_machine_handoff_package,
    build_personal_font_deployment,
    build_personal_font_evaluation,
    load_personal_font_profile,
    build_connection_candidate_report,
    build_report_diagnosis,
    build_similarity_report,
    compare_character_geometry,
    diagnose_character_result,
    convert_hanzi_writer_character,
    extract_style_profile,
    file_sha256,
    generate_styled_text,
    load_personal_font_bundle,
    load_personal_font_deployment_bundle,
    load_style_probe_charset,
    load_skeleton_library,
    load_target_charset,
    preprocess_sample,
    preprocess_style_probe,
    render_text,
    validate_skeleton_library,
    validate_alignment_review,
    validate_stroke_document_preflight,
)
from src.handwriting_robot_layer2_wl_handwriting.export_cli import run as run_export
from src.handwriting_robot_layer2_wl_handwriting.style_generator_cli import (
    run as run_style_generator,
)
from src.handwriting_robot_layer2_wl_handwriting.collection_report import (
    build_collection_report,
)


def make_buffer(offset: float = 0.0) -> RecordingBuffer:
    buffer = RecordingBuffer()
    buffer.begin_stroke(
        StrokePoint(0.1 + offset, 0.2, 0, pressure=0.5, source="mouse")
    )
    buffer.add_point(
        StrokePoint(0.3 + offset, 0.4, 10, pressure=0.5, source="mouse")
    )
    buffer.end_stroke(
        StrokePoint(0.5 + offset, 0.6, 20, pressure=0.5, source="mouse")
    )
    return buffer


def make_tablet_buffer() -> RecordingBuffer:
    buffer = RecordingBuffer()
    buffer.begin_stroke(StrokePoint(0.1, 0.1, 0, pressure=0.2, source="tablet"))
    for index in range(1, 9):
        buffer.add_point(
            StrokePoint(
                0.1 + index * 0.08,
                0.1 + index * 0.08,
                index * 15,
                pressure=0.2 + index * 0.05,
                source="tablet",
            )
        )
    buffer.end_stroke(
        StrokePoint(0.85, 0.85, 150, pressure=0.8, source="tablet")
    )
    return buffer


def make_style_profile() -> dict:
    return {
        "schema_version": "1.0",
        "type": "handwriting_style_profile",
        "writer_id": "test_user",
        "source": {"processed_sample_fingerprint_sha256": "synthetic-test"},
        "generation_priors": {
            "layout": {
                "canvas_width": 0.65,
                "canvas_height": 0.72,
                "center_x": 0.49,
                "center_y": 0.52,
            },
            "deformation": {
                "vertical_slant_deg": 2.0,
                "horizontal_angle_deg": -5.0,
                "straightness": 0.7,
            },
            "motion": {
                "active_speed": 0.8,
                "pen_up_pause_mean_ms": 120.0,
            },
            "pressure": {"mean": 0.5},
            "variability": {
                "canvas_width_std": 0.04,
                "canvas_height_std": 0.05,
                "center_x_std": 0.02,
                "center_y_std": 0.02,
                "vertical_slant_std": 3.0,
            },
        },
    }


def add_personal_font_features(profile: dict) -> dict:
    profile = json.loads(json.dumps(profile))
    profile["source"]["sample_count"] = 2
    profile["sample_features"] = [
        {
            "character": "永",
            "layout": {
                "width": 0.58,
                "height": 0.81,
                "bounding_box_center_x": 0.46,
                "bounding_box_center_y": 0.55,
            },
            "geometry": {
                "vertical_slant_deg": 8.0,
                "horizontal_angle_deg": -8.0,
                "straightness": 0.62,
            },
        },
        {
            "character": "文",
            "layout": {
                "width": 0.7,
                "height": 0.68,
                "bounding_box_center_x": 0.51,
                "bounding_box_center_y": 0.48,
            },
            "geometry": {
                "vertical_slant_deg": -2.0,
                "horizontal_angle_deg": -3.0,
                "straightness": 0.78,
            },
        },
    ]
    return profile


def write_personal_font_fixture(
    root: Path,
    alignment_writer_id: str = "test_user",
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    style_path = root / "style_profile_v1.json"
    alignment_path = root / "automatic_alignment_v1.json"
    manifest_path = root / "personal_font_profile_v1.json"
    style = add_personal_font_features(make_style_profile())
    alignment = {
        "schema_version": "1.0",
        "type": "automatic_running_script_alignment_profile",
        "writer_id": alignment_writer_id,
        "sample_count": 2,
        "characters": [
            {"character": "永", "confidence": "high", "alignment_groups": []},
            {"character": "文", "confidence": "low", "alignment_groups": []},
        ],
    }
    style_path.write_text(
        json.dumps(style, ensure_ascii=False), encoding="utf-8"
    )
    alignment_path.write_text(
        json.dumps(alignment, ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "schema_version": "1.0",
        "type": "personal_handwriting_font_profile",
        "writer_id": "test_user",
        "status": "ready",
        "source": {
            "processed_sample_fingerprint_sha256": "synthetic-test"
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
            "character_count": 2,
            "ready_without_manual_review_count": 2,
            "manual_review_required_count": 0,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return manifest_path


def write_personal_font_evaluation_fixture(
    path: Path,
    manifest_path: Path,
    enhanced_characters: list[str],
) -> Path:
    enhanced = set(enhanced_characters)
    strategies = {
        "永": (
            "automatic_correspondence_features"
            if "永" in enhanced
            else "safe_standard_skeleton_fallback"
        ),
        "文": "safe_standard_skeleton_fallback",
    }
    fallback_characters = [
        character for character in ("永", "文") if character not in enhanced
    ]
    document = {
        "schema_version": "1.0",
        "type": "personal_font_generation_comparison_report",
        "writer_id": "test_user",
        "personal_font_manifest_sha256": file_sha256(manifest_path),
        "evaluated_character_count": 2,
        "skipped_characters": [],
        "invariant_failures": [],
        "deployment_recommendation": {
            "status": "ready_with_per_character_fallback",
            "enhanced_characters": enhanced_characters,
            "safe_fallback_characters": fallback_characters,
            "projected_running_script_score_mean": 0.8,
            "projected_delta_mean": 0.01,
            "manual_review_required": False,
        },
        "characters": [
            {
                "character": "永",
                "alignment_confidence": "high",
                "classification": "stable",
                "delta": {"running_script_score": 0.0},
                "recommended_strategy": strategies["永"],
            },
            {
                "character": "文",
                "alignment_confidence": "low",
                "classification": "stable",
                "delta": {"running_script_score": 0.0},
                "recommended_strategy": strategies["文"],
            },
        ],
    }
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def write_machine_handoff_deployment_fixture(root: Path) -> Path:
    manifest_path = write_personal_font_fixture(root)
    style_path = root / "style_profile_v1.json"
    alignment_path = root / "automatic_alignment_v1.json"
    style = json.loads(style_path.read_text(encoding="utf-8"))
    extra_sample = json.loads(json.dumps(style["sample_features"][1]))
    extra_sample["character"] = "好"
    style["sample_features"].append(extra_sample)
    style["source"]["sample_count"] = 3
    style_path.write_text(json.dumps(style, ensure_ascii=False), encoding="utf-8")
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    alignment["characters"][1]["confidence"] = "high"
    alignment["characters"].append(
        {"character": "好", "confidence": "low", "alignment_groups": []}
    )
    alignment["sample_count"] = 3
    alignment_path.write_text(
        json.dumps(alignment, ensure_ascii=False), encoding="utf-8"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["style_profile"]["sha256"] = file_sha256(style_path)
    manifest["artifacts"]["automatic_alignment"]["sha256"] = file_sha256(
        alignment_path
    )
    manifest["readiness"]["character_count"] = 3
    manifest["readiness"]["ready_without_manual_review_count"] = 3
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    report_path = root / "evaluation.json"
    report = {
        "schema_version": "1.0",
        "type": "personal_font_generation_comparison_report",
        "writer_id": "test_user",
        "personal_font_manifest_sha256": file_sha256(manifest_path),
        "evaluated_character_count": 3,
        "skipped_characters": [],
        "invariant_failures": [],
        "deployment_recommendation": {
            "status": "ready_with_per_character_fallback",
            "enhanced_characters": ["永"],
            "safe_fallback_characters": ["文", "好"],
            "projected_running_script_score_mean": 0.8,
            "projected_delta_mean": 0.01,
            "manual_review_required": False,
        },
        "characters": [
            {
                "character": "永",
                "alignment_confidence": "high",
                "classification": "improved",
                "delta": {"running_script_score": 0.02},
                "recommended_strategy": "automatic_correspondence_features",
            },
            {
                "character": "文",
                "alignment_confidence": "high",
                "classification": "regressed",
                "delta": {"running_script_score": -0.02},
                "recommended_strategy": "safe_standard_skeleton_fallback",
            },
            {
                "character": "好",
                "alignment_confidence": "low",
                "classification": "stable",
                "delta": {"running_script_score": 0.0},
                "recommended_strategy": "safe_standard_skeleton_fallback",
            },
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    deployment_path = root / "personal_font_deployment_v1.json"
    build_personal_font_deployment(manifest_path, report_path, deployment_path)
    return deployment_path


def write_hanzi_writer_fixture(root: Path, glyphs: dict[str, dict]) -> Path:
    package_dir = root / "package"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "hanzi-writer-data",
                "version": "2.0.1",
                "repository": "chanind/hanzi-writer-data",
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "ARPHICPL.TXT").write_text(
        "ARPHIC PUBLIC LICENSE\nfixture only\n", encoding="utf-8"
    )
    for character, document in glyphs.items():
        (package_dir / f"{character}.json").write_text(
            json.dumps(document, ensure_ascii=False), encoding="utf-8"
        )
    return root


class CharsetTests(unittest.TestCase):
    def test_bundled_charset_is_unique(self) -> None:
        entries = load_target_charset()
        self.assertEqual(1140, len(entries))
        self.assertEqual(1140, len({entry.character for entry in entries}))
        self.assertEqual(
            1000, sum(entry.category == "hanzi_frequency" for entry in entries)
        )
        self.assertEqual("的", entries[0].character)

    def test_style_probe_contains_100_unique_target_characters(self) -> None:
        target_entries = load_target_charset()
        entries = load_style_probe_charset(target_entries=target_entries)

        self.assertEqual(100, len(entries))
        self.assertEqual(100, len({entry.character for entry in entries}))
        self.assertEqual("一", entries[0].character)
        self.assertEqual("曲", entries[-1].character)

    def test_demo_skeleton_library_has_ordered_unique_glyphs(self) -> None:
        library = load_skeleton_library()

        self.assertFalse(library["authoritative"])
        self.assertEqual(["永", "文"], [glyph["character"] for glyph in library["glyphs"]])
        self.assertEqual(
            [1, 2, 3, 4, 5],
            [stroke["order"] for stroke in library["glyphs"][0]["strokes"]],
        )

    def test_skeleton_validation_rejects_out_of_range_points(self) -> None:
        library = load_skeleton_library()
        library["glyphs"][0]["strokes"][0]["points"][0][0] = 1.1

        with self.assertRaisesRegex(ValueError, "must be between 0 and 1"):
            validate_skeleton_library(library)

    def test_hanzi_writer_adapter_flips_y_and_preserves_stroke_order(self) -> None:
        source = {
            "strokes": ["outline-1", "outline-2"],
            "medians": [
                [[0, 0], [1024, 1024]],
                [[256, 768], [768, 256]],
            ],
        }

        glyph = convert_hanzi_writer_character("永", source)

        self.assertEqual(2, glyph["stroke_count"])
        self.assertEqual([1, 2], [stroke["order"] for stroke in glyph["strokes"]])
        self.assertEqual([[0.05, 0.95], [0.95, 0.05]], glyph["strokes"][0]["points"])
        self.assertEqual("unknown", glyph["strokes"][0]["stroke_type"])

    def test_hanzi_writer_library_and_coverage_use_local_package(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        package_root = write_hanzi_writer_fixture(
            Path(temporary.name),
            {
                "一": {
                    "strokes": ["outline"],
                    "medians": [[[100, 500], [900, 500]]],
                },
                "二": {
                    "strokes": ["outline-1", "outline-2"],
                    "medians": [
                        [[200, 650], [800, 650]],
                        [[150, 350], [850, 350]],
                    ],
                },
            },
        )
        entries = [
            entry
            for entry in load_target_charset()
            if entry.character in {"一", "二", "你"}
        ]

        library = build_hanzi_writer_library(package_root, "一二")
        report = build_hanzi_writer_coverage_report(
            package_root, entries=entries
        )

        self.assertFalse(library["authoritative"])
        self.assertEqual("Arphic Public License", library["license"]["name"])
        self.assertEqual(["一", "二"], [glyph["character"] for glyph in library["glyphs"]])
        self.assertEqual(3, report["target_count"])
        self.assertEqual(2, report["available_count"])
        self.assertEqual(["你"], report["missing_characters"])


class StorageAndRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)
        self.entries = {entry.character: entry for entry in load_target_charset()}
        self.store = SampleStore(self.data_dir, "test_user", "脱敏测试用户")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_draft_commit_and_manifest(self) -> None:
        entry = self.entries["你"]
        buffer = make_buffer()
        draft = self.store.save_draft(entry, 1, buffer)
        self.assertTrue(draft and draft.exists())

        sample = self.store.commit_sample(entry, 1, buffer)
        self.assertTrue(sample.exists())
        self.assertFalse(draft.exists())
        self.assertEqual(1, self.store.completed_count())
        saved = json.loads(sample.read_text(encoding="utf-8"))
        self.assertEqual("complete", saved["status"])
        self.assertEqual(1, saved["stroke_count"])
        self.assertEqual(3, saved["point_count"])

    def test_commit_rejects_an_active_stroke(self) -> None:
        buffer = RecordingBuffer()
        buffer.begin_stroke(StrokePoint(0.1, 0.2, 0, source="mouse"))
        buffer.add_point(StrokePoint(0.3, 0.4, 10, source="mouse"))

        with self.assertRaisesRegex(ValueError, "finish the current stroke"):
            self.store.commit_sample(self.entries["你"], 1, buffer)

    def test_commit_can_require_tablet_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "required source: tablet"):
            self.store.commit_sample(
                self.entries["你"],
                1,
                make_buffer(),
                required_source="tablet",
            )

        buffer = RecordingBuffer()
        buffer.begin_stroke(StrokePoint(0.1, 0.2, 0, source="tablet"))
        buffer.end_stroke(StrokePoint(0.3, 0.4, 10, source="tablet"))
        sample = self.store.commit_sample(
            self.entries["你"], 1, buffer, required_source="tablet"
        )
        self.assertTrue(sample.exists())

    def test_session_metadata_is_saved_separately(self) -> None:
        path = self.store.save_session(
            "tablet-20260721-001",
            {"collection_mode": "style_probe_100", "device": {"model": "demo"}},
        )
        document = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("tablet-20260721-001", document["session_id"])
        self.assertEqual("style_probe_100", document["metadata"]["collection_mode"])

    def test_collection_report_summarizes_tablet_probe_quality(self) -> None:
        self.store.commit_sample(
            self.entries["一"], 1, make_tablet_buffer(), required_source="tablet"
        )
        report = build_collection_report(self.store, ["一", "二"])

        self.assertEqual(2, report["target_count"])
        self.assertEqual(1, report["completed_count"])
        self.assertEqual(["二"], report["missing_characters"])
        self.assertEqual(1, report["tablet_sample_count"])
        self.assertEqual([], report["review_samples"])
        self.assertEqual(0.2, report["statistics"]["pressure_min"])
        self.assertEqual(0.8, report["statistics"]["pressure_max"])

    def test_preprocessing_preserves_raw_sample_and_normalizes_geometry(self) -> None:
        sample_path = self.store.commit_sample(
            self.entries["一"], 1, make_tablet_buffer(), required_source="tablet"
        )
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        original_text = sample_path.read_text(encoding="utf-8")
        processed = preprocess_sample(
            sample,
            PreprocessingOptions(
                duplicate_distance=0.0005,
                resample_spacing=0.05,
                smoothing_passes=1,
                glyph_margin=0.1,
            ),
        )

        self.assertEqual(original_text, sample_path.read_text(encoding="utf-8"))
        self.assertEqual("processed_handwriting_sample", processed["type"])
        self.assertEqual(
            sample["stroke_count"],
            len(processed["representations"]["canvas"]["strokes"]),
        )
        glyph_box = processed["representations"]["glyph"]["transform"][
            "target_bounding_box"
        ]
        self.assertGreaterEqual(glyph_box["x_min"], 0.1 - 1e-6)
        self.assertLessEqual(glyph_box["x_max"], 0.9 + 1e-6)
        self.assertEqual(
            0,
            processed["representations"]["dynamics"]["strokes"][0]["points"][0][
                "t_ms"
            ],
        )

    def test_preprocessing_keeps_pressure_changes_at_stationary_points(self) -> None:
        sample = self.store.build_document(
            self.entries["一"], 1, make_tablet_buffer(), "complete"
        )
        first_stroke = sample["strokes"][0]["points"]
        stationary = dict(first_stroke[0])
        stationary["pressure"] = 0.7
        first_stroke.insert(1, stationary)
        sample["point_count"] += 1

        processed = preprocess_sample(sample)
        dynamics = processed["representations"]["dynamics"]["strokes"][0][
            "points"
        ]
        self.assertEqual(0.2, dynamics[0]["pressure"])
        self.assertEqual(0.7, dynamics[1]["pressure"])

    def test_preprocess_style_probe_writes_separate_outputs(self) -> None:
        entries = [self.entries["一"], self.entries["二"]]
        self.store.commit_sample(
            entries[0], 1, make_tablet_buffer(), required_source="tablet"
        )
        self.store.commit_sample(
            entries[1], 1, make_tablet_buffer(), required_source="tablet"
        )
        output_dir = self.data_dir / "processed"

        report = preprocess_style_probe(
            self.store,
            output_dir,
            entries=entries,
            options=PreprocessingOptions(resample_spacing=0.05),
        )

        self.assertEqual(2, report["processed_count"])
        self.assertEqual([], report["failed_samples"])
        self.assertTrue((output_dir / "preprocessing_report.json").exists())
        self.assertTrue((output_dir / entries[0].unicode / "v01.json").exists())

    def test_style_analysis_extracts_layout_motion_and_geometry(self) -> None:
        sample = self.store.build_document(
            self.entries["一"], 1, make_tablet_buffer(), "complete"
        )
        processed = preprocess_sample(
            sample, PreprocessingOptions(resample_spacing=0.05)
        )

        features = analyze_processed_sample(processed)

        self.assertEqual("一", features["character"])
        self.assertGreater(features["layout"]["width"], 0.0)
        self.assertGreater(features["dynamics"]["active_speed"], 0.0)
        self.assertEqual(0.44, features["dynamics"]["pressure_mean"])
        self.assertAlmostEqual(
            1.0,
            sum(features["geometry"]["direction_histogram"].values()),
            places=5,
        )
        self.assertGreater(features["geometry"]["diagonal_share"], 0.9)

    def test_style_profile_is_deterministic_and_writes_private_output(self) -> None:
        entries = [self.entries["一"], self.entries["二"]]
        processed_dir = self.data_dir / "processed"
        for index, entry in enumerate(entries):
            sample = self.store.build_document(
                entry, 1, make_tablet_buffer(), "complete"
            )
            sample["strokes"][0]["points"][-1]["x"] -= index * 0.1
            processed = preprocess_sample(
                sample, PreprocessingOptions(resample_spacing=0.05)
            )
            path = processed_dir / entry.unicode / "v01.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(processed, ensure_ascii=False), encoding="utf-8"
            )
        probe_path = self.data_dir / "probe.json"
        probe_path.write_text(
            json.dumps(
                {
                    "groups": [
                        {
                            "id": "basic",
                            "label": "基础",
                            "analysis_focus": "测试",
                            "characters": "一二",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        output_path = self.data_dir / "profiles" / "style_profile.json"
        options = StyleAnalysisOptions(minimum_samples=2)

        first = extract_style_profile(
            processed_dir,
            output_path=output_path,
            probe_path=probe_path,
            options=options,
        )
        second = build_style_profile(
            [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(processed_dir.glob("U+*/v*.json"))
            ],
            probe_path=probe_path,
            options=options,
        )

        self.assertEqual(first, second)
        self.assertTrue(output_path.exists())
        self.assertEqual("handwriting_style_profile", first["type"])
        self.assertEqual(1.0, first["quality"]["style_probe_coverage"])
        self.assertEqual("high", first["quality"]["feature_estimation_confidence"])
        self.assertEqual(["tilt_signal_unavailable"], first["quality"]["warnings"])
        self.assertEqual(2, len(first["sample_features"]))
        self.assertIn("vertical_slant_deg", first["generation_priors"]["deformation"])

    def test_style_profile_rejects_too_few_samples(self) -> None:
        sample = self.store.build_document(
            self.entries["一"], 1, make_tablet_buffer(), "complete"
        )
        processed = preprocess_sample(sample)

        with self.assertRaisesRegex(ValueError, "at least 2 processed samples"):
            build_style_profile(
                [processed], options=StyleAnalysisOptions(minimum_samples=2)
            )

    def test_style_generator_is_deterministic_and_preserves_stroke_order(self) -> None:
        library = load_skeleton_library()
        profile = make_style_profile()
        options = StyleGenerationOptions(random_seed=42, variation_strength=0.5)

        first = generate_styled_text("永文", library, profile, options)
        second = generate_styled_text("永文", library, profile, options)
        different = generate_styled_text(
            "永文",
            library,
            profile,
            StyleGenerationOptions(random_seed=43, variation_strength=0.5),
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual(9, len(first["strokes"]))
        self.assertEqual(list(range(1, 10)), [stroke["order"] for stroke in first["strokes"]])
        self.assertTrue(all(stroke["pen_down"] for stroke in first["strokes"]))
        self.assertEqual(
            "ordered_skeleton_style_transform",
            first["generation"]["method"],
        )
        self.assertEqual(
            [1, 2, 3, 4, 5],
            first["generation"]["characters"][0]["stroke_orders"],
        )
        self.assertIn(
            "non_authoritative_skeleton_library",
            first["generation"]["warnings"],
        )
        self.assertTrue(
            all(
                0.0 <= coordinate <= 210.0
                for stroke in first["strokes"]
                for point in stroke["points"]
                for coordinate in point
            )
        )

    def test_personal_font_bundle_selects_enhanced_safe_and_unseen_strategies(
        self,
    ) -> None:
        manifest_path = write_personal_font_fixture(self.data_dir / "profile")
        bundle = load_personal_font_bundle(manifest_path)
        library = load_skeleton_library()
        unseen_glyph = json.loads(json.dumps(library["glyphs"][1]))
        unseen_glyph["character"] = "好"
        unseen_glyph["unicode"] = "U+597D"
        library["glyphs"].append(unseen_glyph)
        options = StyleGenerationOptions(random_seed=17)

        first = generate_styled_text(
            "永文好",
            library,
            bundle["style_profile"],
            options,
            personal_font_bundle=bundle,
        )
        second = generate_styled_text(
            "永文好",
            library,
            bundle["style_profile"],
            options,
            personal_font_bundle=bundle,
        )

        self.assertEqual(first, second)
        records = first["generation"]["characters"]
        self.assertEqual(
            "automatic_correspondence_features",
            records[0]["personal_font_strategy"],
        )
        self.assertEqual(
            "safe_standard_skeleton_fallback",
            records[1]["personal_font_strategy"],
        )
        self.assertEqual(
            "global_style_unseen_character_fallback",
            records[2]["personal_font_strategy"],
        )
        self.assertTrue(all(not record["ligature_applied"] for record in records))
        self.assertEqual(13, len(first["strokes"]))
        self.assertEqual(
            list(range(1, 14)),
            [stroke["order"] for stroke in first["strokes"]],
        )
        self.assertTrue(
            first["generation"]["personal_font"][
                "preserves_standard_stroke_boundaries"
            ]
        )

    def test_personal_font_bundle_rejects_artifact_hash_mismatch(self) -> None:
        manifest_path = write_personal_font_fixture(self.data_dir / "profile")
        style_path = manifest_path.parent / "style_profile_v1.json"
        style_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            load_personal_font_bundle(manifest_path)

    def test_personal_font_bundle_rejects_writer_mismatch(self) -> None:
        manifest_path = write_personal_font_fixture(
            self.data_dir / "profile",
            alignment_writer_id="other_user",
        )

        with self.assertRaisesRegex(ValueError, "writer_id mismatch"):
            load_personal_font_bundle(manifest_path)

    def test_personal_font_evaluation_compares_multi_seed_generation(self) -> None:
        manifest_path = write_personal_font_fixture(self.data_dir / "profile")
        processed_dir = self.data_dir / "processed"
        for character in ("永", "文"):
            sample = self.store.build_document(
                self.entries[character], 1, make_tablet_buffer(), "complete"
            )
            processed = preprocess_sample(sample)
            path = processed_dir / f"U+{ord(character):04X}" / "v01.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(processed, ensure_ascii=False), encoding="utf-8"
            )
        package_root = write_hanzi_writer_fixture(
            self.data_dir / "hanzi-writer",
            {
                "永": {
                    "strokes": ["outline"],
                    "medians": [[[100, 900], [900, 100]]],
                },
                "文": {
                    "strokes": ["outline"],
                    "medians": [[[100, 100], [900, 900]]],
                },
            },
        )
        evaluation_options = PersonalFontEvaluationOptions(
            random_seeds=(3, 5),
            meaningful_delta=0.001,
        )

        first = build_personal_font_evaluation(
            processed_dir,
            manifest_path,
            package_root,
            evaluation_options=evaluation_options,
        )
        second = build_personal_font_evaluation(
            processed_dir,
            manifest_path,
            package_root,
            evaluation_options=evaluation_options,
        )

        self.assertEqual(first, second)
        self.assertEqual(2, first["evaluated_character_count"])
        self.assertEqual([], first["invariant_failures"])
        self.assertEqual(
            "safe_standard_skeleton_fallback",
            first["characters"][1]["recommended_strategy"],
        )
        self.assertEqual(
            0.0,
            first["characters"][1]["delta"]["running_script_score"],
        )
        self.assertFalse(
            first["deployment_recommendation"]["manual_review_required"]
        )

    def test_personal_font_deployment_forces_evaluated_character_fallback(
        self,
    ) -> None:
        profile_dir = self.data_dir / "profile"
        manifest_path = write_personal_font_fixture(profile_dir)
        report_path = write_personal_font_evaluation_fixture(
            profile_dir / "evaluation.json",
            manifest_path,
            enhanced_characters=[],
        )
        deployment_path = profile_dir / "personal_font_deployment_v1.json"
        deployment = build_personal_font_deployment(
            manifest_path, report_path, deployment_path
        )
        bundle = load_personal_font_deployment_bundle(deployment_path)

        document = generate_styled_text(
            "永文",
            load_skeleton_library(),
            bundle["style_profile"],
            personal_font_bundle=bundle,
        )

        self.assertEqual(0, deployment["summary"]["enhanced_automatic_alignment_count"])
        self.assertEqual(2, deployment["summary"]["safe_fallback_count"])
        records = document["generation"]["characters"]
        self.assertEqual(
            ["safe_standard_skeleton_fallback"] * 2,
            [record["personal_font_strategy"] for record in records],
        )
        self.assertTrue(
            all(record["deployment_policy_applied"] for record in records)
        )
        self.assertIn(
            "deployment", document["generation"]["personal_font"]
        )

    def test_personal_font_deployment_rejects_tampered_evaluation(self) -> None:
        profile_dir = self.data_dir / "profile"
        manifest_path = write_personal_font_fixture(profile_dir)
        report_path = write_personal_font_evaluation_fixture(
            profile_dir / "evaluation.json",
            manifest_path,
            enhanced_characters=[],
        )
        deployment_path = profile_dir / "personal_font_deployment_v1.json"
        build_personal_font_deployment(
            manifest_path, report_path, deployment_path
        )
        report_path.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            load_personal_font_deployment_bundle(deployment_path)

    def test_machine_handoff_builds_preflighted_non_device_package(self) -> None:
        profile_dir = self.data_dir / "profile"
        deployment_path = write_machine_handoff_deployment_fixture(profile_dir)
        package_root = write_hanzi_writer_fixture(
            self.data_dir / "hanzi-writer",
            {
                character: {
                    "strokes": ["outline"],
                    "medians": [[[100, 500], [900, 500]]],
                }
                for character in ("永", "文", "好", "世")
            },
        )
        output_dir = self.data_dir / "handoff"

        package = build_machine_handoff_package(
            deployment_path,
            package_root,
            output_dir,
            unseen_candidates="世",
            handoff_options=MachineHandoffOptions(
                characters_per_scenario=1,
                max_point_spacing_mm=1.0,
            ),
        )

        self.assertFalse(package["machine_ready"])
        self.assertEqual(
            "ready_for_layout_and_device_review", package["status"]
        )
        self.assertEqual("pass", package["software_preflight_summary"]["status"])
        self.assertEqual(5, package["software_preflight_summary"]["artifact_count"])
        self.assertFalse(package["safety_boundary"]["controls_device"])
        self.assertFalse(package["safety_boundary"]["contains_device_commands"])
        self.assertEqual(
            "pending", package["required_external_review"]["status"]
        )
        self.assertTrue((output_dir / "handoff_manifest.json").exists())
        for artifact in package["artifacts"].values():
            self.assertEqual("pass", artifact["software_preflight"]["status"])
            self.assertTrue((output_dir / artifact["path"]).exists())

    def test_machine_handoff_preflight_rejects_out_of_page_point(self) -> None:
        document = generate_styled_text(
            "永", load_skeleton_library(), make_style_profile()
        )
        document["strokes"][0]["points"][0][0] = 999.0

        with self.assertRaisesRegex(ValueError, "outside page bounds"):
            validate_stroke_document_preflight(document)

    def test_style_generator_rejects_missing_skeletons(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing ordered stroke skeletons"):
            generate_styled_text(
                "你", load_skeleton_library(), make_style_profile()
            )

    def test_style_generator_cli_writes_stroke_document(self) -> None:
        profile_path = self.data_dir / "profile.json"
        request_path = self.data_dir / "request.json"
        output_path = self.data_dir / "generated.json"
        profile_path.write_text(
            json.dumps(make_style_profile(), ensure_ascii=False), encoding="utf-8"
        )
        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "user_id": "test_user",
                    "text": "永",
                    "style_profile_path": str(profile_path),
                    "options": {"random_seed": 7},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8-sig",
        )

        exit_code = run_style_generator([str(request_path), str(output_path)])

        self.assertEqual(0, exit_code)
        document = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual("stroke_document", document["type"])
        self.assertEqual("test_user", document["user_id"])
        self.assertEqual(5, len(document["strokes"]))

    def test_style_generator_cli_reads_hanzi_writer_data_on_demand(self) -> None:
        profile_path = self.data_dir / "profile.json"
        request_path = self.data_dir / "request.json"
        output_path = self.data_dir / "generated.json"
        package_root = write_hanzi_writer_fixture(
            self.data_dir / "hanzi-writer",
            {
                "永": {
                    "strokes": ["outline"],
                    "medians": [[[100, 500], [900, 500]]],
                }
            },
        )
        profile_path.write_text(
            json.dumps(make_style_profile(), ensure_ascii=False), encoding="utf-8"
        )
        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "user_id": "test_user",
                    "text": "永",
                    "style_profile_path": str(profile_path),
                    "hanzi_writer_package_dir": str(package_root),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = run_style_generator([str(request_path), str(output_path)])

        self.assertEqual(0, exit_code)
        document = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(document["strokes"]))
        self.assertEqual(
            "third_party_ordered_medians",
            document["generation"]["skeleton_library"]["quality_level"],
        )
        self.assertEqual(
            "Arphic Public License",
            document["generation"]["skeleton_library"]["license"]["name"],
        )

    def test_style_generator_cli_auto_detects_personal_font_profile(self) -> None:
        data_dir = self.data_dir / "handwriting"
        manifest_path = write_personal_font_fixture(
            data_dir / "style_profiles" / "test_user"
        )
        self.assertTrue(manifest_path.exists())
        request_path = self.data_dir / "request.json"
        output_path = self.data_dir / "generated.json"
        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "user_id": "test_user",
                    "text": "永文",
                    "options": {"random_seed": 9},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = run_style_generator(
            [
                str(request_path),
                str(output_path),
                "--data-dir",
                str(data_dir),
            ]
        )

        self.assertEqual(0, exit_code)
        document = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertIn("personal_font", document["generation"])
        self.assertEqual(
            "automatic_correspondence_features",
            document["generation"]["characters"][0][
                "personal_font_strategy"
            ],
        )

    def test_style_generator_cli_prefers_auto_detected_deployment_policy(
        self,
    ) -> None:
        data_dir = self.data_dir / "handwriting"
        profile_dir = data_dir / "style_profiles" / "test_user"
        manifest_path = write_personal_font_fixture(profile_dir)
        report_path = write_personal_font_evaluation_fixture(
            profile_dir / "evaluation.json",
            manifest_path,
            enhanced_characters=[],
        )
        build_personal_font_deployment(
            manifest_path,
            report_path,
            profile_dir / "personal_font_deployment_v1.json",
        )
        request_path = self.data_dir / "request.json"
        output_path = self.data_dir / "generated.json"
        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "user_id": "test_user",
                    "text": "永",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = run_style_generator(
            [
                str(request_path),
                str(output_path),
                "--data-dir",
                str(data_dir),
            ]
        )

        self.assertEqual(0, exit_code)
        document = json.loads(output_path.read_text(encoding="utf-8"))
        record = document["generation"]["characters"][0]
        self.assertEqual(
            "safe_standard_skeleton_fallback",
            record["personal_font_strategy"],
        )
        self.assertTrue(record["deployment_policy_applied"])
        self.assertEqual(
            "deployment_policy_per_character",
            document["generation"]["personal_font"][
                "captured_high_medium_strategy"
            ],
        )

    def test_style_generator_cli_explicit_style_profile_stays_compatible(self) -> None:
        profile_dir = self.data_dir / "profile"
        manifest_path = write_personal_font_fixture(profile_dir)
        profile_path = profile_dir / "style_profile_v1.json"
        request_path = self.data_dir / "request.json"
        output_path = self.data_dir / "generated.json"
        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "user_id": "test_user",
                    "text": "永",
                    "style_profile_path": str(profile_path),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = run_style_generator([str(request_path), str(output_path)])

        self.assertTrue(manifest_path.exists())
        self.assertEqual(0, exit_code)
        document = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertNotIn("personal_font", document["generation"])

    def test_style_generator_supports_single_axis_glyphs(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        package_root = write_hanzi_writer_fixture(
            Path(temporary.name),
            {
                "一": {
                    "strokes": ["outline"],
                    "medians": [[[100, 500], [900, 500]]],
                }
            },
        )
        library = build_hanzi_writer_library(package_root, "一")

        document = generate_styled_text("一", library, make_style_profile())

        self.assertEqual(1, len(document["strokes"]))
        self.assertGreater(len(document["strokes"][0]["points"]), 2)

    def test_geometry_similarity_scores_matching_trajectories(self) -> None:
        sample = self.store.build_document(
            self.entries["一"], 1, make_tablet_buffer(), "complete"
        )
        processed = preprocess_sample(
            sample, PreprocessingOptions(resample_spacing=0.05)
        )
        glyph_points = processed["representations"]["glyph"]["strokes"][0][
            "points"
        ]
        document = {
            "type": "stroke_document",
            "user_id": "test_user",
            "strokes": [
                {
                    "order": 1,
                    "pen_down": True,
                    "points": [[point["x"] * 8.0, point["y"] * 8.0] for point in glyph_points],
                }
            ],
            "generation": {
                "characters": [
                    {"character": "一", "unicode": "U+4E00", "stroke_orders": [1]}
                ]
            },
        }

        result = compare_character_geometry(
            processed, document, document["generation"]["characters"][0]
        )

        self.assertEqual(1.0, result["overall_score"])
        self.assertEqual(1.0, result["scores"]["global_shape_score"])
        self.assertEqual(1.0, result["scores"]["ordered_stroke_score"])

    def test_similarity_report_evaluates_common_characters_and_skips_missing(self) -> None:
        processed_dir = self.data_dir / "processed"
        sample = self.store.build_document(
            self.entries["一"], 1, make_tablet_buffer(), "complete"
        )
        processed = preprocess_sample(sample)
        path = processed_dir / "U+4E00" / "v01.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(processed, ensure_ascii=False), encoding="utf-8")
        document = {
            "type": "stroke_document",
            "user_id": "test_user",
            "strokes": [
                {"order": 1, "pen_down": True, "points": [[0.0, 0.0], [1.0, 1.0]]},
                {"order": 2, "pen_down": True, "points": [[2.0, 0.0], [3.0, 1.0]]},
            ],
            "generation": {
                "characters": [
                    {"character": "一", "stroke_orders": [1]},
                    {"character": "二", "stroke_orders": [2]},
                ]
            },
        }

        first = build_similarity_report(processed_dir, document)
        second = build_similarity_report(processed_dir, document)

        self.assertEqual(first, second)
        self.assertEqual(1, first["evaluated_character_count"])
        self.assertEqual(1, first["skipped_character_count"])
        self.assertEqual("二", first["skipped"][0]["character"])
        self.assertIsNotNone(first["summary"]["overall_score_mean"])
        self.assertIn("diagnosis", first)

    def test_similarity_diagnosis_separates_segmentation_and_shape_issues(self) -> None:
        segmentation = diagnose_character_result(
            {
                "reference_stroke_count": 5,
                "generated_stroke_count": 6,
                "scores": {
                    "global_shape_score": 0.86,
                    "ordered_stroke_score": 0.0,
                    "aspect_ratio_score": 0.9,
                    "direction_score": 0.84,
                },
            }
        )
        shape_issue = diagnose_character_result(
            {
                "reference_stroke_count": 5,
                "generated_stroke_count": 5,
                "scores": {
                    "global_shape_score": 0.65,
                    "ordered_stroke_score": 0.62,
                    "aspect_ratio_score": 0.65,
                    "direction_score": 0.61,
                },
            }
        )

        self.assertEqual(
            "likely_running_script_variant",
            segmentation["primary_category"],
        )
        self.assertEqual("low", segmentation["review_priority"])
        self.assertEqual("shape_difference", shape_issue["primary_category"])
        self.assertEqual("high", shape_issue["review_priority"])

        report = build_report_diagnosis(
            [
                {"character": "字", "overall_score": 0.6, **{
                    "reference_stroke_count": 5,
                    "generated_stroke_count": 6,
                    "scores": {
                        "global_shape_score": 0.86,
                        "ordered_stroke_score": 0.0,
                        "aspect_ratio_score": 0.9,
                        "direction_score": 0.84,
                    },
                }},
                {"character": "计", "overall_score": 0.7, **{
                    "reference_stroke_count": 4,
                    "generated_stroke_count": 4,
                    "scores": {
                        "global_shape_score": 0.65,
                        "ordered_stroke_score": 0.62,
                        "aspect_ratio_score": 0.65,
                        "direction_score": 0.61,
                    },
                }},
            ]
        )
        self.assertEqual("计", report["review_queue"][0]["character"])

    def test_style_analysis_records_natural_handwriting_stroke_behavior(self) -> None:
        sample = self.store.build_document(
            self.entries["一"], 1, make_tablet_buffer(), "complete"
        )
        sample["character"]["expected_stroke_count"] = 2
        processed = preprocess_sample(sample)

        features = analyze_processed_sample(processed)

        behavior = features["script_behavior"]
        self.assertEqual(2, behavior["standard_kaishu_stroke_count"])
        self.assertEqual(1, behavior["observed_pen_down_stroke_count"])
        self.assertEqual(0.5, behavior["observed_to_standard_stroke_ratio"])
        self.assertEqual(1.0, behavior["joins_standard_strokes"])

    def test_connection_analysis_finds_close_quick_smooth_boundary(self) -> None:
        sample = self.store.build_document(
            self.entries["二"], 1, make_tablet_buffer(), "complete"
        )
        sample["strokes"].append(
            {
                "points": [
                    StrokePoint(
                        0.84, 0.86, 170, pressure=0.3, source="tablet"
                    ).to_dict(),
                    StrokePoint(
                        0.88, 0.90, 190, pressure=0.5, source="tablet"
                    ).to_dict(),
                ]
            }
        )
        sample["stroke_count"] = 2
        sample["point_count"] += 2
        sample["duration_ms"] = 190
        processed = preprocess_sample(
            sample, PreprocessingOptions(resample_spacing=0.05)
        )

        result = analyze_sample_connections(
            processed,
            ConnectionAnalysisOptions(
                maximum_endpoint_distance=0.2,
                maximum_pen_up_pause_ms=50,
                maximum_exit_turn_deg=90.0,
                maximum_entry_turn_deg=90.0,
            ),
        )

        self.assertEqual(1, result["boundary_count"])
        self.assertEqual(1, result["candidate_count"])
        self.assertTrue(result["boundaries"][0]["candidate"])
        self.assertEqual(
            "analysis_only_no_pen_down_path",
            result["boundaries"][0]["safety_status"],
        )

    def test_connection_report_is_deterministic_and_analysis_only(self) -> None:
        processed_dir = self.data_dir / "processed"
        sample = self.store.build_document(
            self.entries["一"], 1, make_tablet_buffer(), "complete"
        )
        processed = preprocess_sample(sample)
        path = processed_dir / "U+4E00" / "v01.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(processed, ensure_ascii=False), encoding="utf-8")

        first = build_connection_candidate_report(processed_dir)
        second = build_connection_candidate_report(processed_dir)

        self.assertEqual(first, second)
        self.assertEqual(1, first["sample_count"])
        self.assertFalse(first["safety"]["generates_pen_down_connections"])

    def test_alignment_review_validator_supports_joined_standard_strokes(self) -> None:
        document = {
            "schema_version": "1.0",
            "type": "running_script_alignment_review",
            "writer_id": "test_user",
            "characters": [
                {
                    "character": "字",
                    "observed_stroke_count": 2,
                    "standard_kaishu_stroke_count": 3,
                    "connection_candidates": [
                        {
                            "from_observed_stroke_order": 1,
                            "to_observed_stroke_order": 2,
                            "review_decision": "reject_ligature",
                        }
                    ],
                    "alignment_groups": [
                        {
                            "observed_stroke_orders": [1],
                            "standard_kaishu_stroke_orders": [1, 2],
                            "relation": "observed_joins_standard",
                        },
                        {
                            "observed_stroke_orders": [2],
                            "standard_kaishu_stroke_orders": [3],
                            "relation": "one_to_one",
                        },
                    ],
                    "review": {"status": "approved"},
                }
            ],
        }

        self.assertEqual(document, validate_alignment_review(document))

    def test_alignment_review_rejects_incomplete_approved_mapping(self) -> None:
        document = {
            "schema_version": "1.0",
            "type": "running_script_alignment_review",
            "writer_id": "test_user",
            "characters": [
                {
                    "character": "字",
                    "observed_stroke_count": 2,
                    "standard_kaishu_stroke_count": 3,
                    "connection_candidates": [],
                    "alignment_groups": [
                        {
                            "observed_stroke_orders": [1],
                            "standard_kaishu_stroke_orders": [1, 2],
                            "relation": "observed_joins_standard",
                        }
                    ],
                    "review": {"status": "approved"},
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "cover all observed strokes"):
            validate_alignment_review(document)

    def test_automatic_alignment_supports_one_observed_to_two_standard(self) -> None:
        observed = [[(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)]]
        standard = [
            [(0.0, 0.0), (0.5, 0.0)],
            [(0.5, 0.0), (1.0, 0.0)],
        ]

        result = align_character_strokes(
            observed,
            standard,
            AutomaticAlignmentOptions(
                merge_gap_penalty=0.0,
                relation_complexity_penalty=0.0,
            ),
        )

        self.assertEqual(1, len(result["alignment_groups"]))
        self.assertEqual(
            "observed_joins_standard",
            result["alignment_groups"][0]["relation"],
        )
        self.assertEqual(
            [1, 2],
            result["alignment_groups"][0]["standard_kaishu_stroke_orders"],
        )

    def test_automatic_alignment_uses_optional_review_only_for_low_confidence(self) -> None:
        result = align_character_strokes(
            [[(0.0, 0.0), (1.0, 0.0)]],
            [[(0.0, 0.0), (1.0, 0.0)]],
        )

        self.assertEqual("high", result["confidence"])
        self.assertFalse(result["requires_optional_review"])
        self.assertTrue(result["unique_order_preserving_path"])

    def test_automatic_alignment_avoids_ambiguous_many_to_many_groups(self) -> None:
        result = align_character_strokes(
            [
                [(0.0, 0.0), (1.0, 0.0)],
                [(0.0, 1.0), (1.0, 1.0)],
            ],
            [
                [(0.0, 0.0), (1.0, 0.0)],
                [(0.0, 1.0), (1.0, 1.0)],
            ],
        )

        self.assertEqual(
            ["one_to_one", "one_to_one"],
            [group["relation"] for group in result["alignment_groups"]],
        )
        self.assertTrue(result["unique_order_preserving_path"])

    def test_personal_font_profile_loader_accepts_review_free_ready_profile(self) -> None:
        path = self.data_dir / "personal_font_profile_v1.json"
        document = {
            "schema_version": "1.0",
            "type": "personal_handwriting_font_profile",
            "writer_id": "test_user",
            "status": "ready",
            "readiness": {
                "character_count": 100,
                "ready_without_manual_review_count": 100,
                "manual_review_required_count": 0,
            },
        }
        path.write_text(json.dumps(document), encoding="utf-8")

        self.assertEqual(document, load_personal_font_profile(path))

    def test_coverage_reports_missing_characters(self) -> None:
        self.store.commit_sample(self.entries["你"], 1, make_buffer())
        report = analyze_coverage("你好", self.store)
        self.assertEqual(["你", "好"], report["required_characters"])
        self.assertEqual(["好"], report["missing_characters"])
        self.assertEqual(0.5, report["coverage"])

    def test_render_text_matches_stroke_interface_and_is_deterministic(self) -> None:
        self.store.commit_sample(self.entries["你"], 1, make_buffer())
        self.store.commit_sample(self.entries["好"], 1, make_buffer(0.1))
        options = RenderOptions(random_seed=42)

        first = render_text("你好", self.store, options)
        second = render_text("你好", self.store, options)
        different_seed = render_text(
            "你好", self.store, RenderOptions(random_seed=43)
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, different_seed)
        self.assertEqual("0.1", first["schema_version"])
        self.assertEqual("stroke_document", first["type"])
        self.assertEqual("handwriting", first["source"])
        self.assertEqual("test_user", first["user_id"])
        self.assertEqual([1, 2], [stroke["order"] for stroke in first["strokes"]])
        self.assertTrue(all(stroke["pen_down"] for stroke in first["strokes"]))

    def test_render_rejects_missing_samples(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing handwriting samples"):
            render_text("你", self.store)

    def test_export_cli_writes_stroke_document(self) -> None:
        self.store.commit_sample(self.entries["你"], 1, make_buffer())
        request_path = self.data_dir / "request.json"
        output_path = self.data_dir / "output.json"
        request_path.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "user_id": self.store.writer_id,
                    "text": "你",
                    "options": {"random_seed": 7},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        exit_code = run_export(
            [
                str(request_path),
                str(output_path),
                "--data-dir",
                str(self.data_dir),
            ]
        )

        self.assertEqual(0, exit_code)
        document = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual("stroke_document", document["type"])
        self.assertEqual(self.store.writer_id, document["user_id"])
        self.assertTrue(document["strokes"])


if __name__ == "__main__":
    unittest.main()
