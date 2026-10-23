"""Phoneme to Viseme mapping and fast-cadence co-articulation smoothing.

Designed for high-cadence rap vocal delivery (140+ BPM) with support for
both English (ARPABET) and Chinese (Pinyin) phonemes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class Viseme(str, Enum):
    """Standard Viseme categories for facial animation and lip synchronization."""
    SIL = "SIL"      # Silence, rest mouth position
    AA = "AA"        # Open vowel ('father', 'ah', 'car', 'a', 'ia')
    EE = "EE"        # High front spread vowel ('see', 'eat', 'i', 'yi')
    IH = "IH"        # Mid-high front vowel ('bit', 'pet', 'cat', 'e')
    OH = "OH"        # Open back rounded vowel ('go', 'law', 'o', 'uo')
    OU = "OU"        # Close back rounded vowel ('too', 'blue', 'u', 'w')
    MBP = "MBP"      # Bilabial plosives/nasals ('m', 'b', 'p')
    FV = "FV"        # Labiodental fricatives ('f', 'v')
    TH = "TH"        # Dental fricatives ('th', 'dh')
    TD = "TD"        # Alveolar consonants ('t', 'd', 's', 'z', 'n', 'l', 'r')
    KG = "KG"        # Velar consonants ('k', 'g', 'ng', 'h')
    CH_SH = "CH_SH"  # Palato-alveolar affricates/fricatives ('ch', 'sh', 'j', 'zh')


# Default target mouth shapes: (mouth_open [0..1], mouth_wide [0..1])
DEFAULT_VISEME_SHAPES: Dict[Viseme, Tuple[float, float]] = {
    Viseme.SIL: (0.0, 0.0),
    Viseme.AA: (0.90, 0.50),
    Viseme.EE: (0.30, 0.90),
    Viseme.IH: (0.50, 0.65),
    Viseme.OH: (0.80, 0.20),
    Viseme.OU: (0.40, 0.10),
    Viseme.MBP: (0.00, 0.30),
    Viseme.FV: (0.15, 0.40),
    Viseme.TH: (0.20, 0.40),
    Viseme.TD: (0.25, 0.50),
    Viseme.KG: (0.35, 0.50),
    Viseme.CH_SH: (0.30, 0.25),
}


@dataclass
class TimedPhoneme:
    """Timed phoneme unit with start and end times in seconds."""
    phoneme: str
    start: float
    end: float
    stress: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class TimedViseme:
    """Timed viseme representation with duration and target shape."""
    viseme: Viseme
    start: float
    end: float
    mouth_open: float
    mouth_wide: float
    stress: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


class PhonemeVisemeMapper:
    """Bi-lingual phoneme-to-viseme mapper for English (ARPABET) and Chinese (Pinyin)."""

    # English ARPABET phonemes to Viseme
    _ARPABET_MAP: Dict[str, Viseme] = {
        # Silence & Breath
        "SIL": Viseme.SIL,
        "SP": Viseme.SIL,
        "PAUSE": Viseme.SIL,
        "REST": Viseme.SIL,
        "": Viseme.SIL,
        "HH": Viseme.AA,
        # Vowels
        "AA": Viseme.AA,
        "AH": Viseme.AA,
        "AY": Viseme.AA,
        "AE": Viseme.IH,
        "EH": Viseme.IH,
        "ER": Viseme.IH,
        "IH": Viseme.IH,
        "EY": Viseme.EE,
        "IY": Viseme.EE,
        "AO": Viseme.OH,
        "AW": Viseme.OU,
        "OW": Viseme.OU,
        "OY": Viseme.OH,
        "UH": Viseme.OU,
        "UW": Viseme.OU,
        # Consonants
        "B": Viseme.MBP,
        "P": Viseme.MBP,
        "M": Viseme.MBP,
        "F": Viseme.FV,
        "V": Viseme.FV,
        "TH": Viseme.TH,
        "DH": Viseme.TH,
        "T": Viseme.TD,
        "D": Viseme.TD,
        "S": Viseme.TD,
        "Z": Viseme.TD,
        "N": Viseme.TD,
        "L": Viseme.TD,
        "R": Viseme.TD,
        "K": Viseme.KG,
        "G": Viseme.KG,
        "NG": Viseme.KG,
        "CH": Viseme.CH_SH,
        "JH": Viseme.CH_SH,
        "SH": Viseme.CH_SH,
        "ZH": Viseme.CH_SH,
        "W": Viseme.OU,
        "Y": Viseme.EE,
    }

    # Chinese Pinyin Initials (声母)
    _PINYIN_INITIALS: Dict[str, Viseme] = {
        "b": Viseme.MBP,
        "p": Viseme.MBP,
        "m": Viseme.MBP,
        "f": Viseme.FV,
        "d": Viseme.TD,
        "t": Viseme.TD,
        "n": Viseme.TD,
        "l": Viseme.TD,
        "g": Viseme.KG,
        "k": Viseme.KG,
        "h": Viseme.KG,
        "j": Viseme.CH_SH,
        "q": Viseme.CH_SH,
        "x": Viseme.CH_SH,
        "zh": Viseme.CH_SH,
        "ch": Viseme.CH_SH,
        "sh": Viseme.CH_SH,
        "r": Viseme.CH_SH,
        "z": Viseme.TD,
        "c": Viseme.TD,
        "s": Viseme.TD,
        "y": Viseme.EE,
        "w": Viseme.OU,
    }

    # Chinese Pinyin Finals (韵母)
    _PINYIN_FINALS: Dict[str, Viseme] = {
        "a": Viseme.AA,
        "ia": Viseme.AA,
        "ua": Viseme.AA,
        "va": Viseme.AA,
        "o": Viseme.OH,
        "uo": Viseme.OH,
        "e": Viseme.EE,
        "ie": Viseme.EE,
        "ve": Viseme.EE,
        "ue": Viseme.EE,
        "ai": Viseme.AA,
        "uai": Viseme.AA,
        "ei": Viseme.EE,
        "ui": Viseme.EE,
        "uei": Viseme.EE,
        "ao": Viseme.OH,
        "iao": Viseme.OH,
        "ou": Viseme.OU,
        "iu": Viseme.OU,
        "iou": Viseme.OU,
        "an": Viseme.AA,
        "ian": Viseme.AA,
        "uan": Viseme.AA,
        "van": Viseme.AA,
        "en": Viseme.IH,
        "in": Viseme.IH,
        "un": Viseme.IH,
        "uen": Viseme.IH,
        "vn": Viseme.IH,
        "ang": Viseme.AA,
        "iang": Viseme.AA,
        "uang": Viseme.AA,
        "eng": Viseme.OH,
        "ing": Viseme.OH,
        "ueng": Viseme.OH,
        "ong": Viseme.OH,
        "iong": Viseme.OH,
        "i": Viseme.EE,
        "u": Viseme.OU,
        "v": Viseme.OU,
        "ü": Viseme.OU,
        "er": Viseme.IH,
    }

    def __init__(self, custom_shapes: Optional[Dict[Viseme, Tuple[float, float]]] = None):
        self.shapes = dict(DEFAULT_VISEME_SHAPES)
        if custom_shapes:
            self.shapes.update(custom_shapes)

    def map_phoneme(self, phoneme: str) -> Viseme:
        """Map a single phoneme string (English ARPABET or Chinese Pinyin) to Viseme."""
        if not phoneme or not phoneme.strip():
            return Viseme.SIL

        raw = phoneme.strip()

        # 1. Check exact uppercase ARPABET without stress digit (e.g. "AA1" -> "AA")
        cleaned_en = re.sub(r"\d+$", "", raw.upper())
        if cleaned_en in self._ARPABET_MAP:
            return self._ARPABET_MAP[cleaned_en]

        # 2. Check Chinese pinyin in lowercase
        cleaned_cn = re.sub(r"[1-5]$", "", raw.lower())
        if cleaned_cn in self._PINYIN_FINALS:
            return self._PINYIN_FINALS[cleaned_cn]
        if cleaned_cn in self._PINYIN_INITIALS:
            return self._PINYIN_INITIALS[cleaned_cn]

        # 3. Parse composite pinyin syllables (e.g., 'shuo', 'rap', 'flow', 'ni', 'ha')
        # Check compound initials: zh, ch, sh
        for initial in ("zh", "ch", "sh"):
            if cleaned_cn.startswith(initial) and len(cleaned_cn) > len(initial):
                final = cleaned_cn[len(initial):]
                if final in self._PINYIN_FINALS:
                    return self._PINYIN_FINALS[final]

        # Check single letter initials
        if len(cleaned_cn) > 1 and cleaned_cn[0] in self._PINYIN_INITIALS:
            final = cleaned_cn[1:]
            if final in self._PINYIN_FINALS:
                return self._PINYIN_FINALS[final]

        # 4. Fallback heuristics: vowel sounds
        vowel_match = re.search(r"[aeiouüv]+", cleaned_cn)
        if vowel_match:
            sub = vowel_match.group(0)
            if sub in self._PINYIN_FINALS:
                return self._PINYIN_FINALS[sub]
            if "a" in sub:
                return Viseme.AA
            if "o" in sub:
                return Viseme.OH
            if "e" in sub:
                return Viseme.EE
            if "u" in sub or "v" in sub:
                return Viseme.OU
            if "i" in sub:
                return Viseme.EE

        # Default fallback to SIL
        return Viseme.SIL

    def get_shape(self, viseme: Viseme) -> Tuple[float, float]:
        """Get default (mouth_open, mouth_wide) values for a viseme."""
        return self.shapes.get(viseme, (0.0, 0.0))

    def map_timed_phonemes(
        self,
        timed_phonemes: Sequence[TimedPhoneme],
    ) -> List[TimedViseme]:
        """Map a list of TimedPhoneme to TimedViseme objects."""
        results: List[TimedViseme] = []
        for tp in timed_phonemes:
            v = self.map_phoneme(tp.phoneme)
            base_open, base_wide = self.get_shape(v)
            # Apply stress factor to open amplitude (capped at 1.0)
            stress_open = min(1.0, base_open * tp.stress)
            stress_wide = min(1.0, base_wide * tp.stress)
            results.append(
                TimedViseme(
                    viseme=v,
                    start=tp.start,
                    end=tp.end,
                    mouth_open=stress_open,
                    mouth_wide=stress_wide,
                    stress=tp.stress,
                )
            )
        return results


class CoArticulationFilter:
    """Co-articulation filter designed for high-cadence rap vocal delivery (140+ BPM).

    Prevents unnatural mouth twitching, violent flutter, and machine-gun mouth
    artifacts when syllables change rapidly (e.g., 16th/32nd notes at 140+ BPM).

    Mechanisms:
    1. Target Undershoot: Rapid phonemes (<100ms) do not reach extreme articulatory
       targets, smoothly damping excursion towards a neutral posture.
    2. Cadence-Aware EMA Smoothing: Dynamically adjusts filter inertia tau based
       on BPM tempo and sampling intervals.
    3. Slew-Rate Limiter: Hard-clamps per-frame velocity delta to eliminate
       single-frame pop/flicker while retaining snappy sync on accented rap bars.
    """

    def __init__(
        self,
        bpm: float = 140.0,
        tau_base: float = 0.045,
        max_delta_per_second: float = 8.5,
        undershoot_min_duration: float = 0.10,
    ):
        """Initialize co-articulation filter.

        Args:
            bpm: Musical tempo in beats per minute.
            tau_base: Base exponential smoothing time constant in seconds.
            max_delta_per_second: Max allowed change in mouth parameter per second.
            undershoot_min_duration: Duration threshold below which undershoot applies.
        """
        self.bpm = bpm
        self.tau_base = tau_base
        self.max_delta_per_second = max_delta_per_second
        self.undershoot_min_duration = undershoot_min_duration

    def _get_cadence_tau(self, bpm: float) -> float:
        """Adjust smoothing time constant tau based on tempo cadence."""
        # At 140+ BPM, cadence is intense: we balance snappy response with jitter suppression
        if bpm >= 160:
            return self.tau_base * 0.85
        elif bpm >= 130:
            return self.tau_base
        else:
            return self.tau_base * 1.15

    def apply_undershoot(
        self,
        mouth_open: float,
        mouth_wide: float,
        duration: float,
        neutral_open: float = 0.15,
        neutral_wide: float = 0.35,
    ) -> Tuple[float, float]:
        """Apply articulatory target undershoot for brief phonemes.

        In real speech, articulators do not complete full closure or extreme wide
        openings when moving between syllables faster than ~80-100ms.
        """
        if duration >= self.undershoot_min_duration or duration <= 0:
            return mouth_open, mouth_wide

        # Scale factor between [0.45, 1.0]
        factor = 0.45 + 0.55 * (duration / self.undershoot_min_duration)
        adjusted_open = neutral_open + (mouth_open - neutral_open) * factor
        adjusted_wide = neutral_wide + (mouth_wide - neutral_wide) * factor
        return adjusted_open, adjusted_wide

    def smooth_sequence(
        self,
        raw_targets: Sequence[Tuple[float, float]],
        timestamps: Sequence[float],
        bpm: Optional[float] = None,
    ) -> List[Tuple[float, float]]:
        """Filter a discrete sequence of (mouth_open, mouth_wide) target frames.

        Args:
            raw_targets: List of (open, wide) raw values.
            timestamps: Timestamp of each frame in seconds.
            bpm: Optional tempo override.

        Returns:
            Smoothed (open, wide) frame tuples with twitching eliminated.
        """
        if not raw_targets:
            return []
        if len(raw_targets) == 1:
            return [raw_targets[0]]

        curr_bpm = bpm if bpm is not None else self.bpm
        tau = self._get_cadence_tau(curr_bpm)
        results: List[Tuple[float, float]] = []

        curr_open, curr_wide = raw_targets[0]
        results.append((curr_open, curr_wide))

        for i in range(1, len(raw_targets)):
            dt = max(1e-4, timestamps[i] - timestamps[i - 1])
            target_open, target_wide = raw_targets[i]

            # 1. EMA alpha based on time delta and adaptive tau
            alpha = 1.0 - (2.718281828459045 ** (-dt / tau))

            smoothed_open = curr_open + alpha * (target_open - curr_open)
            smoothed_wide = curr_wide + alpha * (target_wide - curr_wide)

            # 2. Slew-rate velocity clamping to prevent single-frame spikes
            max_delta = self.max_delta_per_second * dt
            delta_open = smoothed_open - curr_open
            delta_wide = smoothed_wide - curr_wide

            if abs(delta_open) > max_delta:
                smoothed_open = curr_open + (max_delta if delta_open > 0 else -max_delta)
            if abs(delta_wide) > max_delta:
                smoothed_wide = curr_wide + (max_delta if delta_wide > 0 else -max_delta)

            # Clamp to valid [0.0, 1.0] range
            smoothed_open = max(0.0, min(1.0, smoothed_open))
            smoothed_wide = max(0.0, min(1.0, smoothed_wide))

            curr_open = smoothed_open
            curr_wide = smoothed_wide
            results.append((curr_open, curr_wide))

        return results

    def filter_timed_visemes(
        self,
        timed_visemes: Sequence[TimedViseme],
        total_duration: float,
        fps: int = 30,
        bpm: Optional[float] = None,
    ) -> List[Tuple[float, float, Viseme]]:
        """Generate smooth continuous frames from timed visemes for video rendering.

        Returns a list of (mouth_open, mouth_wide, active_viseme) for every frame.
        """
        if total_duration <= 0:
            return []

        frame_count = max(1, int(round(total_duration * fps)))
        dt = 1.0 / fps
        timestamps = [i * dt for i in range(frame_count)]

        # Sample raw targets at frame timestamps
        raw_targets: List[Tuple[float, float]] = []
        visemes_at_frame: List[Viseme] = []

        for t in timestamps:
            active_v = Viseme.SIL
            active_open = 0.0
            active_wide = 0.0

            # Find matching timed viseme
            for tv in timed_visemes:
                if tv.start <= t <= tv.end:
                    active_v = tv.viseme
                    # Apply duration undershoot to target
                    active_open, active_wide = self.apply_undershoot(
                        tv.mouth_open, tv.mouth_wide, tv.duration
                    )
                    break

            raw_targets.append((active_open, active_wide))
            visemes_at_frame.append(active_v)

        # Smooth raw targets with cadence co-articulation filter
        smoothed = self.smooth_sequence(raw_targets, timestamps, bpm=bpm)

        return [
            (smoothed[i][0], smoothed[i][1], visemes_at_frame[i])
            for i in range(frame_count)
        ]
