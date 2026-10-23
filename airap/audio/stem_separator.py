"""Audio Stem Separation Interface and Adapters for AIRap.

Provides:
- StemType enum: VOCAL, DRUMS, BASS, OTHER
- Abstract StemSeparator interface
- MockStemSeparator: deterministic DSP filtering (low-pass, band-pass, high-pass) for testing
- DemucsCLIAdapter & UVR5CLIAdapter: production CLI wrappers with graceful fallback
"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from airap.audio.beat_detector import read_wav, write_wav

logger = logging.getLogger(__name__)


class StemType(str, Enum):
    VOCAL = "vocal"
    DRUMS = "drums"
    BASS = "bass"
    OTHER = "other"

    @classmethod
    def from_str(cls, val: str) -> StemType:
        val_lower = val.lower().strip()
        if val_lower in ("vocal", "vocals", "vox"):
            return cls.VOCAL
        elif val_lower in ("drums", "drum", "percussion"):
            return cls.DRUMS
        elif val_lower in ("bass", "sub"):
            return cls.BASS
        elif val_lower in ("other", "inst", "instrumental"):
            return cls.OTHER
        raise ValueError(f"Unknown stem type: {val}")


@dataclass
class SeparationResult:
    """Encapsulates output stem paths and metadata."""
    input_path: Path
    output_dir: Path
    stems: Dict[StemType, Path] = field(default_factory=dict)
    duration: float = 0.0
    success: bool = True
    message: str = ""

    def get(self, stem_type: Union[StemType, str]) -> Optional[Path]:
        """Retrieve path for a given StemType or string key."""
        if isinstance(stem_type, str):
            try:
                stem_type = StemType.from_str(stem_type)
            except ValueError:
                return None
        return self.stems.get(stem_type)

    @property
    def vocal_path(self) -> Optional[Path]:
        return self.get(StemType.VOCAL)

    @property
    def drums_path(self) -> Optional[Path]:
        return self.get(StemType.DRUMS)

    @property
    def bass_path(self) -> Optional[Path]:
        return self.get(StemType.BASS)

    @property
    def other_path(self) -> Optional[Path]:
        return self.get(StemType.OTHER)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_path": str(self.input_path),
            "output_dir": str(self.output_dir),
            "stems": {k.value: str(v) for k, v in self.stems.items()},
            "duration": round(self.duration, 4),
            "success": self.success,
            "message": self.message,
        }


class StemSeparator(ABC):
    """Abstract interface for multi-track stem separation."""

    @abstractmethod
    def separate(
        self,
        audio_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
    ) -> SeparationResult:
        """Separate input audio into vocal, drums, bass, and other stems."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if separator runtime/dependencies are available."""
        pass


# -----------------------------------------------------------------------------
# Pure Python DSP Filters for Mock Separation
# -----------------------------------------------------------------------------

def _lowpass_filter(samples: Sequence[float], sample_rate: int, cutoff: float) -> List[float]:
    """1st-order single-pole IIR low-pass filter."""
    if cutoff <= 0 or sample_rate <= 0:
        return list(samples)
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / sample_rate
    alpha = dt / (rc + dt)
    out = [0.0] * len(samples)
    y = 0.0
    for i, x in enumerate(samples):
        y += alpha * (x - y)
        out[i] = y
    return out


def _highpass_filter(samples: Sequence[float], sample_rate: int, cutoff: float) -> List[float]:
    """1st-order single-pole IIR high-pass filter."""
    if cutoff <= 0 or sample_rate <= 0:
        return list(samples)
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)
    out = [0.0] * len(samples)
    y = 0.0
    prev_x = 0.0
    for i, x in enumerate(samples):
        y = alpha * (y + x - prev_x)
        prev_x = x
        out[i] = y
    return out


def _bandpass_filter(
    samples: Sequence[float],
    sample_rate: int,
    low_cutoff: float,
    high_cutoff: float,
) -> List[float]:
    """Cascaded high-pass and low-pass filter forming a band-pass filter."""
    hp = _highpass_filter(samples, sample_rate, low_cutoff)
    return _lowpass_filter(hp, sample_rate, high_cutoff)


class MockStemSeparator(StemSeparator):
    """Deterministic, pure-python stem separator for testing and offline execution.
    
    Uses acoustic filtering to cleanly split audio:
    - Bass: sub & bass range (< 220 Hz)
    - Vocal: speech formant telephone band (300 Hz - 3400 Hz)
    - Drums: transient high & punch range
    - Other: harmonic mids & air
    """

    def is_available(self) -> bool:
        return True

    def separate(
        self,
        audio_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
    ) -> SeparationResult:
        in_path = Path(audio_path)
        if not in_path.exists():
            return SeparationResult(
                input_path=in_path,
                output_dir=Path(output_dir or in_path.parent),
                success=False,
                message=f"File not found: {in_path}",
            )

        samples, sr = read_wav(in_path)
        duration = len(samples) / sr if sr > 0 else 0.0

        if output_dir is None:
            out_dir = in_path.parent / f"{in_path.stem}_stems"
        else:
            out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Bass: low-pass < 220 Hz
        bass_samples = _lowpass_filter(samples, sr, cutoff=220.0)

        # 2. Vocal: bandpass 300 - 3400 Hz (speech range)
        vocal_samples = _bandpass_filter(samples, sr, low_cutoff=300.0, high_cutoff=3400.0)

        # 3. Drums: high-pass transient response combined with sub-bass kick
        hp_drums = _highpass_filter(samples, sr, cutoff=3500.0)
        lp_kick = _lowpass_filter(samples, sr, cutoff=120.0)
        drum_samples = [math.tanh(hp_drums[i] * 1.2 + lp_kick[i] * 0.8) for i in range(len(samples))]

        # 4. Other: harmonic mid-highs
        mid_other = _bandpass_filter(samples, sr, low_cutoff=1000.0, high_cutoff=6000.0)
        other_samples = [math.tanh(mid_other[i] * 0.9) for i in range(len(samples))]

        # Write WAV files for each stem
        stems: Dict[StemType, Path] = {
            StemType.VOCAL: write_wav(out_dir / "vocal.wav", vocal_samples, sample_rate=sr),
            StemType.DRUMS: write_wav(out_dir / "drums.wav", drum_samples, sample_rate=sr),
            StemType.BASS: write_wav(out_dir / "bass.wav", bass_samples, sample_rate=sr),
            StemType.OTHER: write_wav(out_dir / "other.wav", other_samples, sample_rate=sr),
        }

        return SeparationResult(
            input_path=in_path,
            output_dir=out_dir,
            stems=stems,
            duration=duration,
            success=True,
            message="Mock separation completed successfully.",
        )


class DemucsCLIAdapter(StemSeparator):
    """Adapter for Meta's Demucs music source separation CLI."""

    def __init__(
        self,
        model_name: str = "htdemucs",
        demucs_bin: Optional[str] = None,
        fallback_to_mock: bool = True,
    ):
        self.model_name = model_name
        self.demucs_bin = demucs_bin or shutil.which("demucs")
        self.fallback_to_mock = fallback_to_mock
        self._mock = MockStemSeparator()

    def is_available(self) -> bool:
        return self.demucs_bin is not None and shutil.which(self.demucs_bin) is not None

    def separate(
        self,
        audio_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
    ) -> SeparationResult:
        in_path = Path(audio_path)
        if not in_path.exists():
            return SeparationResult(
                input_path=in_path,
                output_dir=Path(output_dir or in_path.parent),
                success=False,
                message=f"File not found: {in_path}",
            )

        if not self.is_available():
            if self.fallback_to_mock:
                logger.warning("Demucs CLI not found; falling back to MockStemSeparator.")
                return self._mock.separate(audio_path, output_dir)
            raise RuntimeError(
                f"Demucs executable '{self.demucs_bin or 'demucs'}' not found in PATH."
            )

        if output_dir is None:
            out_dir = in_path.parent / f"{in_path.stem}_demucs"
        else:
            out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.demucs_bin),
            "-n",
            self.model_name,
            "-o",
            str(out_dir),
            str(in_path),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Demucs stdout: %s", res.stdout)
        except subprocess.CalledProcessError as e:
            if self.fallback_to_mock:
                logger.warning("Demucs failed (%s); falling back to mock.", e)
                return self._mock.separate(audio_path, output_dir)
            return SeparationResult(
                input_path=in_path,
                output_dir=out_dir,
                success=False,
                message=f"Demucs execution failed: {e.stderr}",
            )

        # Locate Demucs outputs in `<output_dir>/<model_name>/<track_name>/`
        model_out = out_dir / self.model_name / in_path.stem
        stems: Dict[StemType, Path] = {}
        mapping = {
            StemType.VOCAL: ["vocals.wav", "vocal.wav"],
            StemType.DRUMS: ["drums.wav", "drum.wav"],
            StemType.BASS: ["bass.wav"],
            StemType.OTHER: ["other.wav"],
        }

        for st_type, filenames in mapping.items():
            for fname in filenames:
                candidate = model_out / fname
                if candidate.exists():
                    stems[st_type] = candidate
                    break

        return SeparationResult(
            input_path=in_path,
            output_dir=out_dir,
            stems=stems,
            success=len(stems) > 0,
            message=f"Demucs separated {len(stems)} stems.",
        )


class UVR5CLIAdapter(StemSeparator):
    """Adapter for Ultimate Vocal Remover (UVR5) / audio-separator CLI."""

    def __init__(
        self,
        model_name: str = "MDX23C-8KFFT-InstVoc_HQ",
        uvr_bin: Optional[str] = None,
        fallback_to_mock: bool = True,
    ):
        self.model_name = model_name
        self.uvr_bin = uvr_bin or shutil.which("audio-separator") or shutil.which("uvr5")
        self.fallback_to_mock = fallback_to_mock
        self._mock = MockStemSeparator()

    def is_available(self) -> bool:
        return self.uvr_bin is not None and shutil.which(self.uvr_bin) is not None

    def separate(
        self,
        audio_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
    ) -> SeparationResult:
        in_path = Path(audio_path)
        if not in_path.exists():
            return SeparationResult(
                input_path=in_path,
                output_dir=Path(output_dir or in_path.parent),
                success=False,
                message=f"File not found: {in_path}",
            )

        if not self.is_available():
            if self.fallback_to_mock:
                logger.warning("UVR5 CLI not found; falling back to MockStemSeparator.")
                return self._mock.separate(audio_path, output_dir)
            raise RuntimeError("UVR5 / audio-separator binary not found in PATH.")

        if output_dir is None:
            out_dir = in_path.parent / f"{in_path.stem}_uvr5"
        else:
            out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.uvr_bin),
            str(in_path),
            "--model_filename",
            self.model_name,
            "--output_dir",
            str(out_dir),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("UVR5 stdout: %s", res.stdout)
        except subprocess.CalledProcessError as e:
            if self.fallback_to_mock:
                logger.warning("UVR5 failed (%s); falling back to mock.", e)
                return self._mock.separate(audio_path, output_dir)
            return SeparationResult(
                input_path=in_path,
                output_dir=out_dir,
                success=False,
                message=f"UVR5 execution failed: {e.stderr}",
            )

        # Inspect generated files in output_dir
        stems: Dict[StemType, Path] = {}
        for f in out_dir.glob("*.wav"):
            fname_lower = f.name.lower()
            if "vocal" in fname_lower:
                stems[StemType.VOCAL] = f
            elif "drum" in fname_lower:
                stems[StemType.DRUMS] = f
            elif "bass" in fname_lower:
                stems[StemType.BASS] = f
            elif "inst" in fname_lower or "other" in fname_lower:
                stems[StemType.OTHER] = f

        return SeparationResult(
            input_path=in_path,
            output_dir=out_dir,
            stems=stems,
            success=len(stems) > 0,
            message=f"UVR5 separated {len(stems)} stems.",
        )
