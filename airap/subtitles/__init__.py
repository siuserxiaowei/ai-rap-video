"""Kinetic subtitle generation and ASS/SRT export module for AIRap."""

from airap.subtitles.ass_exporter import (
    AspectRatio,
    ASSExporter,
    ASSStyle,
    SRTExporter,
    normalize_ass_color,
    seconds_to_ass_time,
    seconds_to_srt_time,
    strip_ass_tags,
)
from airap.subtitles.kinetic_builder import (
    KineticLine,
    KineticSubtitleBuilder,
    RhymeStyle,
    WordHighlight,
    format_karaoke_tag,
    format_word_karaoke,
    inject_rhyme_highlight,
)

__all__ = [
    "AspectRatio",
    "ASSExporter",
    "ASSStyle",
    "KineticLine",
    "KineticSubtitleBuilder",
    "RhymeStyle",
    "SRTExporter",
    "WordHighlight",
    "format_karaoke_tag",
    "format_word_karaoke",
    "inject_rhyme_highlight",
    "normalize_ass_color",
    "seconds_to_ass_time",
    "seconds_to_srt_time",
    "strip_ass_tags",
]
