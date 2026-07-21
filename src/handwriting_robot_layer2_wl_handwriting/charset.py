from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class CharacterEntry:
    order: int
    character: str
    unicode: str
    category: str
    tier: str
    frequency_rank: str = ""
    pinyin: str = ""
    stroke_count: str = ""
    source: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "CharacterEntry":
        character = row.get("character", "")
        if len(character) != 1:
            raise ValueError(f"character must contain one Unicode code point: {character!r}")
        return cls(
            order=int(row["order"]),
            character=character,
            unicode=row.get("unicode") or f"U+{ord(character):04X}",
            category=row.get("category", ""),
            tier=row.get("tier", ""),
            frequency_rank=row.get("frequency_rank", ""),
            pinyin=row.get("pinyin", ""),
            stroke_count=row.get("stroke_count", ""),
            source=row.get("source", ""),
        )


def default_charset_path() -> Path:
    return Path(resources.files(__package__).joinpath("resources/target_charset_phase1.csv"))


def default_style_probe_path() -> Path:
    return Path(
        resources.files(__package__).joinpath("resources/style_probe_charset.json")
    )


def load_target_charset(path: Optional[Path] = None) -> List[CharacterEntry]:
    charset_path = Path(path) if path else default_charset_path()
    if not charset_path.exists():
        raise FileNotFoundError(f"target charset not found: {charset_path}")

    with charset_path.open("r", encoding="utf-8-sig", newline="") as file:
        entries = [CharacterEntry.from_row(row) for row in csv.DictReader(file)]

    if not entries:
        raise ValueError(f"target charset is empty: {charset_path}")

    characters = [entry.character for entry in entries]
    if len(characters) != len(set(characters)):
        raise ValueError("target charset contains duplicate Unicode characters")
    return sorted(entries, key=lambda entry: entry.order)


def find_character(entries: Iterable[CharacterEntry], character: str) -> int:
    for index, entry in enumerate(entries):
        if entry.character == character:
            return index
    return -1


def load_style_probe_charset(
    path: Optional[Path] = None,
    target_entries: Optional[Iterable[CharacterEntry]] = None,
) -> List[CharacterEntry]:
    probe_path = Path(path) if path else default_style_probe_path()
    document = json.loads(probe_path.read_text(encoding="utf-8"))
    groups = document.get("groups", [])
    if not isinstance(groups, list) or not groups:
        raise ValueError(f"style probe groups are missing: {probe_path}")

    characters: List[str] = []
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("each style probe group must be a JSON object")
        characters.extend(list(group.get("characters", "")))

    if len(characters) != 100:
        raise ValueError("style probe charset must contain exactly 100 characters")
    if len(characters) != len(set(characters)):
        raise ValueError("style probe charset contains duplicate characters")

    entries = list(target_entries) if target_entries is not None else load_target_charset()
    entry_by_character = {entry.character: entry for entry in entries}
    missing = [character for character in characters if character not in entry_by_character]
    if missing:
        raise ValueError(f"style probe characters are missing from target charset: {''.join(missing)}")
    return [entry_by_character[character] for character in characters]
