"""Kinetic subtitle builder and rap typography engine for AIRap."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union


@dataclass
class WordHighlight:
    """Represents a single word with timestamp and rap rhyme metadata.

    Attributes:
        start_ms: Start time in milliseconds.
        end_ms: End time in milliseconds.
        text: The lyric word or token.
        is_rhyme: Whether this word is an end rhyme or internal rhyme.
        custom_color: Optional ASS color override for this specific word (e.g., '&H0000FF&').
        custom_scale: Optional font scale override percentage (e.g., 130).
    """

    start_ms: int
    end_ms: int
    text: str
    is_rhyme: bool = False
    custom_color: Optional[str] = None
    custom_scale: Optional[int] = None

    def __post_init__(self) -> None:
        if self.end_ms < self.start_ms:
            # Safeguard inverted timestamps
            self.end_ms = self.start_ms

    @property
    def duration_ms(self) -> int:
        """Duration in milliseconds."""
        return max(0, self.end_ms - self.start_ms)

    @property
    def duration_cs(self) -> int:
        """Duration in centiseconds (1/100 sec, standard ASS \\k tag unit).

        Guaranteed to be at least 1 centisecond if duration_ms > 0,
        or 1 centisecond fallback so the syllable remains visible on timeline.
        """
        cs = round(self.duration_ms / 10.0)
        return max(1, cs) if self.duration_ms > 0 else 0

    @property
    def start_time(self) -> float:
        """Start time in seconds."""
        return self.start_ms / 1000.0

    @property
    def end_time(self) -> float:
        """End time in seconds."""
        return self.end_ms / 1000.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "is_rhyme": self.is_rhyme,
            "custom_color": self.custom_color,
            "custom_scale": self.custom_scale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WordHighlight:
        """Construct from dictionary."""
        return cls(
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            text=str(data["text"]),
            is_rhyme=bool(data.get("is_rhyme", False)),
            custom_color=data.get("custom_color"),
            custom_scale=data.get("custom_scale"),
        )


@dataclass
class RhymeStyle:
    """Styling parameters for accentuating rhyming words in kinetic rap typography."""

    color: Optional[str] = "&H000000FF"  # Bright Red/Accent in ASS format (&HAABBGGRR / &HBBGGRR&)
    scale_percent: int = 125             # Font scale percentage (125 = 125% zoom pop)
    bold: bool = True                    # Make rhyme bold
    reset_after: bool = True             # Append {\\r} or reset tags after the rhyming word
    custom_tag: Optional[str] = None     # User-specified raw ASS override tag block


def format_karaoke_tag(duration_cs: int, text: str = "", tag_type: str = "k") -> str:
    """Generate a standard ASS karaoke tag.

    Format: `{\\k<centiseconds>}word` (or `{\\K<centiseconds>}word` / `{\\kf<centiseconds>}word`)

    Args:
        duration_cs: Duration in centiseconds (1/100th second).
        text: Optional word text following the tag.
        tag_type: Karaoke tag type: 'k' (instant reveal), 'K' or 'kf' (sweeping reveal),
                  'ko' (outline highlight).

    Returns:
        Formatted karaoke string, e.g. `{\\k35}spit`.
    """
    return f"{{\\{tag_type}{duration_cs}}}{text}"


def format_word_karaoke(word: WordHighlight, tag_type: str = "k") -> str:
    """Format a single WordHighlight into a standard karaoke tag without rhyme accents."""
    return format_karaoke_tag(word.duration_cs, word.text, tag_type=tag_type)


def inject_rhyme_highlight(
    word: WordHighlight,
    rhyme_style: Optional[RhymeStyle] = None,
    tag_type: str = "k",
) -> str:
    """Inject kinetic rhyme accentuation tags into a WordHighlight.

    If word.is_rhyme is True, applies custom color, scale, and bold tags alongside
    the karaoke timing tag. If not a rhyme, outputs standard karaoke tag.

    Args:
        word: WordHighlight instance.
        rhyme_style: Optional RhymeStyle configuration. Defaults to bright red + 125% scale.
        tag_type: Karaoke tag type (default 'k').

    Returns:
        Formatted ASS string with embedded override tags.
        Example rhyme: `{\\c&H000000FF&\\fscx125\\fscy125\\b1\\k35}fire{\\r}`
        Example non-rhyme: `{\\k25}spit`
    """
    if not word.is_rhyme:
        return format_word_karaoke(word, tag_type=tag_type)

    style = rhyme_style or RhymeStyle()

    # If word has custom overrides, prioritize them
    color = word.custom_color or style.color
    scale = word.custom_scale or style.scale_percent

    if style.custom_tag:
        # Prepend or combine custom tag
        return f"{{{style.custom_tag}\\{tag_type}{word.duration_cs}}}{word.text}" + (
            "{\\r}" if style.reset_after else ""
        )

    tag_parts: List[str] = []
    if color:
        # ASS primary fill color tag \c or \1c
        clean_color = color if color.startswith("&") else f"&H{color.lstrip('#')}&"
        tag_parts.append(f"\\c{clean_color}")

    if scale and scale != 100:
        tag_parts.append(f"\\fscx{scale}\\fscy{scale}")

    if style.bold:
        tag_parts.append("\\b1")

    # Add the karaoke timing tag
    tag_parts.append(f"\\{tag_type}{word.duration_cs}")

    tag_block = f"{{{ ''.join(tag_parts) }}}"
    reset_block = "{\\r}" if style.reset_after else ""

    return f"{tag_block}{word.text}{reset_block}"


@dataclass
class KineticLine:
    """A single musical line or phrase in the rap performance.

    Attributes:
        bar_index: Index of musical bar (0, 1, 2, ...).
        start_time: Start time in seconds.
        end_time: End time in seconds.
        words: List of WordHighlight objects.
        style: Style name referenced in the ASS header (default 'Default').
    """

    bar_index: int
    start_time: float
    end_time: float
    words: List[WordHighlight] = field(default_factory=list)
    style: str = "Default"

    @property
    def start_ms(self) -> int:
        """Start time in milliseconds."""
        return round(self.start_time * 1000.0)

    @property
    def end_ms(self) -> int:
        """End time in milliseconds."""
        return round(self.end_time * 1000.0)

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return max(0.0, self.end_time - self.start_time)

    @property
    def plain_text(self) -> str:
        """Extract clean plain text with space-separated words."""
        return " ".join(w.text for w in self.words if w.text)

    def render_karaoke(
        self,
        rhyme_style: Optional[RhymeStyle] = None,
        tag_type: str = "k",
        enable_rhyme_highlight: bool = True,
    ) -> str:
        """Render line into ASS karaoke formatted string.

        Args:
            rhyme_style: Custom rhyme accent styling.
            tag_type: ASS karaoke tag ('k', 'K', 'kf', etc.).
            enable_rhyme_highlight: Whether to inject rhyme accent tags.

        Returns:
            Space-delimited karaoke string with timing and rhyme tags.
        """
        rendered_words: List[str] = []
        for word in self.words:
            if enable_rhyme_highlight and word.is_rhyme:
                rendered_words.append(
                    inject_rhyme_highlight(word, rhyme_style=rhyme_style, tag_type=tag_type)
                )
            else:
                rendered_words.append(format_word_karaoke(word, tag_type=tag_type))

        return " ".join(rendered_words)

    def to_dict(self) -> Dict[str, Any]:
        """Convert line to dictionary representation."""
        return {
            "bar_index": self.bar_index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "words": [w.to_dict() for w in self.words],
            "style": self.style,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KineticLine:
        """Construct KineticLine from dictionary."""
        return cls(
            bar_index=int(data["bar_index"]),
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            words=[WordHighlight.from_dict(w) for w in data.get("words", [])],
            style=str(data.get("style", "Default")),
        )


class KineticSubtitleBuilder:
    """Builder for constructing kinetic rap typography lines with syllable timings and rhymes."""

    def __init__(self, default_style: str = "Default") -> None:
        self.default_style = default_style
        self._lines: List[KineticLine] = []

    @property
    def lines(self) -> List[KineticLine]:
        """Retrieve all registered lines."""
        return list(self._lines)

    def add_line(self, line: KineticLine) -> KineticSubtitleBuilder:
        """Append a pre-built KineticLine."""
        self._lines.append(line)
        return self

    def create_line(
        self,
        bar_index: int,
        words: Sequence[Union[WordHighlight, Dict[str, Any]]],
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        style: Optional[str] = None,
    ) -> KineticLine:
        """Create and add a new KineticLine, auto-deriving timestamps if omitted.

        Args:
            bar_index: Rap bar index.
            words: List of WordHighlight instances or word dicts.
            start_time: Optional line start time in seconds (auto-derived from first word if None).
            end_time: Optional line end time in seconds (auto-derived from last word if None).
            style: ASS style name (defaults to self.default_style).

        Returns:
            The created KineticLine instance.
        """
        parsed_words: List[WordHighlight] = []
        for w in words:
            if isinstance(w, WordHighlight):
                parsed_words.append(w)
            elif isinstance(w, dict):
                parsed_words.append(WordHighlight.from_dict(w))
            else:
                raise TypeError(f"Unsupported word type: {type(w)}")

        if start_time is None:
            start_time = parsed_words[0].start_time if parsed_words else 0.0

        if end_time is None:
            end_time = parsed_words[-1].end_time if parsed_words else start_time + 1.0

        line = KineticLine(
            bar_index=bar_index,
            start_time=start_time,
            end_time=end_time,
            words=parsed_words,
            style=style or self.default_style,
        )
        self._lines.append(line)
        return line

    def mark_rhymes(
        self,
        rhyme_words: Iterable[str],
        case_sensitive: bool = False,
    ) -> KineticSubtitleBuilder:
        """Scan all words in registered lines and mark matches as rhymes.

        Args:
            rhyme_words: Set or list of rhyming words (e.g. ['fire', 'wire', 'desire']).
            case_sensitive: Whether match should be case sensitive.

        Returns:
            Self for chaining.
        """
        targets = set(rhyme_words if case_sensitive else [w.lower() for w in rhyme_words])

        for line in self._lines:
            for word in line.words:
                cleaned = re.sub(r"[^\w]", "", word.text)
                cmp_text = cleaned if case_sensitive else cleaned.lower()
                if cmp_text in targets:
                    word.is_rhyme = True

        return self

    def chunk_line(
        self,
        line: KineticLine,
        max_words_per_chunk: int = 3,
    ) -> List[KineticLine]:
        """Split a long rap bar into kinetic micro-chunks (2-3 words per pop).

        This produces the signature modern TikTok/Shorts punchy kinetic rap subtitle effect,
        displaying 2-3 words at a time locked to the beat.

        Args:
            line: The source KineticLine.
            max_words_per_chunk: Maximum words to display concurrently.

        Returns:
            List of smaller chunked KineticLine instances.
        """
        if not line.words:
            return [line]

        chunks: List[KineticLine] = []
        total_words = len(line.words)

        for i in range(0, total_words, max_words_per_chunk):
            slice_words = line.words[i : i + max_words_per_chunk]
            chunk_start = slice_words[0].start_time
            chunk_end = slice_words[-1].end_time
            chunks.append(
                KineticLine(
                    bar_index=line.bar_index,
                    start_time=chunk_start,
                    end_time=chunk_end,
                    words=slice_words,
                    style=line.style,
                )
            )

        return chunks

    def build_from_lyrics(
        self,
        lyrics_data: Sequence[Dict[str, Any]],
    ) -> List[KineticLine]:
        """Build KineticLines from structured lyrics or ASR transcript data.

        Expected format per item:
            {
                "bar_index": 0,
                "start_time": 1.0,    # Optional, derived if missing
                "end_time": 3.5,      # Optional, derived if missing
                "style": "RapVertical", # Optional
                "words": [
                    {"text": "Spit", "start_ms": 1000, "end_ms": 1350, "is_rhyme": False},
                    {"text": "fire", "start_ms": 1350, "end_ms": 1800, "is_rhyme": True}
                ]
            }

        Returns:
            List of created KineticLines.
        """
        created: List[KineticLine] = []
        for item in lyrics_data:
            bar_idx = int(item.get("bar_index", len(created)))
            raw_words = item.get("words", [])
            st = float(item["start_time"]) if "start_time" in item else None
            et = float(item["end_time"]) if "end_time" in item else None
            style = item.get("style", self.default_style)
            line = self.create_line(
                bar_index=bar_idx,
                words=raw_words,
                start_time=st,
                end_time=et,
                style=style,
            )
            created.append(line)
        return created

    def clear(self) -> None:
        """Clear all registered lines."""
        self._lines.clear()
