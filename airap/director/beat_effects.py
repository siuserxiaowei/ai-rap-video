"""Visual beat effects triggered by downbeats, kicks, snares, and drops."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BeatEffectType(str, Enum):
    """Categorization of beat-driven visual impact effects."""
    ZOOM_PULSE = "zoom_pulse"
    SHAKE = "shake"
    FLASH_GLITCH = "flash_glitch"


@dataclass
class BeatEffect:
    """Base class for beat-synchronized visual effects."""
    start_time: float
    duration: float
    intensity: float = 1.0
    effect_type: BeatEffectType = BeatEffectType.ZOOM_PULSE
    parameters: Dict[str, Any] = field(default_factory=dict)

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    def is_active_at(self, timestamp: float) -> bool:
        return self.start_time <= timestamp < self.end_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_type": self.effect_type.value,
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "duration": round(self.duration, 3),
            "intensity": round(self.intensity, 3),
            "parameters": self.parameters
        }

    def get_ffmpeg_filter(self, width: int = 1080, height: int = 1920, fps: int = 30) -> str:
        """Generate FFmpeg filter expression representing this effect."""
        raise NotImplementedError


@dataclass
class ZoomPulse(BeatEffect):
    """
    Subtle punch zoom on kick drum / downbeats.
    Instantly punches in by zoom_scale and smoothly relaxes over duration.
    """
    zoom_scale: float = 1.06

    def __post_init__(self):
        self.effect_type = BeatEffectType.ZOOM_PULSE
        if not self.parameters:
            self.parameters = {"zoom_scale": self.zoom_scale}
        else:
            self.zoom_scale = self.parameters.get("zoom_scale", self.zoom_scale)

    def get_ffmpeg_filter(self, width: int = 1080, height: int = 1920, fps: int = 30) -> str:
        s = round(self.start_time, 3)
        e = round(self.end_time, 3)
        d = max(0.01, round(self.duration, 3))
        zoom_delta = round((self.zoom_scale - 1.0) * self.intensity, 4)

        return (
            f"zoompan=z='if(between(time,{s},{e}),1+{zoom_delta}*(1-(time-{s})/{d}),1)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps}"
        )


@dataclass
class ShakeEffect(BeatEffect):
    """
    Camera shake on bass drops, heavy snares, or punchline impacts.
    High-frequency sinusoidal translation with exponential decay.
    """
    amplitude_px: float = 16.0
    frequency_hz: float = 24.0

    def __post_init__(self):
        self.effect_type = BeatEffectType.SHAKE
        if not self.parameters:
            self.parameters = {
                "amplitude_px": self.amplitude_px,
                "frequency_hz": self.frequency_hz
            }
        else:
            self.amplitude_px = self.parameters.get("amplitude_px", self.amplitude_px)
            self.frequency_hz = self.parameters.get("frequency_hz", self.frequency_hz)

    def get_ffmpeg_filter(self, width: int = 1080, height: int = 1920, fps: int = 30) -> str:
        s = round(self.start_time, 3)
        e = round(self.end_time, 3)
        d = max(0.01, round(self.duration, 3))
        amp = round(self.amplitude_px * self.intensity, 2)
        pad = int(max(20, amp * 2))
        freq = round(self.frequency_hz, 1)

        x_off = f"{pad // 2}+sin(2*PI*{freq}*(t-{s}))*{amp}*between(t,{s},{e})*(1-(t-{s})/{d})"
        y_off = f"{pad // 2}+cos(2*PI*{freq}*(t-{s}))*{amp}*between(t,{s},{e})*(1-(t-{s})/{d})"

        return (
            f"crop=w=iw-{pad}:h=ih-{pad}:"
            f"x='{x_off}':y='{y_off}',"
            f"scale={width}:{height}"
        )


@dataclass
class FlashGlitch(BeatEffect):
    """
    Flash or color invert on section transitions (e.g. verse to chorus, drops).
    """
    flash_type: str = "white_flash"  # "white_flash", "color_invert", "exposure_spike"

    def __post_init__(self):
        self.effect_type = BeatEffectType.FLASH_GLITCH
        if not self.parameters:
            self.parameters = {"flash_type": self.flash_type}
        else:
            self.flash_type = self.parameters.get("flash_type", self.flash_type)

    def get_ffmpeg_filter(self, width: int = 1080, height: int = 1920, fps: int = 30) -> str:
        s = round(self.start_time, 3)
        e = round(self.end_time, 3)
        d = max(0.01, round(self.duration, 3))

        if self.flash_type == "color_invert":
            return f"negate=enable='between(t,{s},{e})'"
        else:
            b_val = round(0.6 * self.intensity, 2)
            decay = f"between(t,{s},{e}) * (1 - (t - {s}) / {d})"
            return f"eq=brightness='{b_val} * {decay}':eval=frame"


class BeatEffectScheduler:
    """
    Analyzes rhythm grids and schedules beat-synced visual impact effects.
    """

    def __init__(
        self,
        zoom_intensity: float = 1.0,
        shake_intensity: float = 1.0,
        glitch_intensity: float = 1.0
    ):
        self.zoom_intensity = zoom_intensity
        self.shake_intensity = shake_intensity
        self.glitch_intensity = glitch_intensity

    def schedule_beat_effects(
        self,
        bpm: float = 130.0,
        duration: float = 10.0,
        beat_grid: Optional[Any] = None,
        enable_zoom: bool = True,
        enable_shake: bool = True,
        enable_glitch: bool = True
    ) -> List[BeatEffect]:
        """
        Generate a list of beat effects aligned to musical timing.

        Args:
            bpm: Tempo of the track.
            duration: Video length in seconds.
            beat_grid: Optional object containing beat markers (downbeats, snares, drops).
            enable_zoom: Add ZoomPulse on kicks/downbeats.
            enable_shake: Add ShakeEffect on drops/heavy beats.
            enable_glitch: Add FlashGlitch on section markers.
        """
        effects: List[BeatEffect] = []
        if duration <= 0:
            return effects

        # 1. If explicit beat_grid is provided
        if beat_grid and hasattr(beat_grid, "beats"):
            for b in beat_grid.beats:
                t = getattr(b, "time", 0.0)
                is_downbeat = getattr(b, "is_downbeat", False)
                is_drop = getattr(b, "is_drop", False)
                is_snare = getattr(b, "is_snare", False)

                if is_downbeat and enable_zoom:
                    effects.append(
                        ZoomPulse(
                            start_time=t,
                            duration=0.15,
                            intensity=self.zoom_intensity,
                            zoom_scale=1.06
                        )
                    )
                if is_drop and enable_shake:
                    effects.append(
                        ShakeEffect(
                            start_time=t,
                            duration=0.35,
                            intensity=self.shake_intensity * 1.5,
                            amplitude_px=20.0
                        )
                    )
                elif is_snare and enable_shake:
                    effects.append(
                        ShakeEffect(
                            start_time=t,
                            duration=0.20,
                            intensity=self.shake_intensity * 0.7,
                            amplitude_px=10.0
                        )
                    )

            if enable_glitch and hasattr(beat_grid, "sections"):
                for sec in beat_grid.sections:
                    sec_time = getattr(sec, "start_time", 0.0)
                    effects.append(
                        FlashGlitch(
                            start_time=sec_time,
                            duration=0.12,
                            intensity=self.glitch_intensity,
                            flash_type="white_flash"
                        )
                    )

        # 2. Algorithmic procedural rhythm generation from BPM
        else:
            beat_sec = 60.0 / max(40.0, bpm)
            bar_sec = beat_sec * 4  # 4/4 time

            total_bars = int(duration / bar_sec) + 1

            for bar in range(total_bars):
                bar_start = bar * bar_sec
                if bar_start >= duration:
                    break

                # Beat 1: Downbeat Kick -> ZoomPulse
                if enable_zoom:
                    effects.append(
                        ZoomPulse(
                            start_time=round(bar_start, 3),
                            duration=0.14,
                            intensity=self.zoom_intensity,
                            zoom_scale=1.05
                        )
                    )

                # Beat 3: Secondary kick/snare -> Subtle punch
                beat3_time = bar_start + 2 * beat_sec
                if beat3_time < duration and enable_zoom:
                    effects.append(
                        ZoomPulse(
                            start_time=round(beat3_time, 3),
                            duration=0.10,
                            intensity=self.zoom_intensity * 0.8,
                            zoom_scale=1.03
                        )
                    )

                # Section transition glitch every 8 bars (or bar 4 for short demos)
                if enable_glitch and bar > 0 and (bar % 8 == 0 or (duration < 15.0 and bar % 4 == 0)):
                    effects.append(
                        FlashGlitch(
                            start_time=round(bar_start, 3),
                            duration=0.12,
                            intensity=self.glitch_intensity,
                            flash_type="white_flash"
                        )
                    )
                    if enable_shake:
                        effects.append(
                            ShakeEffect(
                                start_time=round(bar_start, 3),
                                duration=0.30,
                                intensity=self.shake_intensity,
                                amplitude_px=16.0
                            )
                        )

        # Sort effects chronologically
        effects.sort(key=lambda e: e.start_time)
        return effects
