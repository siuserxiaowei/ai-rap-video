"""Vocal Alignment and Phonetic Segmentation Engine for AIRap.

Provides:
- PhonemeInterval and WordInterval data models
- Grapheme-to-Phoneme (G2P) rule-based phonetic decomposition (English + Chinese)
- RuleBasedAligner: estimates word and phoneme timestamps from lyrics & audio duration
- Rhythm snapping to BeatGrid musical subdivisions
- Subtitle exporters (SRT and ASS karaoke timing format)
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from airap.audio.beat_detector import BeatGrid


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

@dataclass
class PhonemeInterval:
    """Represents a discrete phoneme timestamp interval within a word."""
    phoneme: str
    start: float
    end: float
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, round(self.end - self.start, 4))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phoneme": self.phoneme,
            "start": round(self.start, 4),
            "end": round(self.end, 4),
            "duration": self.duration,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class WordInterval:
    """Represents a word timestamp interval containing decomposed phonemes."""
    word: str
    start: float
    end: float
    phonemes: List[PhonemeInterval] = field(default_factory=list)
    confidence: float = 1.0
    is_rhyme: bool = False
    line_index: int = 0
    word_index: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, round(self.end - self.start, 4))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "start": round(self.start, 4),
            "end": round(self.end, 4),
            "duration": self.duration,
            "confidence": round(self.confidence, 4),
            "is_rhyme": self.is_rhyme,
            "line_index": self.line_index,
            "word_index": self.word_index,
            "phonemes": [p.to_dict() for p in self.phonemes],
        }


@dataclass
class AlignmentResult:
    """Full alignment output containing all word and phoneme intervals."""
    words: List[WordInterval]
    total_duration: float
    lyrics_raw: str = ""

    @property
    def phonemes(self) -> List[PhonemeInterval]:
        """Flattened list of all phonemes across words."""
        return [p for w in self.words for p in w.phonemes]

    @property
    def word_count(self) -> int:
        return len(self.words)

    def get_active_word(self, time: float) -> Optional[WordInterval]:
        """Find the word active at the specified timestamp."""
        for w in self.words:
            if w.start <= time <= w.end:
                return w
        return None

    def get_active_phoneme(self, time: float) -> Optional[PhonemeInterval]:
        """Find the phoneme active at the specified timestamp."""
        for w in self.words:
            if w.start <= time <= w.end:
                for p in w.phonemes:
                    if p.start <= time <= p.end:
                        return p
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_duration": round(self.total_duration, 4),
            "word_count": len(self.words),
            "phoneme_count": len(self.phonemes),
            "words": [w.to_dict() for w in self.words],
        }

    def to_srt(self) -> str:
        """Export word intervals as standard SubRip (SRT) subtitles grouped by line."""
        if not self.words:
            return ""

        # Group words by line_index
        lines_map: Dict[int, List[WordInterval]] = {}
        for w in self.words:
            lines_map.setdefault(w.line_index, []).append(w)

        def _format_srt_time(sec: float) -> str:
            sec = max(0.0, sec)
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            ms = int(round((sec - int(sec)) * 1000))
            if ms >= 1000:
                s += 1
                ms = 0
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        blocks: List[str] = []
        idx = 1
        for line_idx in sorted(lines_map.keys()):
            line_words = lines_map[line_idx]
            if not line_words:
                continue
            start_t = line_words[0].start
            end_t = line_words[-1].end
            text = " ".join(w.word for w in line_words)
            blocks.append(
                f"{idx}\n{_format_srt_time(start_t)} --> {_format_srt_time(end_t)}\n{text}\n"
            )
            idx += 1

        return "\n".join(blocks)

    def to_ass(self, title: str = "AIRap Karaoke") -> str:
        """Export word intervals as Advanced SubStation Alpha (ASS) karaoke format.
        
        Uses {\\k<centiseconds>} timing tags for kinetic word-by-word highlights.
        """
        header = [
            "[Script Info]",
            f"Title: {title}",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Arial Black,54,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,40,40,240,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        def _format_ass_time(sec: float) -> str:
            sec = max(0.0, sec)
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            cs = int(round((sec - int(sec)) * 100))
            if cs >= 100:
                s += 1
                cs = 0
            return f"{h:01d}:{m:02d}:{s:02d}.{cs:02d}"

        # Group words by line_index
        lines_map: Dict[int, List[WordInterval]] = {}
        for w in self.words:
            lines_map.setdefault(w.line_index, []).append(w)

        events: List[str] = []
        for line_idx in sorted(lines_map.keys()):
            line_words = lines_map[line_idx]
            if not line_words:
                continue
            line_start = line_words[0].start
            line_end = line_words[-1].end

            # Build karaoke string: {\k<cs>}Word
            karaoke_parts: List[str] = []
            for w in line_words:
                cs = max(1, int(round(w.duration * 100)))
                karaoke_parts.append(f"{{\\k{cs}}}{w.word}")

            karaoke_text = " ".join(karaoke_parts)
            events.append(
                f"Dialogue: 0,{_format_ass_time(line_start)},{_format_ass_time(line_end)},Default,,0,0,0,,{karaoke_text}"
            )

        return "\n".join(header + events)


# -----------------------------------------------------------------------------
# Grapheme-to-Phoneme (G2P) Rule-Based Decomposer
# -----------------------------------------------------------------------------

# Common English digraphs and vowels
ENGLISH_PHONEME_MAP = {
    # Vowels & diphthongs
    "ee": "IY", "ea": "IY", "ie": "IY", "igh": "AY", "ai": "EY", "ay": "EY",
    "oa": "OW", "ow": "OW", "oo": "UW", "ou": "AW", "oi": "OY", "oy": "OY",
    "aw": "AO", "au": "AO",
    # Consonants
    "ch": "CH", "sh": "SH", "th": "TH", "ph": "F", "wh": "W", "ck": "K",
    "ng": "NG", "qu": "KW", "gh": "G",
    "a": "AE", "e": "EH", "i": "IH", "o": "AA", "u": "AH", "y": "AY",
    "b": "B", "c": "K", "d": "D", "f": "F", "g": "G", "h": "HH",
    "j": "JH", "k": "K", "l": "L", "m": "M", "n": "N", "p": "P",
    "r": "R", "s": "S", "t": "T", "v": "V", "w": "W", "x": "KS", "z": "Z",
}

# Common Chinese character pinyin/phonetic components
CHINESE_CHAR_MAP: Dict[str, List[str]] = {
    "说": ["SH", "UO"], "唱": ["CH", "ANG"], "嘻": ["X", "I"], "哈": ["H", "A"],
    "麦": ["M", "AI"], "克": ["K", "E"], "风": ["F", "ENG"], "节": ["J", "IE"],
    "奏": ["Z", "OU"], "韵": ["Y", "UN"], "脚": ["J", "IAO"], "流": ["L", "IU"],
    "我": ["W", "O"], "你": ["N", "I"], "他": ["T", "A"], "的": ["D", "E"],
    "在": ["Z", "AI"], "是": ["SH", "I"], "有": ["Y", "OU"], "不": ["B", "U"],
    "这": ["ZH", "E"], "个": ["G", "E"], "上": ["SH", "ANG"], "下": ["X", "IA"],
    "来": ["L", "AI"], "去": ["Q", "U"], "听": ["T", "ING"], "看": ["K", "AN"],
}

VOWEL_PHONEMES = {
    "IY", "AY", "EY", "OW", "UW", "AW", "OY", "AO", "AE", "EH", "IH", "AA", "AH",
    "A", "E", "I", "O", "U", "AI", "EI", "AO", "OU", "IA", "IE", "UA", "UO",
    "ANG", "ENG", "ING", "ONG", "AN", "EN", "IN", "UN",
}


def decompose_word_to_phonemes(word: str) -> List[str]:
    """Decompose an English or Chinese word into constituent phoneme tokens."""
    clean = word.strip()
    if not clean:
        return ["SIL"]

    phonemes: List[str] = []

    # Check for Chinese characters
    i = 0
    while i < len(clean):
        char = clean[i]
        code = ord(char)
        # CJK Unified Ideographs block
        if 0x4E00 <= code <= 0x9FFF:
            if char in CHINESE_CHAR_MAP:
                phonemes.extend(CHINESE_CHAR_MAP[char])
            else:
                # Generic fallback for Chinese character: Initial + Final approximation
                phonemes.extend(["CH_INIT", "CH_FIN"])
            i += 1
            continue

        # English parsing
        if not char.isalpha():
            i += 1
            continue

        matched = False
        # Try 3-letter combinations (e.g. igh)
        if i + 3 <= len(clean):
            tri = clean[i : i + 3].lower()
            if tri in ENGLISH_PHONEME_MAP:
                phonemes.append(ENGLISH_PHONEME_MAP[tri])
                i += 3
                matched = True
                continue

        # Try 2-letter digraphs (e.g. sh, ch, ee, ou)
        if not matched and i + 2 <= len(clean):
            di = clean[i : i + 2].lower()
            if di in ENGLISH_PHONEME_MAP:
                phonemes.append(ENGLISH_PHONEME_MAP[di])
                i += 2
                matched = True
                continue

        # Single letter
        if not matched:
            single = char.lower()
            if single in ENGLISH_PHONEME_MAP:
                phonemes.append(ENGLISH_PHONEME_MAP[single])
            else:
                phonemes.append(single.upper())
            i += 1

    return phonemes if phonemes else ["AH"]


# -----------------------------------------------------------------------------
# Rule-Based Forced Aligner
# -----------------------------------------------------------------------------

class RuleBasedAligner:
    """Estimates word and phoneme timestamps from lyrics text and audio duration.
    
    Incorporates:
    - Bar and line structure with natural breath pause modeling
    - Grapheme-to-phoneme decomposition (English & Chinese)
    - Vowel vs consonant duration weighting (vowels receive ~60-70% sustained duration)
    - Optional BeatGrid rhythm snapping for authentic hip-hop flow
    """

    def __init__(
        self,
        min_word_duration: float = 0.12,
        inter_word_gap: float = 0.04,
        inter_line_pause: float = 0.28,
        vowel_weight: float = 2.4,
        consonant_weight: float = 1.0,
    ):
        self.min_word_duration = min_word_duration
        self.inter_word_gap = inter_word_gap
        self.inter_line_pause = inter_line_pause
        self.vowel_weight = vowel_weight
        self.consonant_weight = consonant_weight

    def align(
        self,
        lyrics: str,
        audio_duration: float,
        start_offset: float = 0.2,
        end_padding: float = 0.25,
        beat_grid: Optional[BeatGrid] = None,
    ) -> AlignmentResult:
        """Align lyrics to audio duration and generate word and phoneme intervals."""
        if audio_duration <= 0:
            return AlignmentResult(words=[], total_duration=0.0, lyrics_raw=lyrics)

        # Parse lyrics into lines and words
        raw_lines = [l.strip() for l in lyrics.strip().splitlines() if l.strip()]
        if not raw_lines:
            # Handle single-line without newlines or empty
            tokens = [t for t in lyrics.strip().split() if t]
            if tokens:
                raw_lines = [" ".join(tokens)]
            else:
                return AlignmentResult(words=[], total_duration=audio_duration, lyrics_raw=lyrics)

        # Parse tokens per line
        parsed_lines: List[List[str]] = []
        for line in raw_lines:
            words_in_line = [w.strip() for w in line.split() if w.strip()]
            if words_in_line:
                parsed_lines.append(words_in_line)

        if not parsed_lines:
            return AlignmentResult(words=[], total_duration=audio_duration, lyrics_raw=lyrics)

        # Usable vocal timeframe
        effective_start = max(0.0, start_offset)
        effective_end = max(effective_start + 0.1, audio_duration - end_padding)
        available_time = effective_end - effective_start

        # Calculate weight for each line
        line_weights: List[float] = []
        line_phonemes: List[List[List[str]]] = []

        for line_idx, line in enumerate(parsed_lines):
            line_p_list: List[List[str]] = []
            l_weight = 0.0
            for word in line:
                clean_word = re.sub(r"[^\w]", "", word)
                p_tokens = decompose_word_to_phonemes(clean_word if clean_word else word)
                line_p_list.append(p_tokens)
                l_weight += max(1.0, len(clean_word) * 0.3 + len(p_tokens) * 0.7)
            line_weights.append(l_weight)
            line_phonemes.append(line_p_list)

        num_lines = len(parsed_lines)
        total_pause_time = (num_lines - 1) * self.inter_line_pause
        # Clamp pauses if duration is too constrained
        if total_pause_time > available_time * 0.4:
            line_pause = (available_time * 0.25) / max(1, num_lines - 1)
        else:
            line_pause = self.inter_line_pause

        speech_time = max(0.1, available_time - (num_lines - 1) * line_pause)
        total_weight = sum(line_weights) if sum(line_weights) > 0 else 1.0

        words_out: List[WordInterval] = []
        current_time = effective_start

        for line_idx, line in enumerate(parsed_lines):
            line_w = line_weights[line_idx]
            line_duration = speech_time * (line_w / total_weight)
            line_start = current_time
            line_end = line_start + line_duration

            # BeatGrid snapping for line starts (musical groove)
            if beat_grid and beat_grid.beats:
                nearest_quarter = beat_grid.get_nearest_beat(line_start)
                # Snap if within 0.25 seconds and keeps valid order
                if abs(nearest_quarter - line_start) < 0.25 and nearest_quarter >= current_time - 0.05:
                    shift = nearest_quarter - line_start
                    line_start = max(0.0, nearest_quarter)
                    line_end += shift

            # Distribute time among words in the line
            num_words = len(line)
            word_p_lists = line_phonemes[line_idx]

            # Calculate word weights
            word_weights = [max(1.0, len(w) * 0.3 + len(p) * 0.7) for w, p in zip(line, word_p_lists)]
            sum_w_weights = sum(word_weights) if sum(word_weights) > 0 else 1.0

            total_word_gaps = (num_words - 1) * self.inter_word_gap
            actual_gap = self.inter_word_gap if total_word_gaps < line_duration * 0.3 else 0.01
            word_available = max(0.05 * num_words, line_duration - (num_words - 1) * actual_gap)

            w_curr_time = line_start
            for w_idx, word in enumerate(line):
                w_dur = word_available * (word_weights[w_idx] / sum_w_weights)
                w_start = w_curr_time
                w_end = w_start + w_dur

                # Last word of a line in rap is marked as rhyme
                is_rhyme = (w_idx == num_words - 1)

                # Optional beat quantization for word start
                if beat_grid and beat_grid.sixteenth_notes:
                    quant_start = beat_grid.quantize(w_start, division="1/16")
                    # Apply snapping if it preserves order
                    if abs(quant_start - w_start) <= 0.08 and quant_start >= w_curr_time:
                        w_start = quant_start
                        if w_end <= w_start + 0.05:
                            w_end = w_start + 0.05

                # Decompose and distribute phonemes within the word
                p_tokens = word_p_lists[w_idx]
                phoneme_intervals = self._allocate_phonemes(p_tokens, w_start, w_end)

                word_obj = WordInterval(
                    word=word,
                    start=round(w_start, 4),
                    end=round(w_end, 4),
                    phonemes=phoneme_intervals,
                    confidence=0.95,
                    is_rhyme=is_rhyme,
                    line_index=line_idx,
                    word_index=w_idx,
                )
                words_out.append(word_obj)

                w_curr_time = w_end + actual_gap

            current_time = max(w_curr_time, line_end) + line_pause

        # Ensure word intervals are strictly non-overlapping and within audio_duration
        for i in range(len(words_out) - 1):
            if words_out[i].end > words_out[i + 1].start:
                # adjust midpoint
                mid = (words_out[i].start + words_out[i + 1].end) / 2.0
                words_out[i].end = round(mid - 0.01, 4)
                words_out[i + 1].start = round(mid, 4)
                # re-adjust phonemes
                words_out[i].phonemes = self._allocate_phonemes(
                    [p.phoneme for p in words_out[i].phonemes],
                    words_out[i].start,
                    words_out[i].end,
                )
                words_out[i + 1].phonemes = self._allocate_phonemes(
                    [p.phoneme for p in words_out[i + 1].phonemes],
                    words_out[i + 1].start,
                    words_out[i + 1].end,
                )

        return AlignmentResult(
            words=words_out,
            total_duration=audio_duration,
            lyrics_raw=lyrics,
        )

    def _allocate_phonemes(
        self,
        phonemes: List[str],
        start: float,
        end: float,
    ) -> List[PhonemeInterval]:
        """Distribute timestamps for phoneme tokens within a word's start and end window."""
        if not phonemes:
            return []

        word_dur = max(0.01, end - start)
        weights: List[float] = []

        for p in phonemes:
            p_upper = p.upper()
            if p_upper in VOWEL_PHONEMES or any(v in p_upper for v in ("A", "E", "I", "O", "U")):
                weights.append(self.vowel_weight)
            else:
                weights.append(self.consonant_weight)

        total_weight = sum(weights)
        intervals: List[PhonemeInterval] = []
        curr = start

        for idx, (p, w) in enumerate(zip(phonemes, weights)):
            dur = word_dur * (w / total_weight)
            p_start = curr
            p_end = p_start + dur if idx < len(phonemes) - 1 else end
            intervals.append(
                PhonemeInterval(
                    phoneme=p,
                    start=round(p_start, 4),
                    end=round(p_end, 4),
                    confidence=0.92,
                )
            )
            curr = p_end

        return intervals


# Convenience function
def align_lyrics(
    lyrics: str,
    audio_duration: float,
    beat_grid: Optional[BeatGrid] = None,
    start_offset: float = 0.2,
) -> AlignmentResult:
    """Convenience functional wrapper for RuleBasedAligner."""
    aligner = RuleBasedAligner()
    return aligner.align(
        lyrics=lyrics,
        audio_duration=audio_duration,
        start_offset=start_offset,
        beat_grid=beat_grid,
    )
