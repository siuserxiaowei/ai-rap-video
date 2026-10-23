"""Bar scheduler and word-level timing engine for rap lyrics.

Features:
- Splits raw lyrics into structured 16-bar verses (ignoring headers like [Verse 1]).
- Computes exact start_time, end_time, beats for each bar based on BPM and time signature.
- Estimates word-level time intervals within bars based on syllable weights and breath rest pockets.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from airap.lyrics.flow_analyzer import (
    FlowAnalyzer,
    FlowCadence,
    RhymeSchemeResult,
    count_syllables,
    count_syllables_english,
    is_chinese_char,
    tokenize_lyrics,
)


@dataclass
class WordTiming:
    """Word-level timing information within a bar."""
    text: str
    syllable_count: int
    start_time: float
    end_time: float
    start_beat: float
    end_beat: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def beat_duration(self) -> float:
        return max(0.0, self.end_beat - self.start_beat)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "syllable_count": self.syllable_count,
            "start_time": round(self.start_time, 4),
            "end_time": round(self.end_time, 4),
            "start_beat": round(self.start_beat, 4),
            "end_beat": round(self.end_beat, 4),
            "duration": round(self.duration, 4),
            "beat_duration": round(self.beat_duration, 4),
        }


@dataclass
class Bar:
    """Structured bar representing one measure in the rap track."""
    index: int  # 1-indexed (e.g. 1 to 16)
    text: str
    syllable_count: int
    start_time: float
    end_time: float
    start_beat: float
    end_beat: float
    words: List[WordTiming] = field(default_factory=list)
    cadence_type: str = "boom_bap"
    rhyme_tag: str = ""
    section: str = "verse"

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def beats(self) -> float:
        return max(0.0, self.end_beat - self.start_beat)

    def get_word_at_time(self, timestamp: float) -> Optional[WordTiming]:
        """Find the active word at a given timestamp."""
        for w in self.words:
            if w.start_time <= timestamp <= w.end_time:
                return w
        return None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "syllable_count": self.syllable_count,
            "start_time": round(self.start_time, 4),
            "end_time": round(self.end_time, 4),
            "start_beat": round(self.start_beat, 4),
            "end_beat": round(self.end_beat, 4),
            "duration": round(self.duration, 4),
            "beats": round(self.beats, 4),
            "cadence_type": self.cadence_type,
            "rhyme_tag": self.rhyme_tag,
            "section": self.section,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class VerseSchedule:
    """Complete scheduled verse containing bars, flow cadence, and timing."""
    bars: List[Bar]
    bpm: float
    time_signature: Tuple[int, int]
    total_duration: float
    total_beats: float
    total_syllables: int
    rhyme_scheme: str
    dominant_cadence: str
    section: str = "verse"

    def get_bar_at_time(self, timestamp: float) -> Optional[Bar]:
        """Find the bar active at a given timestamp in seconds."""
        for bar in self.bars:
            if bar.start_time <= timestamp < bar.end_time:
                return bar
        return None

    def get_word_at_time(self, timestamp: float) -> Optional[WordTiming]:
        """Find the word active at a given timestamp in seconds."""
        bar = self.get_bar_at_time(timestamp)
        if bar:
            return bar.get_word_at_time(timestamp)
        return None

    def to_dict(self) -> dict:
        return {
            "section": self.section,
            "bpm": self.bpm,
            "time_signature": list(self.time_signature),
            "total_duration": round(self.total_duration, 4),
            "total_beats": round(self.total_beats, 4),
            "total_syllables": self.total_syllables,
            "rhyme_scheme": self.rhyme_scheme,
            "dominant_cadence": self.dominant_cadence,
            "bar_count": len(self.bars),
            "bars": [b.to_dict() for b in self.bars],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ============================================================================
# Splitting Raw Lyrics
# ============================================================================

SECTION_HEADER_REGEX = re.compile(
    r"^\s*(\[|\()?(verse|chorus|hook|bridge|intro|outro|drop|pre-chorus|break)\b[^\n\]\)]*(\]|\))?\s*$",
    re.IGNORECASE,
)


def split_into_bars(
    raw_lyrics: Union[str, List[str]],
    target_bars: Optional[int] = 16,
    pad_to_target: bool = False,
) -> List[str]:
    """Parse raw rap lyrics into clean bar lines.

    - Strips section headers like '[Verse 1]', '[Chorus]'
    - Trims whitespace and ignores blank lines
    - If pad_to_target is True and lines < target_bars, pads with repeated bars
    - If target_bars is provided, limits or preserves bars accordingly
    """
    if isinstance(raw_lyrics, list):
        lines = raw_lyrics
    else:
        lines = raw_lyrics.splitlines()

    cleaned_bars: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Check if line is a section header like [Verse 1]
        if SECTION_HEADER_REGEX.match(stripped):
            continue
        # Split compound multi-bar lines separated by '//' or ' / '
        if " // " in stripped:
            subparts = [p.strip() for p in stripped.split("//") if p.strip()]
            cleaned_bars.extend(subparts)
        else:
            cleaned_bars.append(stripped)

    if pad_to_target and target_bars and len(cleaned_bars) < target_bars and cleaned_bars:
        # Loop existing bars to reach target_bars
        original = list(cleaned_bars)
        while len(cleaned_bars) < target_bars:
            cleaned_bars.append(original[(len(cleaned_bars)) % len(original)])

    if target_bars is not None and not pad_to_target and len(cleaned_bars) > target_bars:
        return cleaned_bars[:target_bars]

    return cleaned_bars


# ============================================================================
# BarScheduler Engine
# ============================================================================

class BarScheduler:
    """Computes exact musical beat grids, bar boundaries, and word-level timings."""

    def __init__(
        self,
        bpm: float = 130.0,
        time_signature: Tuple[int, int] = (4, 4),
        start_offset: float = 0.0,
        rest_ratio: float = 0.12,  # Natural breath pause at bar end (12% of bar)
    ):
        self.bpm = max(1.0, float(bpm))
        self.time_signature = time_signature
        self.start_offset = max(0.0, float(start_offset))
        # Ensure rest ratio is between 0.0 and 0.4
        self.rest_ratio = min(max(0.0, float(rest_ratio)), 0.40)
        self.flow_analyzer = FlowAnalyzer(default_bpm=self.bpm)

    @property
    def beats_per_bar(self) -> float:
        """Number of beats in one bar (time_signature numerator)."""
        return float(self.time_signature[0])

    @property
    def seconds_per_beat(self) -> float:
        """Duration of a single beat in seconds."""
        return 60.0 / self.bpm

    @property
    def bar_duration(self) -> float:
        """Exact duration of a single bar in seconds."""
        return self.beats_per_bar * self.seconds_per_beat

    def estimate_word_timings(
        self,
        bar_text: str,
        bar_start_time: float,
        bar_start_beat: float,
    ) -> List[WordTiming]:
        """Estimate word-level time intervals within a bar based on syllable weights."""
        tokens = tokenize_lyrics(bar_text)
        if not tokens:
            return []

        # Calculate syllable count per token
        word_syllables: List[Tuple[str, int]] = []
        for tok in tokens:
            if is_chinese_char(tok):
                s_count = 1
            else:
                s_count = max(1, count_syllables_english(tok))
            word_syllables.append((tok, s_count))

        total_syllables = sum(s for _, s in word_syllables)
        if total_syllables == 0:
            return []

        active_bar_duration = self.bar_duration * (1.0 - self.rest_ratio)
        word_timings: List[WordTiming] = []
        current_time = bar_start_time

        for tok, s_count in word_syllables:
            fraction = s_count / total_syllables
            w_duration = fraction * active_bar_duration
            w_start = current_time
            w_end = current_time + w_duration

            # Calculate corresponding musical beats
            w_start_beat = bar_start_beat + ((w_start - bar_start_time) / self.seconds_per_beat)
            w_end_beat = bar_start_beat + ((w_end - bar_start_time) / self.seconds_per_beat)

            word_timings.append(
                WordTiming(
                    text=tok,
                    syllable_count=s_count,
                    start_time=w_start,
                    end_time=w_end,
                    start_beat=w_start_beat,
                    end_beat=w_end_beat,
                )
            )
            current_time = w_end

        return word_timings

    def schedule(
        self,
        lyrics: Union[str, List[str]],
        target_bars: Optional[int] = 16,
        section: str = "verse",
        pad_to_target: bool = False,
    ) -> List[Bar]:
        """Schedule raw lyrics into structured Bar objects with exact times and word timings."""
        raw_bars = split_into_bars(lyrics, target_bars=target_bars, pad_to_target=pad_to_target)
        if not raw_bars:
            return []

        # Analyze rhyme scheme and cadence for the verse
        flow_analysis = self.flow_analyzer.analyze_verse(raw_bars, bpm=self.bpm)
        rhyme_scheme = flow_analysis.rhyme_scheme

        bars: List[Bar] = []
        for i, bar_text in enumerate(raw_bars):
            bar_start_beat = (i * self.beats_per_bar)
            bar_end_beat = ((i + 1) * self.beats_per_bar)
            bar_start_time = self.start_offset + (i * self.bar_duration)
            bar_end_time = self.start_offset + ((i + 1) * self.bar_duration)

            s_count = count_syllables(bar_text)
            cadence = flow_analysis.bar_cadences[i]
            rhyme_tag = (
                rhyme_scheme.end_rhymes[i]["tag"]
                if i < len(rhyme_scheme.end_rhymes)
                else ""
            )

            word_timings = self.estimate_word_timings(
                bar_text=bar_text,
                bar_start_time=bar_start_time,
                bar_start_beat=bar_start_beat,
            )

            bars.append(
                Bar(
                    index=i + 1,
                    text=bar_text,
                    syllable_count=s_count,
                    start_time=bar_start_time,
                    end_time=bar_end_time,
                    start_beat=bar_start_beat,
                    end_beat=bar_end_beat,
                    words=word_timings,
                    cadence_type=cadence.cadence_type,
                    rhyme_tag=rhyme_tag,
                    section=section,
                )
            )

        return bars

    def schedule_verse(
        self,
        lyrics: Union[str, List[str]],
        target_bars: Optional[int] = 16,
        section: str = "verse",
        pad_to_target: bool = False,
    ) -> VerseSchedule:
        """Schedule raw lyrics into a complete VerseSchedule model."""
        bars = self.schedule(
            lyrics=lyrics,
            target_bars=target_bars,
            section=section,
            pad_to_target=pad_to_target,
        )

        total_sylls = sum(b.syllable_count for b in bars)
        total_dur = len(bars) * self.bar_duration
        total_bts = len(bars) * self.beats_per_bar

        # Cadence distribution
        cadence_counts: Dict[str, int] = {}
        for b in bars:
            cadence_counts[b.cadence_type] = cadence_counts.get(b.cadence_type, 0) + 1
        dominant = max(cadence_counts.items(), key=lambda kv: kv[1])[0] if cadence_counts else "boom_bap"

        rhyme_str = "".join(b.rhyme_tag for b in bars)

        return VerseSchedule(
            bars=bars,
            bpm=self.bpm,
            time_signature=self.time_signature,
            total_duration=total_dur,
            total_beats=total_bts,
            total_syllables=total_sylls,
            rhyme_scheme=rhyme_str,
            dominant_cadence=dominant,
            section=section,
        )


# ============================================================================
# Functional Interface
# ============================================================================

def schedule_bars(
    lyrics: Union[str, List[str]],
    bpm: float = 130.0,
    time_signature: Tuple[int, int] = (4, 4),
    start_offset: float = 0.0,
    target_bars: Optional[int] = 16,
    rest_ratio: float = 0.12,
    section: str = "verse",
) -> List[Bar]:
    """Convenience helper to schedule bars with exact beats and word timings."""
    scheduler = BarScheduler(
        bpm=bpm,
        time_signature=time_signature,
        start_offset=start_offset,
        rest_ratio=rest_ratio,
    )
    return scheduler.schedule(lyrics=lyrics, target_bars=target_bars, section=section)
