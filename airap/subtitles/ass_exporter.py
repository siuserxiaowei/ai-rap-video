"""Advanced SubStation Alpha (.ass) and fallback SRT (.srt) subtitle exporter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from airap.config import StyleConfig
from airap.subtitles.kinetic_builder import KineticLine, RhymeStyle


class AspectRatio(str, Enum):
    """Target video canvas aspect ratio."""

    VERTICAL_9_16 = "9:16"
    HORIZONTAL_16_9 = "16:9"

    @classmethod
    def from_str(cls, value: str) -> AspectRatio:
        val = value.strip().lower()
        if val in ("9:16", "vertical", "portrait", "shorts", "tiktok", "reels"):
            return cls.VERTICAL_9_16
        if val in ("16:9", "horizontal", "landscape", "youtube", "cinema"):
            return cls.HORIZONTAL_16_9
        raise ValueError(f"Unsupported aspect ratio: '{value}'. Expected '9:16' or '16:9'.")


@dataclass
class ASSStyle:
    """Definition of an ASS V4+ Style line.

    Format:
    Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,
    Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,
    BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    """

    name: str = "Default"
    fontname: str = "Arial Black"
    fontsize: int = 72
    primary_color: str = "&H00FFFFFF"     # White
    secondary_color: str = "&H00808080"   # Gray (unhighlighted karaoke color)
    outline_color: str = "&H00000000"     # Black outline
    back_color: str = "&H80000000"        # Semi-transparent drop shadow
    bold: int = -1                        # -1 for True in ASS
    italic: int = 0
    underline: int = 0
    strikeout: int = 0
    scale_x: int = 100
    scale_y: int = 100
    spacing: int = 0
    angle: float = 0.0
    border_style: int = 1                 # 1 = outline + drop shadow
    outline: float = 4.0
    shadow: float = 2.0
    alignment: int = 5                    # 5 = middle center, 2 = bottom center
    margin_l: int = 60
    margin_r: int = 60
    margin_v: int = 280
    encoding: int = 1

    def to_ass_line(self) -> str:
        """Render style as an ASS V4+ Style definition line."""
        fields = [
            self.name,
            self.fontname,
            str(self.fontsize),
            self.primary_color,
            self.secondary_color,
            self.outline_color,
            self.back_color,
            str(self.bold),
            str(self.italic),
            str(self.underline),
            str(self.strikeout),
            str(self.scale_x),
            str(self.scale_y),
            str(self.spacing),
            str(int(self.angle) if self.angle.is_integer() else self.angle),
            str(self.border_style),
            str(int(self.outline) if self.outline.is_integer() else self.outline),
            str(int(self.shadow) if self.shadow.is_integer() else self.shadow),
            str(self.alignment),
            str(self.margin_l),
            str(self.margin_r),
            str(self.margin_v),
            str(self.encoding),
        ]
        return f"Style: {','.join(fields)}"


def seconds_to_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp format `H:MM:SS.cc` (centiseconds).

    Examples:
        0.0     -> "0:00:00.00"
        1.25    -> "0:00:01.25"
        65.342  -> "0:01:05.34"
        3661.05 -> "1:01:01.05"
    """
    if seconds < 0:
        seconds = 0.0
    total_cs = round(seconds * 100)
    hours = total_cs // 360000
    mins = (total_cs % 360000) // 6000
    secs = (total_cs % 6000) // 100
    cs = total_cs % 100
    return f"{hours}:{mins:02d}:{secs:02d}.{cs:02d}"


def seconds_to_srt_time(seconds: float) -> str:
    """Format seconds into SubRip timestamp format `HH:MM:SS,mmm` (milliseconds).

    Examples:
        0.0     -> "00:00:00,000"
        1.25    -> "00:00:01,250"
        65.342  -> "00:01:05,342"
        3661.05 -> "01:01:01,050"
    """
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    hours = total_ms // 3600000
    mins = (total_ms % 3600000) // 60000
    secs = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def strip_ass_tags(text: str) -> str:
    """Strip all ASS override tags and formatting commands, returning clean text."""
    # Remove all curly brace blocks: {...}
    cleaned = re.sub(r"\{[^{}]*\}", "", text)
    # Replace line breaks \N, \n, \h with spaces
    cleaned = re.sub(r"\\[Nnh]", " ", cleaned)
    # Collapse multiple whitespace
    return " ".join(cleaned.split()).strip()


def normalize_ass_color(color: str) -> str:
    """Normalize color strings (hex or ASS format) into ASS format `&HAABBGGRR` or `&HBBGGRR&`.

    Supports:
        - ASS format: '&H0000FFFF', '&H00FFFF00', '&H0000FF&'
        - Hex RGB: '#FF0000' -> '&H000000FF' (Red in ASS BGR)
        - Hex RGBA: '#FF000080' -> '&H800000FF'
    """
    clean = color.strip()
    if clean.startswith("&"):
        return clean

    if clean.startswith("#"):
        hex_val = clean.lstrip("#")
        if len(hex_val) == 6:  # RRGGBB
            rr = hex_val[0:2]
            gg = hex_val[2:4]
            bb = hex_val[4:6]
            return f"&H00{bb}{gg}{rr}".upper()
        if len(hex_val) == 8:  # RRGGBBAA
            rr = hex_val[0:2]
            gg = hex_val[2:4]
            bb = hex_val[4:6]
            aa = hex_val[6:8]
            return f"&H{aa}{bb}{gg}{rr}".upper()

    return f"&H{clean}&"


class ASSExporter:
    """Advanced SubStation Alpha (.ass) subtitle exporter with kinetic rap styling.

    Supports dual-aspect ratio presets:
        - 9:16 vertical (Shorts / TikTok / Reels) with centered punchy typography.
        - 16:9 horizontal (YouTube / Cinema) with widescreen bottom margins.
    """

    def __init__(
        self,
        style_config: Optional[StyleConfig] = None,
        aspect_ratio: Union[AspectRatio, str] = AspectRatio.VERTICAL_9_16,
        custom_styles: Optional[List[ASSStyle]] = None,
        rhyme_style: Optional[RhymeStyle] = None,
    ) -> None:
        self.style_config = style_config or StyleConfig()
        self.aspect_ratio = (
            aspect_ratio
            if isinstance(aspect_ratio, AspectRatio)
            else AspectRatio.from_str(aspect_ratio)
        )
        self.custom_styles = custom_styles or []

        # Derive rhyme style from StyleConfig if not explicitly given
        if rhyme_style is not None:
            self.rhyme_style = rhyme_style
        else:
            self.rhyme_style = RhymeStyle(
                color=self.style_config.highlight_color,
                scale_percent=125,
                bold=True,
                reset_after=True,
            )

    def get_styles_for_aspect_ratio(self, aspect_ratio: AspectRatio) -> List[ASSStyle]:
        """Construct the default style suite for a given aspect ratio."""
        if self.custom_styles:
            return list(self.custom_styles)

        font_name = self.style_config.font_name
        primary = normalize_ass_color(self.style_config.primary_color)
        highlight = normalize_ass_color(self.style_config.highlight_color)

        if aspect_ratio == AspectRatio.VERTICAL_9_16:
            # 1080x1920 Vertical (Shorts/TikTok)
            # Default style: Alignment 5 (Middle Center), large punchy text for kinetic pop
            default_style = ASSStyle(
                name="Default",
                fontname=font_name,
                fontsize=72,
                primary_color=primary,
                secondary_color="&H00808080",
                outline_color="&H00000000",
                back_color="&H80000000",
                bold=-1,
                outline=4.5,
                shadow=2.5,
                alignment=5,  # Screen center
                margin_l=60,
                margin_r=60,
                margin_v=280,
            )
            rap_vertical = ASSStyle(
                name="RapVertical",
                fontname=font_name,
                fontsize=76,
                primary_color=primary,
                secondary_color="&H00A0A0A0",
                outline_color="&H00000000",
                back_color="&H80000000",
                bold=-1,
                outline=5.0,
                shadow=3.0,
                alignment=5,
                margin_l=50,
                margin_r=50,
                margin_v=280,
            )
            rap_vertical_bottom = ASSStyle(
                name="RapVerticalBottom",
                fontname=font_name,
                fontsize=68,
                primary_color=primary,
                secondary_color="&H00808080",
                outline_color="&H00000000",
                back_color="&H80000000",
                bold=-1,
                outline=4.0,
                shadow=2.0,
                alignment=2,  # Bottom center
                margin_l=60,
                margin_r=60,
                margin_v=300,
            )
            rhyme_accent = ASSStyle(
                name="RhymeAccent",
                fontname=font_name,
                fontsize=80,
                primary_color=highlight,
                secondary_color="&H00808080",
                outline_color="&H00000000",
                back_color="&H80000000",
                bold=-1,
                scale_x=115,
                scale_y=115,
                outline=5.5,
                shadow=3.0,
                alignment=5,
                margin_l=50,
                margin_r=50,
                margin_v=280,
            )
            return [default_style, rap_vertical, rap_vertical_bottom, rhyme_accent]
        else:
            # 1920x1080 Horizontal (YouTube/Cinema)
            default_style = ASSStyle(
                name="Default",
                fontname=font_name,
                fontsize=52,
                primary_color=primary,
                secondary_color="&H00808080",
                outline_color="&H00000000",
                back_color="&H80000000",
                bold=-1,
                outline=3.5,
                shadow=2.0,
                alignment=2,  # Bottom center
                margin_l=80,
                margin_r=80,
                margin_v=80,
            )
            rap_horizontal = ASSStyle(
                name="RapHorizontal",
                fontname=font_name,
                fontsize=56,
                primary_color=primary,
                secondary_color="&H00A0A0A0",
                outline_color="&H00000000",
                back_color="&H80000000",
                bold=-1,
                outline=4.0,
                shadow=2.5,
                alignment=2,
                margin_l=80,
                margin_r=80,
                margin_v=90,
            )
            rhyme_accent = ASSStyle(
                name="RhymeAccent",
                fontname=font_name,
                fontsize=60,
                primary_color=highlight,
                secondary_color="&H00808080",
                outline_color="&H00000000",
                back_color="&H80000000",
                bold=-1,
                scale_x=110,
                scale_y=110,
                outline=4.5,
                shadow=2.5,
                alignment=2,
                margin_l=80,
                margin_r=80,
                margin_v=90,
            )
            return [default_style, rap_horizontal, rhyme_accent]

    def generate_header(self, aspect_ratio: Optional[AspectRatio] = None) -> str:
        """Generate the [Script Info] and [V4+ Styles] header sections."""
        ar = aspect_ratio or self.aspect_ratio
        if ar == AspectRatio.VERTICAL_9_16:
            play_res_x = 1080
            play_res_y = 1920
        else:
            play_res_x = 1920
            play_res_y = 1080

        styles = self.get_styles_for_aspect_ratio(ar)

        lines = [
            "[Script Info]",
            "; Script generated by AIRap Kinetic Subtitle Engine",
            "Title: AIRap Kinetic Subtitles",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        ]

        for s in styles:
            lines.append(s.to_ass_line())

        lines.append("")
        lines.append("[Events]")
        lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

        return "\n".join(lines)

    def format_dialogue_line(
        self,
        line: KineticLine,
        style_override: Optional[str] = None,
        tag_type: str = "k",
    ) -> str:
        """Format a single KineticLine into an ASS Dialogue event line.

        Example:
            Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,{\\k30}Yo {\\k25}spit {\\c&H000000FF&\\fscx125\\fscy125\\b1\\k35}fire{\\r}
        """
        start_str = seconds_to_ass_time(line.start_time)
        end_str = seconds_to_ass_time(line.end_time)
        style = style_override or line.style or "Default"

        enable_rhyme = self.style_config.enable_rhyme_highlight
        text = line.render_karaoke(
            rhyme_style=self.rhyme_style,
            tag_type=tag_type,
            enable_rhyme_highlight=enable_rhyme,
        )

        return f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{text}"

    def export(
        self,
        lines: Sequence[KineticLine],
        aspect_ratio: Optional[Union[AspectRatio, str]] = None,
        tag_type: str = "k",
    ) -> str:
        """Export all lines into complete ASS file contents as string.

        Args:
            lines: Collection of KineticLine objects.
            aspect_ratio: Optional aspect ratio override ('9:16' or '16:9').
            tag_type: Karaoke tag type ('k', 'K', 'kf', etc.).

        Returns:
            Complete ASS document string.
        """
        ar = (
            AspectRatio.from_str(aspect_ratio)
            if isinstance(aspect_ratio, str)
            else (aspect_ratio or self.aspect_ratio)
        )

        header = self.generate_header(ar)
        dialogue_lines: List[str] = []

        for line in lines:
            dialogue_lines.append(self.format_dialogue_line(line, tag_type=tag_type))

        return f"{header}\n" + "\n".join(dialogue_lines) + "\n"

    def export_to_file(
        self,
        lines: Sequence[KineticLine],
        output_path: Union[str, Path],
        aspect_ratio: Optional[Union[AspectRatio, str]] = None,
        tag_type: str = "k",
    ) -> Path:
        """Export lines and write to an .ass file.

        Args:
            lines: Collection of KineticLine objects.
            output_path: Target file path.
            aspect_ratio: Optional aspect ratio override ('9:16' or '16:9').
            tag_type: Karaoke tag type.

        Returns:
            Path object of the written file.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.export(lines, aspect_ratio=aspect_ratio, tag_type=tag_type)
        path.write_text(content, encoding="utf-8")
        return path


class SRTExporter:
    """Fallback SRT (SubRip .srt) subtitle exporter."""

    @staticmethod
    def format_entry(
        index: int,
        line: KineticLine,
        include_html_tags: bool = False,
    ) -> str:
        """Format a single subtitle entry block in SRT format."""
        start_str = seconds_to_srt_time(line.start_time)
        end_str = seconds_to_srt_time(line.end_time)

        if include_html_tags:
            # Highlight rhymes with HTML bold and red color tags
            rendered_words: List[str] = []
            for w in line.words:
                if w.is_rhyme:
                    rendered_words.append(f'<b><font color="#FF0000">{w.text}</font></b>')
                else:
                    rendered_words.append(w.text)
            text = " ".join(rendered_words)
        else:
            text = line.plain_text

        # Ensure no lingering ASS tags
        clean_text = strip_ass_tags(text) if not include_html_tags else text

        return f"{index}\n{start_str} --> {end_str}\n{clean_text}"

    @classmethod
    def export(
        cls,
        lines: Sequence[KineticLine],
        include_html_tags: bool = False,
    ) -> str:
        """Export collection of KineticLine objects to a standard SRT string."""
        entries: List[str] = []
        for idx, line in enumerate(lines, start=1):
            entries.append(cls.format_entry(idx, line, include_html_tags=include_html_tags))

        return "\n\n".join(entries) + ("\n" if entries else "")

    @classmethod
    def export_to_file(
        cls,
        lines: Sequence[KineticLine],
        output_path: Union[str, Path],
        include_html_tags: bool = False,
    ) -> Path:
        """Write lines to an .srt file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = cls.export(lines, include_html_tags=include_html_tags)
        path.write_text(content, encoding="utf-8")
        return path
