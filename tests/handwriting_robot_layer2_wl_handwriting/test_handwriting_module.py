from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.handwriting_robot_layer2_wl_handwriting import (
    RecordingBuffer,
    RenderOptions,
    SampleStore,
    StrokePoint,
    PreprocessingOptions,
    StyleAnalysisOptions,
    StyleGenerationOptions,
    analyze_coverage,
    analyze_processed_sample,
    build_style_profile,
    build_hanzi_writer_coverage_report,
    build_hanzi_writer_library,
    convert_hanzi_writer_character,
    extract_style_profile,
    generate_styled_text,
    load_style_probe_charset,
    load_skeleton_library,
    load_target_charset,
    preprocess_sample,
    preprocess_style_probe,
    render_text,
    validate_skeleton_library,
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
