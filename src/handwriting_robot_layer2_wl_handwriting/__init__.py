"""Member 2 personal-handwriting collection and StrokeDocument rendering API."""

from .charset import (
    CharacterEntry,
    default_style_probe_path,
    find_character,
    load_style_probe_charset,
    load_target_charset,
)
from .capture_protocol import (
    CAPTURE_SCHEMA_VERSION,
    CaptureSubmission,
    buffer_from_capture,
    normalize_input_source,
)
from .models import RecordingBuffer, Stroke, StrokePoint
from .hanzi_writer_adapter import (
    build_hanzi_writer_coverage_report,
    build_hanzi_writer_library,
    convert_hanzi_writer_character,
    load_hanzi_writer_glyph,
    read_hanzi_writer_metadata,
)
from .preprocessing import (
    PreprocessingOptions,
    preprocess_sample,
    preprocess_style_probe,
)
from .renderer import RenderOptions, analyze_coverage, render_text
from .storage import SampleStore
from .style_analysis import (
    StyleAnalysisOptions,
    analyze_processed_sample,
    build_style_profile,
    extract_style_profile,
)
from .skeleton import (
    analyze_skeleton_coverage,
    default_demo_skeleton_path,
    load_skeleton_library,
    skeleton_by_character,
    validate_skeleton_library,
)
from .style_generator import (
    StyleGenerationOptions,
    generate_styled_text,
    load_style_profile,
    validate_style_profile,
)

__all__ = [
    "CharacterEntry",
    "CAPTURE_SCHEMA_VERSION",
    "CaptureSubmission",
    "RecordingBuffer",
    "PreprocessingOptions",
    "RenderOptions",
    "SampleStore",
    "Stroke",
    "StrokePoint",
    "StyleAnalysisOptions",
    "StyleGenerationOptions",
    "analyze_coverage",
    "analyze_processed_sample",
    "analyze_skeleton_coverage",
    "build_style_profile",
    "build_hanzi_writer_coverage_report",
    "build_hanzi_writer_library",
    "buffer_from_capture",
    "default_style_probe_path",
    "default_demo_skeleton_path",
    "find_character",
    "extract_style_profile",
    "convert_hanzi_writer_character",
    "load_target_charset",
    "load_style_probe_charset",
    "load_skeleton_library",
    "load_hanzi_writer_glyph",
    "load_style_profile",
    "normalize_input_source",
    "preprocess_sample",
    "preprocess_style_probe",
    "render_text",
    "read_hanzi_writer_metadata",
    "generate_styled_text",
    "skeleton_by_character",
    "validate_skeleton_library",
    "validate_style_profile",
]
