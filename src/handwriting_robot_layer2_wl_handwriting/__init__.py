"""Member 2 personal-handwriting collection and StrokeDocument rendering API."""

from .alignment_review import (
    build_alignment_review_package,
    render_alignment_preview_svg,
    validate_alignment_review,
)
from .automatic_alignment import (
    AutomaticAlignmentOptions,
    align_character_strokes,
    build_automatic_alignment_profile,
)

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
from .personal_font_profile import (
    build_personal_font_profile,
    file_sha256,
    load_personal_font_bundle,
    load_personal_font_profile,
)
from .personal_font_evaluation import (
    PersonalFontEvaluationOptions,
    build_personal_font_evaluation,
)
from .personal_font_deployment import (
    build_personal_font_deployment,
    load_personal_font_deployment,
    load_personal_font_deployment_bundle,
)
from .machine_handoff import (
    MachineHandoffOptions,
    build_machine_handoff_package,
    validate_stroke_document_preflight,
)
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
from .connection_analysis import (
    ConnectionAnalysisOptions,
    analyze_sample_connections,
    build_connection_candidate_report,
)
from .similarity import (
    build_report_diagnosis,
    build_similarity_report,
    compare_character_geometry,
    diagnose_character_result,
)

__all__ = [
    "CharacterEntry",
    "CAPTURE_SCHEMA_VERSION",
    "CaptureSubmission",
    "ConnectionAnalysisOptions",
    "AutomaticAlignmentOptions",
    "RecordingBuffer",
    "PreprocessingOptions",
    "PersonalFontEvaluationOptions",
    "MachineHandoffOptions",
    "RenderOptions",
    "SampleStore",
    "Stroke",
    "StrokePoint",
    "StyleAnalysisOptions",
    "StyleGenerationOptions",
    "analyze_coverage",
    "align_character_strokes",
    "analyze_sample_connections",
    "analyze_processed_sample",
    "analyze_skeleton_coverage",
    "build_style_profile",
    "build_hanzi_writer_coverage_report",
    "build_hanzi_writer_library",
    "build_personal_font_profile",
    "build_personal_font_evaluation",
    "build_personal_font_deployment",
    "build_machine_handoff_package",
    "build_connection_candidate_report",
    "build_alignment_review_package",
    "build_automatic_alignment_profile",
    "build_report_diagnosis",
    "build_similarity_report",
    "buffer_from_capture",
    "default_style_probe_path",
    "default_demo_skeleton_path",
    "find_character",
    "file_sha256",
    "extract_style_profile",
    "convert_hanzi_writer_character",
    "compare_character_geometry",
    "diagnose_character_result",
    "load_target_charset",
    "load_style_probe_charset",
    "load_skeleton_library",
    "load_hanzi_writer_glyph",
    "load_personal_font_profile",
    "load_personal_font_bundle",
    "load_personal_font_deployment",
    "load_personal_font_deployment_bundle",
    "load_style_profile",
    "normalize_input_source",
    "preprocess_sample",
    "preprocess_style_probe",
    "render_text",
    "render_alignment_preview_svg",
    "read_hanzi_writer_metadata",
    "generate_styled_text",
    "skeleton_by_character",
    "validate_skeleton_library",
    "validate_alignment_review",
    "validate_style_profile",
    "validate_stroke_document_preflight",
]
