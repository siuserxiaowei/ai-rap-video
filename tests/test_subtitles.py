"""Comprehensive unit tests for AIRap kinetic subtitle engine and exporters."""

import tempfile
from pathlib import Path

import pytest

from airap.config import StyleConfig
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


class TestWordHighlight:
    """Test WordHighlight dataclass and properties."""

    def test_word_highlight_init_and_properties(self):
        word = WordHighlight(start_ms=1000, end_ms=1350, text="Drop", is_rhyme=False)
        assert word.start_ms == 1000
        assert word.end_ms == 1350
        assert word.text == "Drop"
        assert not word.is_rhyme
        assert word.duration_ms == 350
        assert word.duration_cs == 35  # 350 ms = 35 centiseconds
        assert word.start_time == 1.0
        assert word.end_time == 1.35

    def test_word_highlight_centiseconds_rounding(self):
        # 125 ms rounds to 13 cs (or 12-13 depending on round)
        w1 = WordHighlight(start_ms=0, end_ms=125, text="fast")
        assert w1.duration_cs in (12, 13)

        # Very short duration (5 ms) minimum 1 cs
        w2 = WordHighlight(start_ms=0, end_ms=5, text="a")
        assert w2.duration_cs == 1

        # 0 ms duration
        w3 = WordHighlight(start_ms=100, end_ms=100, text="")
        assert w3.duration_cs == 0

    def test_inverted_timestamps_safeguard(self):
        word = WordHighlight(start_ms=2000, end_ms=1500, text="glitch")
        assert word.end_ms == 2000
        assert word.duration_ms == 0

    def test_serialization(self):
        original = WordHighlight(
            start_ms=500,
            end_ms=900,
            text="Rhyme",
            is_rhyme=True,
            custom_color="&H0000FF&",
            custom_scale=130,
        )
        data = original.to_dict()
        assert data["text"] == "Rhyme"
        assert data["is_rhyme"] is True
        assert data["custom_color"] == "&H0000FF&"
        assert data["custom_scale"] == 130

        recreated = WordHighlight.from_dict(data)
        assert recreated.start_ms == original.start_ms
        assert recreated.end_ms == original.end_ms
        assert recreated.text == original.text
        assert recreated.is_rhyme == original.is_rhyme
        assert recreated.custom_color == original.custom_color
        assert recreated.custom_scale == original.custom_scale


class TestKaraokeTagGenerator:
    """Test standard ASS karaoke tag formatting."""

    def test_format_karaoke_tag(self):
        tag = format_karaoke_tag(duration_cs=30, text="Spit")
        assert tag == r"{\k30}Spit"

        tag_empty_text = format_karaoke_tag(duration_cs=15)
        assert tag_empty_text == r"{\k15}"

    def test_format_karaoke_tag_variants(self):
        # Sweeping reveal \K or \kf
        tag_k_upper = format_karaoke_tag(duration_cs=25, text="flow", tag_type="K")
        assert tag_k_upper == r"{\K25}flow"

        tag_kf = format_karaoke_tag(duration_cs=40, text="bars", tag_type="kf")
        assert tag_kf == r"{\kf40}bars"

    def test_format_word_karaoke(self):
        word = WordHighlight(start_ms=1000, end_ms=1450, text="Mic")
        tag = format_word_karaoke(word)
        assert tag == r"{\k45}Mic"


class TestRhymeHighlightInjector:
    """Test injecting visual rhyme accentuation into ASS karaoke tokens."""

    def test_non_rhyme_word_formatting(self):
        word = WordHighlight(start_ms=0, end_ms=300, text="Check", is_rhyme=False)
        rendered = inject_rhyme_highlight(word)
        assert rendered == r"{\k30}Check"
        assert r"\c" not in rendered
        assert r"\fscx" not in rendered

    def test_rhyme_word_with_default_style(self):
        word = WordHighlight(start_ms=0, end_ms=350, text="Fire", is_rhyme=True)
        rendered = inject_rhyme_highlight(word)

        # Must contain karaoke tag
        assert r"\k35" in rendered
        # Must contain color override
        assert r"\c&H000000FF&" in rendered or r"\c" in rendered
        # Must contain font scale
        assert r"\fscx125\fscy125" in rendered
        # Must contain bold
        assert r"\b1" in rendered
        # Must contain text
        assert "Fire" in rendered
        # Must reset after word
        assert rendered.endswith(r"{\r}")

    def test_rhyme_word_with_custom_style(self):
        word = WordHighlight(start_ms=500, end_ms=900, text="Desire", is_rhyme=True)
        style = RhymeStyle(
            color="&H0000FFFF&",  # Yellow in ASS
            scale_percent=140,
            bold=False,
            reset_after=False,
        )
        rendered = inject_rhyme_highlight(word, rhyme_style=style)

        assert r"\c&H0000FFFF&" in rendered
        assert r"\fscx140\fscy140" in rendered
        assert r"\b1" not in rendered
        assert not rendered.endswith(r"{\r}")
        assert r"\k40" in rendered
        assert "Desire" in rendered

    def test_word_level_overrides(self):
        word = WordHighlight(
            start_ms=0,
            end_ms=400,
            text="Gold",
            is_rhyme=True,
            custom_color="&H00D7FF&",
            custom_scale=150,
        )
        rendered = inject_rhyme_highlight(word)
        assert r"\c&H00D7FF&" in rendered
        assert r"\fscx150\fscy150" in rendered

    def test_custom_tag_override(self):
        word = WordHighlight(start_ms=0, end_ms=300, text="Hyped", is_rhyme=True)
        style = RhymeStyle(custom_tag=r"\jitter1\c&HFFFFFF&", reset_after=True)
        rendered = inject_rhyme_highlight(word, rhyme_style=style)
        assert r"\jitter1\c&HFFFFFF&\k30" in rendered
        assert rendered.endswith(r"{\r}")


class TestKineticLine:
    """Test KineticLine operations and rendering."""

    def test_kinetic_line_properties(self):
        words = [
            WordHighlight(start_ms=1000, end_ms=1300, text="Yo", is_rhyme=False),
            WordHighlight(start_ms=1300, end_ms=1600, text="listen", is_rhyme=False),
            WordHighlight(start_ms=1600, end_ms=2000, text="close", is_rhyme=True),
        ]
        line = KineticLine(bar_index=0, start_time=1.0, end_time=2.0, words=words, style="RapVertical")
        assert line.bar_index == 0
        assert line.start_ms == 1000
        assert line.end_ms == 2000
        assert line.duration == 1.0
        assert line.plain_text == "Yo listen close"
        assert line.style == "RapVertical"

    def test_render_karaoke_with_rhymes(self):
        words = [
            WordHighlight(start_ms=0, end_ms=300, text="Spit", is_rhyme=False),
            WordHighlight(start_ms=300, end_ms=700, text="fire", is_rhyme=True),
        ]
        line = KineticLine(bar_index=1, start_time=0.0, end_time=0.7, words=words)
        rendered = line.render_karaoke()

        # Split words by space
        tokens = rendered.split(" ")
        assert len(tokens) == 2
        assert tokens[0] == r"{\k30}Spit"
        assert r"\k40" in tokens[1]
        assert r"\c" in tokens[1]
        assert "fire" in tokens[1]

    def test_render_karaoke_disable_rhyme_highlight(self):
        words = [
            WordHighlight(start_ms=0, end_ms=300, text="Spit", is_rhyme=False),
            WordHighlight(start_ms=300, end_ms=700, text="fire", is_rhyme=True),
        ]
        line = KineticLine(bar_index=1, start_time=0.0, end_time=0.7, words=words)
        rendered = line.render_karaoke(enable_rhyme_highlight=False)
        assert rendered == r"{\k30}Spit {\k40}fire"
        assert r"\c" not in rendered

    def test_serialization(self):
        line = KineticLine(
            bar_index=3,
            start_time=4.5,
            end_time=6.2,
            words=[WordHighlight(start_ms=4500, end_ms=5000, text="Beat", is_rhyme=False)],
            style="RapVerticalBottom",
        )
        d = line.to_dict()
        assert d["bar_index"] == 3
        assert d["start_time"] == 4.5
        assert d["style"] == "RapVerticalBottom"
        assert len(d["words"]) == 1

        recreated = KineticLine.from_dict(d)
        assert recreated.bar_index == line.bar_index
        assert recreated.start_time == line.start_time
        assert recreated.end_time == line.end_time
        assert recreated.words[0].text == "Beat"
        assert recreated.style == line.style


class TestKineticSubtitleBuilder:
    """Test KineticSubtitleBuilder workflow."""

    def test_create_line_auto_derive_timestamps(self):
        builder = KineticSubtitleBuilder()
        words = [
            WordHighlight(start_ms=1000, end_ms=1300, text="Drop"),
            WordHighlight(start_ms=1300, end_ms=1800, text="it"),
        ]
        line = builder.create_line(bar_index=0, words=words)
        assert line.start_time == 1.0
        assert line.end_time == 1.8
        assert len(builder.lines) == 1

    def test_create_line_from_dicts(self):
        builder = KineticSubtitleBuilder()
        word_dicts = [
            {"start_ms": 2000, "end_ms": 2400, "text": "Bass", "is_rhyme": False},
            {"start_ms": 2400, "end_ms": 3000, "text": "heavy", "is_rhyme": True},
        ]
        line = builder.create_line(bar_index=1, words=word_dicts, style="RapVertical")
        assert line.words[0].text == "Bass"
        assert line.words[1].text == "heavy"
        assert line.words[1].is_rhyme is True
        assert line.style == "RapVertical"

    def test_mark_rhymes(self):
        builder = KineticSubtitleBuilder()
        builder.create_line(
            bar_index=0,
            words=[
                WordHighlight(start_ms=0, end_ms=300, text="I'm"),
                WordHighlight(start_ms=300, end_ms=600, text="spitting"),
                WordHighlight(start_ms=600, end_ms=1000, text="fire,"),
            ],
        )
        builder.create_line(
            bar_index=1,
            words=[
                WordHighlight(start_ms=1000, end_ms=1300, text="Taking"),
                WordHighlight(start_ms=1300, end_ms=1600, text="it"),
                WordHighlight(start_ms=1600, end_ms=2000, text="higher!"),
            ],
        )

        builder.mark_rhymes(["fire", "higher"])

        # Word "fire," has punctuation stripped for matching
        line0 = builder.lines[0]
        assert not line0.words[0].is_rhyme
        assert line0.words[2].is_rhyme is True

        line1 = builder.lines[1]
        assert line1.words[2].is_rhyme is True

    def test_chunk_line(self):
        builder = KineticSubtitleBuilder()
        words = [
            WordHighlight(start_ms=0, end_ms=300, text="One"),
            WordHighlight(start_ms=300, end_ms=600, text="two"),
            WordHighlight(start_ms=600, end_ms=900, text="three"),
            WordHighlight(start_ms=900, end_ms=1200, text="four"),
            WordHighlight(start_ms=1200, end_ms=1500, text="five"),
        ]
        long_line = KineticLine(bar_index=0, start_time=0.0, end_time=1.5, words=words)

        chunks = builder.chunk_line(long_line, max_words_per_chunk=2)
        assert len(chunks) == 3

        # Chunk 1: "One two"
        assert chunks[0].plain_text == "One two"
        assert chunks[0].start_time == 0.0
        assert chunks[0].end_time == 0.6

        # Chunk 2: "three four"
        assert chunks[1].plain_text == "three four"
        assert chunks[1].start_time == 0.6
        assert chunks[1].end_time == 1.2

        # Chunk 3: "five"
        assert chunks[2].plain_text == "five"
        assert chunks[2].start_time == 1.2
        assert chunks[2].end_time == 1.5

    def test_build_from_lyrics(self):
        builder = KineticSubtitleBuilder()
        lyrics_data = [
            {
                "bar_index": 0,
                "words": [
                    {"start_ms": 0, "end_ms": 400, "text": "Start", "is_rhyme": False},
                    {"start_ms": 400, "end_ms": 800, "text": "up", "is_rhyme": False},
                ],
            },
            {
                "bar_index": 1,
                "style": "RapVertical",
                "words": [
                    {"start_ms": 1000, "end_ms": 1400, "text": "Lock", "is_rhyme": False},
                    {"start_ms": 1400, "end_ms": 1900, "text": "in", "is_rhyme": True},
                ],
            },
        ]
        lines = builder.build_from_lyrics(lyrics_data)
        assert len(lines) == 2
        assert lines[0].bar_index == 0
        assert lines[1].style == "RapVertical"
        assert lines[1].words[1].is_rhyme is True


class TestASSExporter:
    """Test ASS subtitle export functionality."""

    def test_seconds_to_ass_time(self):
        assert seconds_to_ass_time(0.0) == "0:00:00.00"
        assert seconds_to_ass_time(1.25) == "0:00:01.25"
        assert seconds_to_ass_time(65.342) == "0:01:05.34"
        assert seconds_to_ass_time(3661.05) == "1:01:01.05"
        assert seconds_to_ass_time(-5.0) == "0:00:00.00"

    def test_normalize_ass_color(self):
        # Already ASS format
        assert normalize_ass_color("&H00FFFF00") == "&H00FFFF00"
        # Hex RGB (#RRGGBB) to ASS BGR
        # Pure Red: RR=FF, GG=00, BB=00 -> ASS &H000000FF
        assert normalize_ass_color("#FF0000") == "&H000000FF"
        # Pure Blue: RR=00, GG=00, BB=FF -> ASS &H00FF0000
        assert normalize_ass_color("#0000FF") == "&H00FF0000"
        # Pure Yellow: RR=FF, GG=FF, BB=00 -> ASS &H0000FFFF
        assert normalize_ass_color("#FFFF00") == "&H0000FFFF"

    def test_ass_header_vertical_9_16(self):
        exporter = ASSExporter(aspect_ratio=AspectRatio.VERTICAL_9_16)
        header = exporter.generate_header()

        assert "[Script Info]" in header
        assert "PlayResX: 1080" in header
        assert "PlayResY: 1920" in header
        assert "[V4+ Styles]" in header
        assert "Style: Default," in header
        assert "Style: RapVertical," in header
        assert "Style: RhymeAccent," in header
        assert "[Events]" in header

    def test_ass_header_horizontal_16_9(self):
        exporter = ASSExporter(aspect_ratio=AspectRatio.HORIZONTAL_16_9)
        header = exporter.generate_header()

        assert "PlayResX: 1920" in header
        assert "PlayResY: 1080" in header
        assert "Style: RapHorizontal," in header

    def test_dialogue_formatting(self):
        exporter = ASSExporter(aspect_ratio=AspectRatio.VERTICAL_9_16)
        line = KineticLine(
            bar_index=0,
            start_time=1.25,
            end_time=3.5,
            words=[
                WordHighlight(start_ms=1250, end_ms=1750, text="Mic", is_rhyme=False),
                WordHighlight(start_ms=1750, end_ms=2500, text="check", is_rhyme=True),
            ],
            style="RapVertical",
        )
        dialogue = exporter.format_dialogue_line(line)
        assert dialogue.startswith("Dialogue: 0,0:00:01.25,0:00:03.50,RapVertical,,0,0,0,,")
        assert r"{\k50}Mic" in dialogue
        assert r"\k75" in dialogue
        assert r"\c" in dialogue
        assert "check" in dialogue

    def test_export_complete_ass(self):
        exporter = ASSExporter(aspect_ratio=AspectRatio.VERTICAL_9_16)
        lines = [
            KineticLine(
                bar_index=0,
                start_time=0.5,
                end_time=2.0,
                words=[
                    WordHighlight(start_ms=500, end_ms=1000, text="Spit", is_rhyme=False),
                    WordHighlight(start_ms=1000, end_ms=2000, text="fire", is_rhyme=True),
                ],
            )
        ]
        ass_content = exporter.export(lines)
        assert "[Script Info]" in ass_content
        assert "[V4+ Styles]" in ass_content
        assert "[Events]" in ass_content
        assert "Dialogue: 0,0:00:00.50,0:00:02.00,Default" in ass_content
        assert "Spit" in ass_content
        assert "fire" in ass_content

    def test_export_to_file(self):
        exporter = ASSExporter()
        line = KineticLine(
            bar_index=0,
            start_time=0.0,
            end_time=1.0,
            words=[WordHighlight(start_ms=0, end_ms=1000, text="Test")],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "subtitles.ass"
            returned_path = exporter.export_to_file([line], out_file)
            assert returned_path.is_file()
            content = returned_path.read_text(encoding="utf-8")
            assert "PlayResX: 1080" in content
            assert "Test" in content

    def test_style_config_integration(self):
        cfg = StyleConfig(
            font_name="Montserrat ExtraBold",
            primary_color="#00FFCC",
            highlight_color="#FF0055",
            enable_rhyme_highlight=True,
        )
        exporter = ASSExporter(style_config=cfg, aspect_ratio=AspectRatio.VERTICAL_9_16)
        header = exporter.generate_header()
        assert "Montserrat ExtraBold" in header


class TestSRTExporter:
    """Test SRT fallback subtitle exporter."""

    def test_seconds_to_srt_time(self):
        assert seconds_to_srt_time(0.0) == "00:00:00,000"
        assert seconds_to_srt_time(1.25) == "00:00:01,250"
        assert seconds_to_srt_time(65.342) == "00:01:05,342"
        assert seconds_to_srt_time(3661.05) == "01:01:01,050"

    def test_strip_ass_tags(self):
        raw = r"{\k30}Yo {\c&H0000FF&\fscx125\fscy125\k40}spit{\r} \N {\b1}fire{\b0}"
        cleaned = strip_ass_tags(raw)
        assert cleaned == "Yo spit fire"

    def test_srt_plain_export(self):
        lines = [
            KineticLine(
                bar_index=0,
                start_time=1.0,
                end_time=3.5,
                words=[
                    WordHighlight(start_ms=1000, end_ms=2000, text="First", is_rhyme=False),
                    WordHighlight(start_ms=2000, end_ms=3500, text="bar", is_rhyme=True),
                ],
            ),
            KineticLine(
                bar_index=1,
                start_time=3.6,
                end_time=5.0,
                words=[
                    WordHighlight(start_ms=3600, end_ms=4200, text="Second", is_rhyme=False),
                    WordHighlight(start_ms=4200, end_ms=5000, text="star", is_rhyme=True),
                ],
            ),
        ]
        srt_content = SRTExporter.export(lines)
        expected_blocks = [
            "1\n00:00:01,000 --> 00:00:03,500\nFirst bar",
            "2\n00:00:03,600 --> 00:00:05,000\nSecond star",
        ]
        for block in expected_blocks:
            assert block in srt_content

    def test_srt_html_tags_export(self):
        lines = [
            KineticLine(
                bar_index=0,
                start_time=1.0,
                end_time=2.0,
                words=[
                    WordHighlight(start_ms=1000, end_ms=1500, text="Drop", is_rhyme=False),
                    WordHighlight(start_ms=1500, end_ms=2000, text="heat", is_rhyme=True),
                ],
            )
        ]
        srt_content = SRTExporter.export(lines, include_html_tags=True)
        assert 'Drop <b><font color="#FF0000">heat</font></b>' in srt_content

    def test_srt_export_to_file(self):
        lines = [
            KineticLine(
                bar_index=0,
                start_time=0.0,
                end_time=2.0,
                words=[WordHighlight(start_ms=0, end_ms=2000, text="Sample rap line")],
            )
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.srt"
            returned_path = SRTExporter.export_to_file(lines, out_file)
            assert returned_path.is_file()
            content = returned_path.read_text(encoding="utf-8")
            assert "00:00:00,000 --> 00:00:02,000" in content
            assert "Sample rap line" in content


class TestEdgeCasesAndSpecialCharacters:
    """Test rap slang, contractions, and timing edge cases."""

    def test_rap_slang_and_punctuation(self):
        builder = KineticSubtitleBuilder()
        line = builder.create_line(
            bar_index=0,
            words=[
                WordHighlight(start_ms=0, end_ms=200, text="I'm"),
                WordHighlight(start_ms=200, end_ms=500, text="100%"),
                WordHighlight(start_ms=500, end_ms=900, text="real!"),
            ],
        )
        assert line.plain_text == "I'm 100% real!"
        rendered = line.render_karaoke()
        assert r"{\k20}I'm" in rendered
        assert r"{\k30}100%" in rendered
        assert r"{\k40}real!" in rendered

    def test_empty_line_rendering(self):
        empty_line = KineticLine(bar_index=0, start_time=0.0, end_time=1.0, words=[])
        assert empty_line.plain_text == ""
        assert empty_line.render_karaoke() == ""

        exporter = ASSExporter()
        dialogue = exporter.format_dialogue_line(empty_line)
        assert dialogue.endswith(",,")

        srt = SRTExporter.export([empty_line])
        assert "00:00:00,000 --> 00:00:01,000" in srt
