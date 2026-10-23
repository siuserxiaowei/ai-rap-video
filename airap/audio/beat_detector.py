"""Audio Beat Detection and DSP Processing Engine for AIRap.

Provides:
- BeatGrid & BeatEvent generator for quarter, eighth, sixteenth, and downbeats
- Waveform I/O with standard library (wave, struct)
- RMS energy curve calculation and transient spike/onset detection
- BPM estimation from audio onsets
- Synthetic rap beat generator: realistic 808 kick, snare, and hi-hats
"""

from __future__ import annotations

import math
import random
import struct
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


class BeatType(str, Enum):
    DOWNBEAT = "downbeat"
    QUARTER = "quarter"
    EIGHTH = "eighth"
    SIXTEENTH = "sixteenth"


@dataclass
class BeatEvent:
    """Represents a discrete musical timing event in a beat grid."""
    time: float
    beat_index: float
    bar_index: int
    beat_in_bar: float
    is_downbeat: bool = False
    is_quarter: bool = False
    is_eighth: bool = False
    is_sixteenth: bool = False
    energy: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": round(self.time, 4),
            "beat_index": round(self.beat_index, 4),
            "bar_index": self.bar_index,
            "beat_in_bar": round(self.beat_in_bar, 4),
            "is_downbeat": self.is_downbeat,
            "is_quarter": self.is_quarter,
            "is_eighth": self.is_eighth,
            "is_sixteenth": self.is_sixteenth,
            "energy": round(self.energy, 4),
        }


@dataclass
class BeatGrid:
    """Musical timing grid representing beats and subdivisions over a track duration."""
    bpm: float
    start_offset: float = 0.0
    duration: float = 0.0
    beats_per_bar: int = 4
    quarter_interval: float = 0.0
    eighth_interval: float = 0.0
    sixteenth_interval: float = 0.0
    beats: List[float] = field(default_factory=list)          # Quarter note timestamps
    downbeats: List[float] = field(default_factory=list)      # Bar start timestamps
    eighth_notes: List[float] = field(default_factory=list)   # 8th note timestamps
    sixteenth_notes: List[float] = field(default_factory=list)# 16th note timestamps
    events: List[BeatEvent] = field(default_factory=list)

    @classmethod
    def from_config(
        cls,
        config: Any,
        duration: float,
        start_offset: float = 0.0,
    ) -> "BeatGrid":
        """Instantiate BeatGrid from BeatGridConfig or similar config object."""
        bpm = getattr(config, "bpm", 130.0)
        time_sig = getattr(config, "time_signature", (4, 4))
        beats_per_bar = time_sig[0] if isinstance(time_sig, (tuple, list)) else 4
        return generate_beat_grid(
            bpm=bpm,
            duration=duration,
            start_offset=start_offset,
            beats_per_bar=beats_per_bar,
        )

    def get_nearest_beat(self, time: float) -> float:
        """Find the timestamp of the nearest quarter-note beat."""
        if not self.beats:
            return max(0.0, time)
        return min(self.beats, key=lambda b: abs(b - time))

    def get_nearest_downbeat(self, time: float) -> float:
        """Find the timestamp of the nearest downbeat (bar start)."""
        if not self.downbeats:
            return self.get_nearest_beat(time)
        return min(self.downbeats, key=lambda b: abs(b - time))

    def quantize(self, time: float, division: str = "1/4") -> float:
        """Quantize timestamp to a musical grid division ('1/1', '1/2', '1/4', '1/8', '1/16', '1/32')."""
        div_map = {
            "1/1": self.quarter_interval * self.beats_per_bar,
            "1/2": self.quarter_interval * 2.0,
            "1/4": self.quarter_interval,
            "1/8": self.eighth_interval,
            "1/16": self.sixteenth_interval,
            "1/32": self.sixteenth_interval / 2.0,
        }
        step = div_map.get(division, self.quarter_interval)
        if step <= 0:
            return time
        rel_time = time - self.start_offset
        quantized_steps = round(rel_time / step)
        return max(0.0, round(self.start_offset + (quantized_steps * step), 6))

    def get_active_bar_and_beat(self, time: float) -> Tuple[int, float]:
        """Compute the bar index (0-based) and beat position within that bar (0.0 to beats_per_bar)."""
        rel_time = max(0.0, time - self.start_offset)
        total_beats = rel_time / self.quarter_interval if self.quarter_interval > 0 else 0.0
        bar_idx = int(total_beats // self.beats_per_bar)
        beat_in_bar = total_beats % self.beats_per_bar
        return bar_idx, round(beat_in_bar, 4)

    def get_events_in_range(self, start_time: float, end_time: float) -> List[BeatEvent]:
        """Get all beat events occurring between start_time and end_time (inclusive)."""
        return [e for e in self.events if start_time <= e.time <= end_time]


def generate_beat_grid(
    bpm: float,
    duration: float,
    start_offset: float = 0.0,
    beats_per_bar: int = 4,
) -> BeatGrid:
    """Generate a high-precision BeatGrid with downbeats, quarter notes, 8th notes, and 16th notes."""
    if bpm <= 0:
        raise ValueError(f"BPM must be positive, got {bpm}")
    if duration < 0:
        raise ValueError(f"Duration cannot be negative, got {duration}")

    quarter_interval = 60.0 / bpm
    eighth_interval = quarter_interval / 2.0
    sixteenth_interval = quarter_interval / 4.0

    beats: List[float] = []
    downbeats: List[float] = []
    eighth_notes: List[float] = []
    sixteenth_notes: List[float] = []
    events: List[BeatEvent] = []

    # Generate sixteenth note grid (finest subdivision)
    if duration == 0:
        return BeatGrid(
            bpm=bpm,
            start_offset=start_offset,
            duration=duration,
            beats_per_bar=beats_per_bar,
            quarter_interval=quarter_interval,
            eighth_interval=eighth_interval,
            sixteenth_interval=sixteenth_interval,
        )

    t = start_offset
    sub_index = 0
    eps = 1e-7

    while t <= duration + eps:
        rounded_t = round(t, 6)
        if rounded_t >= 0.0:
            is_sixteenth = True
            is_eighth = (sub_index % 2 == 0)
            is_quarter = (sub_index % 4 == 0)
            beat_idx = sub_index / 4.0
            bar_idx = int(beat_idx // beats_per_bar)
            beat_in_bar = beat_idx % beats_per_bar
            is_downbeat = is_quarter and (int(round(beat_idx)) % beats_per_bar == 0)

            sixteenth_notes.append(rounded_t)
            if is_eighth:
                eighth_notes.append(rounded_t)
            if is_quarter:
                beats.append(rounded_t)
            if is_downbeat:
                downbeats.append(rounded_t)

            events.append(
                BeatEvent(
                    time=rounded_t,
                    beat_index=beat_idx,
                    bar_index=bar_idx,
                    beat_in_bar=beat_in_bar,
                    is_downbeat=is_downbeat,
                    is_quarter=is_quarter,
                    is_eighth=is_eighth,
                    is_sixteenth=is_sixteenth,
                    energy=1.2 if is_downbeat else (1.0 if is_quarter else 0.8),
                )
            )

        sub_index += 1
        t = start_offset + sub_index * sixteenth_interval

    return BeatGrid(
        bpm=bpm,
        start_offset=start_offset,
        duration=duration,
        beats_per_bar=beats_per_bar,
        quarter_interval=quarter_interval,
        eighth_interval=eighth_interval,
        sixteenth_interval=sixteenth_interval,
        beats=beats,
        downbeats=downbeats,
        eighth_notes=eighth_notes,
        sixteenth_notes=sixteenth_notes,
        events=events,
    )


# -----------------------------------------------------------------------------
# WAV Audio I/O using Python standard libraries (wave, struct)
# -----------------------------------------------------------------------------

def read_wav(file_path: Union[str, Path]) -> Tuple[List[float], int]:
    """Read a WAV file into normalized float samples [-1.0, 1.0] and sample rate.
    
    Averages stereo / multi-channel audio to mono.
    Supports 16-bit, 24-bit, and 32-bit signed PCM audio.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"WAV file not found: {path}")

    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_bytes = wf.readframes(n_frames)

    samples: List[float] = []

    if sampwidth == 2:
        total_samples = n_frames * n_channels
        unpacked = struct.unpack(f"<{total_samples}h", raw_bytes)
        if n_channels == 1:
            samples = [s / 32768.0 for s in unpacked]
        else:
            samples = [0.0] * n_frames
            for i in range(n_frames):
                ch_sum = sum(unpacked[i * n_channels + c] for c in range(n_channels))
                samples[i] = (ch_sum / n_channels) / 32768.0
    elif sampwidth == 1:
        # 8-bit unsigned PCM [0, 255]
        total_samples = n_frames * n_channels
        unpacked = struct.unpack(f"<{total_samples}B", raw_bytes)
        if n_channels == 1:
            samples = [(s - 128) / 128.0 for s in unpacked]
        else:
            samples = [0.0] * n_frames
            for i in range(n_frames):
                ch_sum = sum(unpacked[i * n_channels + c] - 128 for c in range(n_channels))
                samples[i] = (ch_sum / n_channels) / 128.0
    elif sampwidth == 3:
        # 24-bit signed PCM
        total_samples = n_frames * n_channels
        raw_vals: List[float] = []
        for i in range(total_samples):
            b = raw_bytes[i * 3 : (i + 1) * 3]
            val = int.from_bytes(b, byteorder="little", signed=True)
            raw_vals.append(val / 8388608.0)
        if n_channels == 1:
            samples = raw_vals
        else:
            samples = [0.0] * n_frames
            for i in range(n_frames):
                samples[i] = sum(raw_vals[i * n_channels + c] for c in range(n_channels)) / n_channels
    elif sampwidth == 4:
        # 32-bit signed PCM
        total_samples = n_frames * n_channels
        unpacked = struct.unpack(f"<{total_samples}i", raw_bytes)
        if n_channels == 1:
            samples = [s / 2147483648.0 for s in unpacked]
        else:
            samples = [0.0] * n_frames
            for i in range(n_frames):
                ch_sum = sum(unpacked[i * n_channels + c] for c in range(n_channels))
                samples[i] = (ch_sum / n_channels) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")

    return samples, framerate


def write_wav(
    file_path: Union[str, Path],
    samples: Sequence[float],
    sample_rate: int = 44100,
    num_channels: int = 1,
) -> Path:
    """Write normalized float samples [-1.0, 1.0] to a standard 16-bit PCM WAV file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Clamp and convert to 16-bit signed PCM
    int_samples = [int(max(-1.0, min(1.0, s)) * 32767.0) for s in samples]

    if num_channels == 2:
        # Duplicate mono to stereo
        stereo_samples: List[int] = []
        for s in int_samples:
            stereo_samples.extend([s, s])
        data_to_pack = stereo_samples
    else:
        data_to_pack = int_samples

    raw_bytes = struct.pack(f"<{len(data_to_pack)}h", *data_to_pack)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_bytes)

    return path


# -----------------------------------------------------------------------------
# Energy Curve, RMS, Transient Onset Detection & BPM Estimation
# -----------------------------------------------------------------------------

def compute_rms(
    samples: Sequence[float],
    frame_size: int = 1024,
    hop_size: int = 512,
) -> List[float]:
    """Compute Root Mean Square (RMS) energy in framing windows."""
    n = len(samples)
    if n == 0:
        return []

    rms_values: List[float] = []
    for start in range(0, n, hop_size):
        end = min(n, start + frame_size)
        frame = samples[start:end]
        if not frame:
            continue
        energy = sum(x * x for x in frame) / len(frame)
        rms_values.append(math.sqrt(energy))

    return rms_values


def compute_energy_curve(
    samples: Sequence[float],
    sample_rate: int = 44100,
    frame_size: int = 1024,
    hop_size: int = 512,
    normalize: bool = True,
) -> Tuple[List[float], List[float]]:
    """Compute timestamps and RMS energy curve across audio samples."""
    n = len(samples)
    if n == 0:
        return [], []

    times: List[float] = []
    energies: List[float] = []

    for start in range(0, n, hop_size):
        end = min(n, start + frame_size)
        frame = samples[start:end]
        if not frame:
            continue
        center_sample = (start + end) / 2.0
        times.append(round(center_sample / sample_rate, 4))
        energy = sum(x * x for x in frame) / len(frame)
        energies.append(math.sqrt(energy))

    if normalize and energies:
        max_energy = max(energies)
        if max_energy > 0:
            energies = [round(e / max_energy, 5) for e in energies]

    return times, energies


def detect_transients(
    samples: Sequence[float],
    sample_rate: int = 44100,
    threshold: float = 0.25,
    min_distance_sec: float = 0.08,
    frame_size: int = 1024,
    hop_size: int = 512,
) -> List[float]:
    """Detect transient spike onset timestamps (kicks, snares, percussive hits).
    
    Utilizes energy novelty (half-wave rectified RMS derivative) with adaptive
    thresholding and peak picking with refractory period suppression.
    """
    if len(samples) < frame_size:
        return []

    # Prepend 1 frame of silence to catch transients right at t = 0.0
    padded_samples = [0.0] * frame_size + list(samples)
    rms = compute_rms(padded_samples, frame_size=frame_size, hop_size=hop_size)

    if len(rms) < 2:
        return []

    # First-difference high-frequency onset novelty
    novelty: List[float] = [0.0]
    for i in range(1, len(rms)):
        diff = max(0.0, rms[i] - rms[i - 1])
        novelty.append(diff)

    max_nov = max(novelty) if novelty else 0.0
    if max_nov > 0:
        novelty = [n / max_nov for n in novelty]

    # Calculate timestamps corresponding to original audio
    times: List[float] = []
    for k in range(len(novelty)):
        # original sample index
        orig_sample = (k * hop_size) - frame_size
        times.append(max(0.0, round(orig_sample / sample_rate, 4)))

    peaks: List[float] = []
    last_peak_time = -10.0

    # Local moving average window (approx 150 ms)
    win_frames = max(2, int(0.15 * sample_rate / hop_size))

    for i in range(len(novelty)):
        val = novelty[i]
        # Compute local mean
        w_start = max(0, i - win_frames)
        w_end = min(len(novelty), i + win_frames + 1)
        local_mean = sum(novelty[w_start:w_end]) / (w_end - w_start)
        local_thresh = max(threshold, local_mean + (threshold * 0.5))

        if val < local_thresh:
            continue

        # Peak check against immediate neighbors
        is_peak = True
        if i > 0 and novelty[i - 1] > val:
            is_peak = False
        if i < len(novelty) - 1 and novelty[i + 1] > val:
            is_peak = False

        if is_peak:
            t = times[i]
            if t - last_peak_time >= min_distance_sec:
                peaks.append(t)
                last_peak_time = t

    return peaks


def estimate_bpm(
    onset_times: Sequence[float],
    min_bpm: float = 70.0,
    max_bpm: float = 175.0,
    default_bpm: float = 120.0,
) -> float:
    """Estimate musical BPM from detected onset intervals via inter-onset interval scoring."""
    if len(onset_times) < 4:
        return default_bpm

    # Calculate inter-onset intervals (IOIs)
    iois: List[float] = []
    for i in range(len(onset_times)):
        for j in range(i + 1, min(len(onset_times), i + 6)):
            delta = onset_times[j] - onset_times[i]
            if 0.25 <= delta <= 2.0:
                iois.append(delta)

    if not iois:
        return default_bpm

    # Score tempo candidates in 0.5 BPM steps
    best_bpm = default_bpm
    max_score = -1.0

    step_bpm = 1.0
    bpm_candidate = min_bpm
    while bpm_candidate <= max_bpm:
        beat_interval = 60.0 / bpm_candidate
        score = 0.0

        for ioi in iois:
            # Check how close ioi is to multiples/divisions (1 beat, 2 beats, 0.5 beats, 4 beats)
            for mult in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]:
                expected = beat_interval * mult
                diff = abs(ioi - expected)
                tolerance = 0.05 * mult
                if diff < tolerance:
                    weight = 1.0 / (mult if mult >= 1.0 else 2.0)
                    score += weight * (1.0 - (diff / tolerance))

        if score > max_score:
            max_score = score
            best_bpm = bpm_candidate

        bpm_candidate += step_bpm

    return round(best_bpm, 1)


@dataclass
class DetectionResult:
    """Aggregate result from BeatDetector."""
    onset_times: List[float]
    energy_times: List[float]
    energy_values: List[float]
    estimated_bpm: float
    beat_grid: Optional[BeatGrid] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimated_bpm": self.estimated_bpm,
            "onset_count": len(self.onset_times),
            "onset_times": [round(t, 4) for t in self.onset_times],
            "has_beat_grid": self.beat_grid is not None,
        }


class BeatDetector:
    """Acoustic beat and transient detection engine."""

    def __init__(
        self,
        frame_size: int = 1024,
        hop_size: int = 512,
        threshold: float = 0.25,
        min_distance_sec: float = 0.08,
    ):
        self.frame_size = frame_size
        self.hop_size = hop_size
        self.threshold = threshold
        self.min_distance_sec = min_distance_sec

    def detect(
        self,
        samples: Sequence[float],
        sample_rate: int = 44100,
        generate_grid: bool = True,
    ) -> DetectionResult:
        """Process float samples, compute energy curve, detect transients, estimate BPM."""
        duration = len(samples) / sample_rate if sample_rate > 0 else 0.0

        e_times, e_vals = compute_energy_curve(
            samples,
            sample_rate=sample_rate,
            frame_size=self.frame_size,
            hop_size=self.hop_size,
        )

        onsets = detect_transients(
            samples,
            sample_rate=sample_rate,
            threshold=self.threshold,
            min_distance_sec=self.min_distance_sec,
            frame_size=self.frame_size,
            hop_size=self.hop_size,
        )

        est_bpm = estimate_bpm(onsets)

        grid = None
        if generate_grid and est_bpm > 0 and duration > 0:
            first_onset = onsets[0] if onsets else 0.0
            grid = generate_beat_grid(
                bpm=est_bpm,
                duration=duration,
                start_offset=first_onset,
            )

        return DetectionResult(
            onset_times=onsets,
            energy_times=e_times,
            energy_values=e_vals,
            estimated_bpm=est_bpm,
            beat_grid=grid,
        )

    def detect_from_file(
        self,
        wav_path: Union[str, Path],
        generate_grid: bool = True,
    ) -> DetectionResult:
        """Load WAV audio file and perform beat & transient detection."""
        samples, sr = read_wav(wav_path)
        return self.detect(samples, sample_rate=sr, generate_grid=generate_grid)


# -----------------------------------------------------------------------------
# Synthetic Rap Beat Generator (Pure Python Standard Library)
# -----------------------------------------------------------------------------

def generate_808_kick(
    duration: float = 0.55,
    sample_rate: int = 44100,
    start_freq: float = 160.0,
    end_freq: float = 48.0,
    pitch_decay: float = 0.04,
    amp_decay: float = 0.22,
    punch_gain: float = 1.3,
) -> List[float]:
    """Synthesize an 808 kick drum using exponential pitch sweep and saturation."""
    num_samples = int(duration * sample_rate)
    samples = [0.0] * num_samples
    dt = 1.0 / sample_rate
    two_pi = 2.0 * math.pi
    freq_diff = start_freq - end_freq

    for i in range(num_samples):
        t = i * dt
        # Phase integral: 2 * pi * [end_freq * t + freq_diff * pitch_decay * (1 - exp(-t / pitch_decay))]
        phase = two_pi * (end_freq * t + freq_diff * pitch_decay * (1.0 - math.exp(-t / pitch_decay)))
        raw_sine = math.sin(phase)

        # Amplitude envelope: 3ms linear attack, exponential decay
        attack = min(1.0, t / 0.003) if t < 0.003 else 1.0
        amp = attack * math.exp(-t / amp_decay)

        # Punchy saturation via hyperbolic tangent
        samples[i] = math.tanh(punch_gain * raw_sine * amp)

    return samples


def generate_snare(
    duration: float = 0.22,
    sample_rate: int = 44100,
    tone_freq: float = 185.0,
    tone_decay: float = 0.08,
    noise_decay: float = 0.12,
    seed: Optional[int] = 42,
) -> List[float]:
    """Synthesize a rap snare / clap layering a pitched body tone with high-pass filtered noise."""
    num_samples = int(duration * sample_rate)
    samples = [0.0] * num_samples
    dt = 1.0 / sample_rate
    two_pi = 2.0 * math.pi
    rng = random.Random(seed)

    prev_noise = 0.0
    for i in range(num_samples):
        t = i * dt
        # Tone layer: slight downward bend
        curr_freq = tone_freq + tone_freq * 0.3 * math.exp(-t / 0.02)
        tone_phase = two_pi * curr_freq * t
        tone_amp = math.exp(-t / tone_decay)
        tone_val = math.sin(tone_phase) * tone_amp

        # Noise layer: 1st-order high-pass difference filter
        raw_noise = rng.uniform(-1.0, 1.0)
        hp_noise = raw_noise - 0.7 * prev_noise
        prev_noise = raw_noise
        noise_amp = math.exp(-t / noise_decay)
        noise_val = hp_noise * noise_amp

        # Combine layers and apply soft clipping
        val = 0.35 * tone_val + 0.65 * noise_val
        samples[i] = math.tanh(1.2 * val)

    return samples


def generate_hihat(
    duration: float = 0.05,
    sample_rate: int = 44100,
    is_open: bool = False,
    seed: Optional[int] = 42,
) -> List[float]:
    """Synthesize closed or open trap hi-hat tick using multi-stage high-pass noise."""
    actual_dur = 0.22 if is_open else duration
    num_samples = int(actual_dur * sample_rate)
    samples = [0.0] * num_samples
    dt = 1.0 / sample_rate
    decay_rate = 0.07 if is_open else 0.015
    rng = random.Random(seed)

    x1 = 0.0
    x2 = 0.0
    for i in range(num_samples):
        t = i * dt
        raw = rng.uniform(-1.0, 1.0)
        # 2nd-order high-pass filter
        hp = raw - 1.6 * x1 + 0.64 * x2
        x2 = x1
        x1 = raw

        amp = math.exp(-t / decay_rate)
        samples[i] = math.tanh(0.8 * hp * amp)

    return samples


class SyntheticRapBeatGenerator:
    """Generates synthetic hip-hop / rap drum tracks without external audio dependencies."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate

    def _mix_into(
        self,
        buffer: List[float],
        instrument: List[float],
        start_sample: int,
        gain: float = 1.0,
    ) -> None:
        """Mix instrument samples into master buffer starting at start_sample."""
        buf_len = len(buffer)
        for i, s in enumerate(instrument):
            idx = start_sample + i
            if 0 <= idx < buf_len:
                buffer[idx] += s * gain

    def generate_samples(
        self,
        bpm: float = 130.0,
        duration: float = 8.0,
        pattern: str = "trap",
        seed: Optional[int] = 42,
    ) -> List[float]:
        """Generate float samples for a full rap beat drum track.
        
        Supported patterns:
        - 'trap': Half-time snare on beat 3 (beat index 2), syncopated 808 kicks, 16th-note hats.
        - 'boom_bap': Classical 90s boom bap with snares on beats 2 & 4, swing hats.
        - 'basic': 4-on-the-floor rock/rap beat.
        """
        total_samples = int(duration * self.sample_rate)
        master_buffer = [0.0] * total_samples

        quarter_dur = 60.0 / bpm
        sixteenth_dur = quarter_dur / 4.0

        # Synthesize base drums
        kick = generate_808_kick(sample_rate=self.sample_rate)
        snare = generate_snare(sample_rate=self.sample_rate, seed=seed)
        closed_hat = generate_hihat(sample_rate=self.sample_rate, is_open=False, seed=seed)
        open_hat = generate_hihat(sample_rate=self.sample_rate, is_open=True, seed=seed)

        # 16-step bar patterns (steps are sixteenth notes, 4 quarters = 16 sixteenths)
        # Indices: 0, 1, 2, ..., 15
        if pattern == "trap":
            # Trap half-time feel: Snare on step 8 (beat 3)
            # Kick on step 0, step 6 (beat 2.5), step 10 (beat 3.5)
            kick_steps = [0, 6, 10]
            snare_steps = [8]
            # 16th hats on all steps with accent on 0, 4, 8, 12
            hat_steps = list(range(16))
            open_hat_steps = [14]
        elif pattern == "boom_bap":
            # Boom-bap: Snare on beat 2 and 4 (steps 4 and 12)
            # Kick on beat 1 and beat 3-and (steps 0 and 10)
            kick_steps = [0, 10]
            snare_steps = [4, 12]
            hat_steps = [0, 2, 4, 6, 8, 10, 12, 14]  # 8th notes
            open_hat_steps = []
        else:  # 'basic'
            kick_steps = [0, 8]
            snare_steps = [4, 12]
            hat_steps = [0, 2, 4, 6, 8, 10, 12, 14]
            open_hat_steps = []

        total_sixteenths = int(duration / sixteenth_dur)

        for step in range(total_sixteenths):
            step_time = step * sixteenth_dur
            start_idx = int(step_time * self.sample_rate)
            if start_idx >= total_samples:
                break

            bar_step = step % 16

            # Kick
            if bar_step in kick_steps:
                self._mix_into(master_buffer, kick, start_idx, gain=0.9)

            # Snare
            if bar_step in snare_steps:
                self._mix_into(master_buffer, snare, start_idx, gain=0.85)

            # Open Hat
            if bar_step in open_hat_steps:
                self._mix_into(master_buffer, open_hat, start_idx, gain=0.5)
            # Closed Hat
            elif bar_step in hat_steps:
                # Accent on quarter beats
                gain = 0.55 if (bar_step % 4 == 0) else 0.35
                self._mix_into(master_buffer, closed_hat, start_idx, gain=gain)

        # Master soft-limiter and normalization to -0.5 dB (peak ~0.94)
        peak = max(abs(x) for x in master_buffer) if master_buffer else 0.0
        target_peak = 0.94
        if peak > 0:
            scale = min(1.0, target_peak / peak)
            for i in range(total_samples):
                # Apply gentle saturation curve
                val = master_buffer[i] * scale
                master_buffer[i] = math.tanh(val)

        return master_buffer

    def generate_wav(
        self,
        output_path: Union[str, Path],
        bpm: float = 130.0,
        duration: float = 8.0,
        pattern: str = "trap",
        seed: Optional[int] = 42,
    ) -> Path:
        """Generate and save WAV audio file for the synthetic rap beat."""
        samples = self.generate_samples(
            bpm=bpm,
            duration=duration,
            pattern=pattern,
            seed=seed,
        )
        return write_wav(output_path, samples, sample_rate=self.sample_rate)
