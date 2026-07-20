"""Member 2 personal-handwriting collection and StrokeDocument rendering API."""

from .charset import CharacterEntry, find_character, load_target_charset
from .capture_protocol import (
    CAPTURE_SCHEMA_VERSION,
    CaptureSubmission,
    buffer_from_capture,
    normalize_input_source,
)
from .models import RecordingBuffer, Stroke, StrokePoint
from .renderer import RenderOptions, analyze_coverage, render_text
from .storage import SampleStore

__all__ = [
    "CharacterEntry",
    "CAPTURE_SCHEMA_VERSION",
    "CaptureSubmission",
    "RecordingBuffer",
    "RenderOptions",
    "SampleStore",
    "Stroke",
    "StrokePoint",
    "analyze_coverage",
    "buffer_from_capture",
    "find_character",
    "load_target_charset",
    "normalize_input_source",
    "render_text",
]
