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
    analyze_coverage,
    load_target_charset,
    render_text,
)
from src.handwriting_robot_layer2_wl_handwriting.export_cli import run as run_export


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


class CharsetTests(unittest.TestCase):
    def test_bundled_charset_is_unique(self) -> None:
        entries = load_target_charset()
        self.assertEqual(1140, len(entries))
        self.assertEqual(1140, len({entry.character for entry in entries}))
        self.assertEqual(
            1000, sum(entry.category == "hanzi_frequency" for entry in entries)
        )
        self.assertEqual("的", entries[0].character)


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
