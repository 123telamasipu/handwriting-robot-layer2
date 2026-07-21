from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .charset import CharacterEntry
from .models import RecordingBuffer


SAMPLE_SCHEMA_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def safe_identifier(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("writer_id cannot be empty")
    safe = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    if not safe:
        raise ValueError("writer_id does not contain usable filename characters")
    return safe[:80]


def atomic_write_json(path: Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def read_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


class SampleStore:
    """Persists private handwriting samples outside tracked source files."""

    def __init__(self, root: Path, writer_id: str, writer_name: str = "") -> None:
        self.root = Path(root)
        self.writer_id = safe_identifier(writer_id)
        self.writer_name = writer_name.strip() or writer_id.strip()
        self.writer_dir = self.root / "writers" / self.writer_id
        self.writer_dir.mkdir(parents=True, exist_ok=True)
        self._save_profile()

    @property
    def manifest_path(self) -> Path:
        return self.writer_dir / "manifest.json"

    def session_path(self, session_id: str) -> Path:
        return self.writer_dir / "sessions" / f"{safe_identifier(session_id)}.json"

    def save_session(
        self, session_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        path = self.session_path(session_id)
        previous = read_json(path, {})
        atomic_write_json(
            path,
            {
                "schema_version": SAMPLE_SCHEMA_VERSION,
                "session_id": safe_identifier(session_id),
                "writer_id": self.writer_id,
                "started_at": previous.get("started_at", utc_now()),
                "updated_at": utc_now(),
                "metadata": metadata or {},
            },
        )
        return path

    def _save_profile(self) -> None:
        path = self.writer_dir / "profile.json"
        previous = read_json(path, {})
        atomic_write_json(
            path,
            {
                "schema_version": SAMPLE_SCHEMA_VERSION,
                "writer_id": self.writer_id,
                "writer_name": self.writer_name,
                "created_at": previous.get("created_at", utc_now()),
                "updated_at": utc_now(),
            },
        )

    def _manifest(self) -> Dict[str, Any]:
        return read_json(
            self.manifest_path,
            {
                "schema_version": SAMPLE_SCHEMA_VERSION,
                "writer_id": self.writer_id,
                "updated_at": utc_now(),
                "samples": {},
            },
        )

    def draft_path(self, entry: CharacterEntry, variant: int) -> Path:
        return self.writer_dir / "drafts" / f"{entry.unicode}_v{variant:02d}.json"

    def sample_path(self, entry: CharacterEntry, variant: int) -> Path:
        return self.writer_dir / "samples" / entry.unicode / f"v{variant:02d}.json"

    def build_document(
        self,
        entry: CharacterEntry,
        variant: int,
        buffer: RecordingBuffer,
        status: str,
        capture_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        document = {
            "schema_version": SAMPLE_SCHEMA_VERSION,
            "status": status,
            "writer": {"id": self.writer_id, "name": self.writer_name},
            "character": {
                "value": entry.character,
                "unicode": entry.unicode,
                "order": entry.order,
                "category": entry.category,
                "frequency_rank": entry.frequency_rank,
                "pinyin": entry.pinyin,
                "expected_stroke_count": entry.stroke_count,
            },
            "variant": int(variant),
            "coordinate_system": {
                "type": "normalized",
                "x_range": [0.0, 1.0],
                "y_range": [0.0, 1.0],
                "origin": "top-left",
            },
            "captured_at": utc_now(),
            "duration_ms": buffer.duration_ms,
            "stroke_count": len(buffer.strokes),
            "point_count": buffer.point_count,
            "bounding_box": buffer.bounding_box(),
            "input_sources": buffer.sources(),
            "strokes": [stroke.to_dict() for stroke in buffer.strokes],
        }
        if capture_context:
            document["capture_context"] = capture_context
        return document

    def save_draft(
        self,
        entry: CharacterEntry,
        variant: int,
        buffer: RecordingBuffer,
        capture_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        path = self.draft_path(entry, variant)
        if not buffer.strokes:
            self.delete_draft(entry, variant)
            return None
        atomic_write_json(
            path,
            self.build_document(
                entry, variant, buffer, "draft", capture_context=capture_context
            ),
        )
        return path

    def commit_sample(
        self,
        entry: CharacterEntry,
        variant: int,
        buffer: RecordingBuffer,
        capture_context: Optional[Dict[str, Any]] = None,
        required_source: Optional[str] = None,
    ) -> Path:
        if buffer.active:
            raise ValueError("finish the current stroke before saving the sample")
        if not buffer.strokes or buffer.point_count < 2:
            raise ValueError("current sample does not contain a complete stroke")
        if required_source and required_source not in buffer.sources():
            raise ValueError(
                f"current sample does not contain required source: {required_source}"
            )

        document = self.build_document(
            entry, variant, buffer, "complete", capture_context=capture_context
        )
        path = self.sample_path(entry, variant)
        atomic_write_json(path, document)

        manifest = self._manifest()
        samples = manifest.setdefault("samples", {})
        character = samples.setdefault(
            entry.unicode,
            {"character": entry.character, "order": entry.order, "variants": {}},
        )
        character["character"] = entry.character
        character["order"] = entry.order
        character.setdefault("variants", {})[str(variant)] = {
            "path": str(path.relative_to(self.writer_dir)).replace("\\", "/"),
            "saved_at": document["captured_at"],
            "stroke_count": document["stroke_count"],
            "point_count": document["point_count"],
            "input_sources": document["input_sources"],
        }
        manifest["updated_at"] = utc_now()
        atomic_write_json(self.manifest_path, manifest)
        self.delete_draft(entry, variant)
        return path

    def delete_draft(self, entry: CharacterEntry, variant: int) -> None:
        path = self.draft_path(entry, variant)
        if path.exists():
            path.unlink()

    def load_working_document(
        self, entry: CharacterEntry, variant: int
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        draft = self.draft_path(entry, variant)
        if draft.exists():
            return read_json(draft), "draft"
        sample = self.sample_path(entry, variant)
        if sample.exists():
            return read_json(sample), "complete"
        return None, "missing"

    def available_variants(self, character: str) -> List[Dict[str, Any]]:
        unicode_value = f"U+{ord(character):04X}"
        item = self._manifest().get("samples", {}).get(unicode_value, {})
        variants = []
        for variant, metadata in item.get("variants", {}).items():
            path = self.writer_dir / metadata["path"]
            if path.exists():
                variants.append(read_json(path))
        return variants

    def is_complete(self, entry: CharacterEntry) -> bool:
        item = self._manifest().get("samples", {}).get(entry.unicode, {})
        return bool(item.get("variants"))

    def completed_count(self) -> int:
        return sum(
            bool(item.get("variants"))
            for item in self._manifest().get("samples", {}).values()
        )

    def completed_characters(self) -> List[str]:
        return [
            item.get("character", "")
            for item in self._manifest().get("samples", {}).values()
            if item.get("variants") and item.get("character")
        ]

    def next_incomplete_index(self, entries: list[CharacterEntry], start: int) -> int:
        if not entries:
            return -1
        completed = {
            unicode_value
            for unicode_value, item in self._manifest().get("samples", {}).items()
            if item.get("variants")
        }
        for offset in range(1, len(entries) + 1):
            index = (start + offset) % len(entries)
            if entries[index].unicode not in completed:
                return index
        return start
