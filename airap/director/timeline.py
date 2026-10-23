"""Timeline and cut scheduling model for AIRapStudio director."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ShotType(str, Enum):
    """Camera shot framing types for rap video pacing."""
    CLOSE_UP = "close_up"      # Intimate vocal delivery, tight facial lip-sync
    MEDIUM = "medium"          # Waist-up, hip-hop hand gestures & body cadence
    B_ROLL = "b_roll"          # Cutaway / street atmosphere / glitch / crowd
    WIDE = "wide"              # Full scene stage / environmental establishment


@dataclass
class CutPoint:
    """Represents a scheduled shot or cut in the timeline."""
    start_time: float
    end_time: float
    shot_type: ShotType | str
    scene_id: str = ""
    description: str = ""
    transition: str = "cut"    # "cut", "fade", "glitch", "zoom"
    source_clip: Optional[str] = None
    speed_factor: float = 1.0
    effects: List[Any] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def to_dict(self) -> Dict[str, Any]:
        shot_val = self.shot_type.value if hasattr(self.shot_type, "value") else str(self.shot_type)
        return {
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "duration": round(self.duration, 3),
            "shot_type": shot_val,
            "scene_id": self.scene_id,
            "description": self.description,
            "transition": self.transition,
            "source_clip": self.source_clip,
            "speed_factor": self.speed_factor,
            "effects_count": len(self.effects)
        }


@dataclass
class VideoTrack:
    """Sequence of video cuts forming the visual narrative."""
    cuts: List[CutPoint] = field(default_factory=list)

    def add_cut(self, cut: CutPoint) -> None:
        self.cuts.append(cut)
        self.cuts.sort(key=lambda c: c.start_time)

    def get_cut_at(self, timestamp: float) -> Optional[CutPoint]:
        for cut in self.cuts:
            if cut.start_time <= timestamp < cut.end_time:
                return cut
        return None

    def total_duration(self) -> float:
        if not self.cuts:
            return 0.0
        return max(cut.end_time for cut in self.cuts)

    def validate(self) -> bool:
        """Validate that cuts are chronologically non-overlapping and contiguous."""
        if not self.cuts:
            return True
        for i in range(len(self.cuts) - 1):
            curr_cut = self.cuts[i]
            next_cut = self.cuts[i + 1]
            if curr_cut.end_time > next_cut.start_time + 1e-4:
                return False
        return True


@dataclass
class AudioTrack:
    """Master audio track for the music video."""
    audio_path: Optional[str] = None
    duration: float = 0.0
    bpm: float = 130.0
    volume: float = 1.0
    sample_rate: int = 44100


@dataclass
class SubtitleTrack:
    """Subtitle track containing lyric events and ASS styling."""
    ass_path: Optional[str] = None
    subtitles: List[Any] = field(default_factory=list)


@dataclass
class EffectTrack:
    """Track containing time-coded visual beat effects."""
    effects: List[Any] = field(default_factory=list)

    def add_effect(self, effect: Any) -> None:
        self.effects.append(effect)
        self.effects.sort(key=lambda e: getattr(e, "start_time", 0.0))

    def get_effects_at(self, timestamp: float) -> List[Any]:
        return [
            e for e in self.effects
            if getattr(e, "start_time", 0.0) <= timestamp < (getattr(e, "start_time", 0.0) + getattr(e, "duration", 0.0))
        ]

    def get_effects_in_range(self, start: float, end: float) -> List[Any]:
        return [
            e for e in self.effects
            if getattr(e, "start_time", 0.0) < end and (getattr(e, "start_time", 0.0) + getattr(e, "duration", 0.0)) > start
        ]


@dataclass
class Timeline:
    """Composite multitrack timeline for video production."""
    video_track: VideoTrack = field(default_factory=VideoTrack)
    audio_track: Optional[AudioTrack] = None
    subtitle_track: Optional[SubtitleTrack] = None
    effect_track: EffectTrack = field(default_factory=EffectTrack)
    duration: float = 0.0
    width: int = 1080
    height: int = 1920
    fps: int = 30

    def get_active_shot(self, timestamp: float) -> Optional[CutPoint]:
        return self.video_track.get_cut_at(timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration": round(self.duration, 3),
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps,
            "cuts_count": len(self.video_track.cuts),
            "cuts": [c.to_dict() for c in self.video_track.cuts],
            "audio_track": self.audio_track.audio_path if self.audio_track else None,
            "subtitle_track": self.subtitle_track.ass_path if self.subtitle_track else None,
            "effects_count": len(self.effect_track.effects)
        }


class CutScheduler:
    """
    Directorial camera switch scheduler aligned to musical rhythm.
    Schedules camera switches (Close-up, Medium, B-Roll) aligned to 4-bar or 8-bar
    boundaries and minimum duration rules.
    """

    DEFAULT_ROTATION: List[ShotType] = [
        ShotType.CLOSE_UP,
        ShotType.MEDIUM,
        ShotType.CLOSE_UP,
        ShotType.B_ROLL
    ]

    def __init__(
        self,
        bpm: float = 130.0,
        bar_interval: int = 4,
        min_cut_duration: float = 0.8,
        shot_rotation: Optional[List[ShotType]] = None
    ):
        self.bpm = max(40.0, bpm)
        self.bar_interval = max(1, bar_interval)
        self.min_cut_duration = max(0.2, min_cut_duration)
        self.shot_rotation = shot_rotation or list(self.DEFAULT_ROTATION)

    def calculate_bar_duration(self, bpm: Optional[float] = None, beats_per_bar: int = 4) -> float:
        effective_bpm = bpm or self.bpm
        return (60.0 / effective_bpm) * beats_per_bar

    def schedule_cuts(
        self,
        total_duration: float,
        bars: Optional[List[Any]] = None,
        bpm: Optional[float] = None,
        bar_interval: Optional[int] = None
    ) -> List[CutPoint]:
        """
        Schedule shot transitions aligned to bar boundaries.

        Args:
            total_duration: Total target video duration in seconds.
            bars: Optional list of Bar objects (with start_time, end_time, etc.).
            bpm: Optional BPM override.
            bar_interval: Number of bars per cut (e.g. 4 or 8 bars).
        """
        if total_duration <= 0:
            return []

        effective_bpm = bpm or self.bpm
        interval = bar_interval or self.bar_interval

        cut_points: List[CutPoint] = []
        rotation_idx = 0

        # Case 1: Provided explicit bar definitions
        if bars and len(bars) > 0:
            i = 0
            while i < len(bars):
                start_bar = bars[i]
                start_time = getattr(start_bar, "start_time", 0.0)
                if isinstance(start_bar, dict):
                    start_time = start_bar.get("start_time", 0.0)

                end_idx = min(i + interval, len(bars))
                end_bar = bars[end_idx - 1]
                end_time = getattr(end_bar, "end_time", start_time + 1.0)
                if isinstance(end_bar, dict):
                    end_time = end_bar.get("end_time", start_time + 1.0)

                # Advance to next chunk
                i = end_idx

                # If this is the final cut, stretch to total_duration
                if i >= len(bars):
                    end_time = max(end_time, total_duration)

                # Enforce minimum duration rule by extending or merging
                if cut_points and (end_time - start_time) < self.min_cut_duration:
                    cut_points[-1].end_time = max(cut_points[-1].end_time, end_time)
                    continue

                shot = self.shot_rotation[rotation_idx % len(self.shot_rotation)]
                rotation_idx += 1

                cut_points.append(
                    CutPoint(
                        start_time=round(start_time, 3),
                        end_time=round(end_time, 3),
                        shot_type=shot,
                        scene_id=f"scene_{len(cut_points) + 1:03d}",
                        description=f"Auto-cut {shot.value} bar {len(cut_points) * interval}"
                    )
                )

        # Case 2: Procedural bar calculation from BPM
        else:
            bar_duration = self.calculate_bar_duration(effective_bpm)
            chunk_duration = bar_duration * interval

            # Ensure chunk duration adheres to minimum cut duration
            if chunk_duration < self.min_cut_duration:
                # Scale up bar interval to meet minimum duration
                multiplier = int((self.min_cut_duration / bar_duration) + 0.999)
                chunk_duration = bar_duration * max(1, multiplier)

            curr_time = 0.0
            while curr_time < total_duration:
                next_time = min(curr_time + chunk_duration, total_duration)

                # Check if final fragment violates min_cut_duration
                remaining_after = total_duration - next_time
                if 0 < remaining_after < self.min_cut_duration:
                    # Merge remaining into this cut
                    next_time = total_duration

                # If current cut itself is too short and we have a previous cut, merge
                if (next_time - curr_time) < self.min_cut_duration and cut_points:
                    cut_points[-1].end_time = round(next_time, 3)
                    break

                shot = self.shot_rotation[rotation_idx % len(self.shot_rotation)]
                rotation_idx += 1

                cut_points.append(
                    CutPoint(
                        start_time=round(curr_time, 3),
                        end_time=round(next_time, 3),
                        shot_type=shot,
                        scene_id=f"scene_{len(cut_points) + 1:03d}",
                        description=f"Scheduled {shot.value} cut"
                    )
                )
                curr_time = next_time

        return cut_points


class TimelineDirector:
    """
    High-level director orchestrating video cuts, audio tracks,
    subtitles, and beat-synced visual effects.
    """

    def __init__(
        self,
        min_cut_duration: float = 0.8,
        default_bar_interval: int = 4,
        fps: int = 30,
        width: int = 1080,
        height: int = 1920
    ):
        self.min_cut_duration = min_cut_duration
        self.default_bar_interval = default_bar_interval
        self.fps = fps
        self.width = width
        self.height = height
        self.scheduler = CutScheduler(
            min_cut_duration=min_cut_duration,
            bar_interval=default_bar_interval
        )

    def plan_timeline(
        self,
        bars: Optional[List[Any]] = None,
        beat_grid: Optional[Any] = None,
        total_duration: Optional[float] = None,
        bpm: float = 130.0,
        audio_path: Optional[str] = None,
        ass_subtitle_path: Optional[str] = None
    ) -> Timeline:
        """
        Synthesize multi-track Timeline from musical and lyrical cues.
        """
        # Determine duration
        duration = total_duration
        if duration is None or duration <= 0:
            if bars and len(bars) > 0:
                last_bar = bars[-1]
                duration = getattr(last_bar, "end_time", 10.0)
                if isinstance(last_bar, dict):
                    duration = last_bar.get("end_time", 10.0)
            elif beat_grid and hasattr(beat_grid, "duration"):
                duration = beat_grid.duration
            else:
                duration = 10.0  # Default fallback duration

        # Schedule cuts
        cuts = self.scheduler.schedule_cuts(
            total_duration=duration,
            bars=bars,
            bpm=bpm,
            bar_interval=self.default_bar_interval
        )

        video_track = VideoTrack(cuts=cuts)

        # Build audio track
        audio_track = AudioTrack(
            audio_path=audio_path,
            duration=duration,
            bpm=bpm
        )

        # Build subtitle track
        subtitle_track = SubtitleTrack(ass_path=ass_subtitle_path)

        # Schedule beat effects
        from airap.director.beat_effects import BeatEffectScheduler
        effect_scheduler = BeatEffectScheduler()
        effects = effect_scheduler.schedule_beat_effects(
            bpm=bpm,
            duration=duration,
            beat_grid=beat_grid
        )
        effect_track = EffectTrack(effects=effects)

        return Timeline(
            video_track=video_track,
            audio_track=audio_track,
            subtitle_track=subtitle_track,
            effect_track=effect_track,
            duration=round(duration, 3),
            width=self.width,
            height=self.height,
            fps=self.fps
        )
