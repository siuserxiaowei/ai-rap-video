"""LipSync Engine and adapter abstractions for AIRapStudio.

Provides:
- FrameAvatarState: Frame-level avatar state containing lip, head motion, and eye blink values.
- LipSyncEngine: Abstract base class for facial animation engines.
- LivePortraitAdapter: Retargeting and driving parameter adapter for LivePortrait.
- HedraAdapter: Timeline and expression payload adapter for Hedra API.
- Wav2LipAdapter: Mouth ROI and blending mask adapter for Wav2Lip.
- MockLipSyncRenderer: Fully deterministic renderer for tests, headless CI, and pipeline simulation.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from airap.avatar.head_motion import BlinkGenerator, HeadBobber
from airap.avatar.phoneme_viseme import (
    CoArticulationFilter,
    PhonemeVisemeMapper,
    TimedPhoneme,
    Viseme,
)


@dataclass
class FrameAvatarState:
    """Complete facial and head pose state for an avatar at a single frame."""
    timestamp: float
    viseme: Viseme
    mouth_open: float  # [0.0, 1.0]
    mouth_wide: float  # [0.0, 1.0]
    head_pitch: float  # degrees (positive = downward nod, negative = raised)
    head_yaw: float    # degrees (positive = right, negative = left)
    head_roll: float   # degrees (positive = right tilt)
    blink: float       # [0.0, 1.0] (0.0 = open, 1.0 = fully closed)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to standard dictionary."""
        return {
            "timestamp": round(self.timestamp, 4),
            "viseme": self.viseme.value if isinstance(self.viseme, Viseme) else str(self.viseme),
            "mouth_open": round(self.mouth_open, 4),
            "mouth_wide": round(self.mouth_wide, 4),
            "head_pitch": round(self.head_pitch, 4),
            "head_yaw": round(self.head_yaw, 4),
            "head_roll": round(self.head_roll, 4),
            "blink": round(self.blink, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FrameAvatarState:
        """Construct state from dictionary."""
        return cls(
            timestamp=float(data["timestamp"]),
            viseme=Viseme(data["viseme"]),
            mouth_open=float(data["mouth_open"]),
            mouth_wide=float(data["mouth_wide"]),
            head_pitch=float(data["head_pitch"]),
            head_yaw=float(data["head_yaw"]),
            head_roll=float(data["head_roll"]),
            blink=float(data["blink"]),
        )


class LipSyncEngine(ABC):
    """Abstract interface for lip-sync and facial motion generation."""

    @abstractmethod
    def generate_states(
        self,
        audio_duration: float,
        phonemes: Sequence[TimedPhoneme],
        bpm: float = 130.0,
        fps: int = 30,
    ) -> List[FrameAvatarState]:
        """Generate per-frame avatar animation states for given phoneme sequence."""
        pass

    @abstractmethod
    def render(
        self,
        states: Sequence[FrameAvatarState],
        audio_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Render or export animation data."""
        pass


class LivePortraitAdapter:
    """Adapter for LivePortrait motion driving and facial expression retargeting."""

    def __init__(self, source_image: Optional[str] = None):
        self.source_image = source_image

    def prepare_payload(
        self,
        states: Sequence[FrameAvatarState],
        source_image: Optional[str] = None,
        driving_audio: Optional[str] = None,
        fps: int = 30,
    ) -> Dict[str, Any]:
        """Convert FrameAvatarState sequence into LivePortrait driving vectors."""
        image = source_image or self.source_image
        pitch_seq = [s.head_pitch for s in states]
        yaw_seq = [s.head_yaw for s in states]
        roll_seq = [s.head_roll for s in states]

        mouth_open_seq = [s.mouth_open for s in states]
        mouth_wide_seq = [s.mouth_wide for s in states]
        blink_seq = [s.blink for s in states]

        return {
            "engine": "live_portrait",
            "source_image": image,
            "driving_audio": driving_audio,
            "fps": fps,
            "n_frames": len(states),
            "head_motion": {
                "pitch": pitch_seq,
                "yaw": yaw_seq,
                "roll": roll_seq,
            },
            "retargeting": {
                "lip_open": mouth_open_seq,
                "lip_wide": mouth_wide_seq,
                "eye_blink": blink_seq,
            },
        }


class HedraAdapter:
    """Adapter for Hedra AI character video animation API."""

    def __init__(self, default_character_id: str = "avatar_rapper_01"):
        self.default_character_id = default_character_id

    def prepare_payload(
        self,
        states: Sequence[FrameAvatarState],
        audio_url: Optional[str] = None,
        character_id: Optional[str] = None,
        aspect_ratio: str = "9:16",
    ) -> Dict[str, Any]:
        """Convert FrameAvatarState sequence into Hedra animation request payload."""
        cid = character_id or self.default_character_id
        duration = states[-1].timestamp if states else 0.0

        # Sample keyframes every 3 frames for efficient API payload delivery
        keyframes = [
            {
                "time": s.timestamp,
                "viseme": s.viseme.value,
                "mouth_open": s.mouth_open,
                "head_nod": s.head_pitch,
                "blink": s.blink,
            }
            for i, s in enumerate(states)
            if i % 3 == 0 or i == len(states) - 1
        ]

        return {
            "engine": "hedra",
            "character_id": cid,
            "aspect_ratio": aspect_ratio,
            "audio_url": audio_url,
            "duration": round(duration, 3),
            "total_frames": len(states),
            "timeline_keyframes": keyframes,
        }


class Wav2LipAdapter:
    """Adapter for Wav2Lip mouth ROI warping and blending."""

    def __init__(self, mouth_padding: float = 0.15):
        self.mouth_padding = mouth_padding

    def prepare_payload(
        self,
        states: Sequence[FrameAvatarState],
        face_video_path: Optional[str] = None,
        audio_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert FrameAvatarState sequence into Wav2Lip frame blending guidance."""
        # Calculate dynamic mouth bbox scaling based on mouth_open and mouth_wide
        blending_weights = [
            round(0.5 + 0.5 * s.mouth_open, 4) for s in states
        ]
        roi_scales = [
            round(1.0 + self.mouth_padding * max(s.mouth_open, s.mouth_wide), 4)
            for s in states
        ]

        return {
            "engine": "wav2lip",
            "face_video": face_video_path,
            "audio_path": audio_path,
            "frame_count": len(states),
            "blending_weights": blending_weights,
            "roi_scales": roi_scales,
        }


class MockLipSyncRenderer(LipSyncEngine):
    """Deterministic mock avatar renderer for headless testing and validation.

    Generates reproducible animation state tracks, summary statistics,
    and optional JSON manifests without requiring GPU or external cloud APIs.
    """

    def __init__(
        self,
        mapper: Optional[PhonemeVisemeMapper] = None,
        filter_: Optional[CoArticulationFilter] = None,
        seed: int = 42,
    ):
        self.mapper = mapper or PhonemeVisemeMapper()
        self.filter = filter_ or CoArticulationFilter()
        self.seed = seed

    def generate_states(
        self,
        audio_duration: float,
        phonemes: Sequence[TimedPhoneme],
        bpm: float = 130.0,
        fps: int = 30,
    ) -> List[FrameAvatarState]:
        """Generate smooth deterministic FrameAvatarState timeline."""
        if audio_duration <= 0:
            return []

        frame_count = max(1, int(round(audio_duration * fps)))
        dt = 1.0 / fps

        # 1. Map phonemes to timed visemes
        timed_visemes = self.mapper.map_timed_phonemes(phonemes)

        # 2. Smooth mouth shapes with CoArticulationFilter
        mouth_frames = self.filter.filter_timed_visemes(
            timed_visemes=timed_visemes,
            total_duration=audio_duration,
            fps=fps,
            bpm=bpm,
        )

        # 3. Generate beat-synced rap head bobbing
        bobber = HeadBobber(bpm=bpm)
        head_frames = bobber.generate_timeline(duration=audio_duration, fps=fps)

        # 4. Generate Poisson eye-blinks
        blinker = BlinkGenerator(seed=self.seed)
        blink_frames = blinker.generate_timeline(duration=audio_duration, fps=fps)

        # 5. Assemble unified FrameAvatarState per frame
        states: List[FrameAvatarState] = []
        for i in range(frame_count):
            t = round(i * dt, 4)
            m_open, m_wide, vis = mouth_frames[i]
            head = head_frames[i]
            blink = blink_frames[i]

            states.append(
                FrameAvatarState(
                    timestamp=t,
                    viseme=vis,
                    mouth_open=round(m_open, 4),
                    mouth_wide=round(m_wide, 4),
                    head_pitch=round(head.pitch, 4),
                    head_yaw=round(head.yaw, 4),
                    head_roll=round(head.roll, 4),
                    blink=round(blink, 4),
                )
            )

        return states

    def render(
        self,
        states: Sequence[FrameAvatarState],
        audio_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute deterministic mock rendering and generate audit summary."""
        if not states:
            return {
                "status": "empty",
                "frame_count": 0,
                "duration": 0.0,
            }

        duration = states[-1].timestamp
        frame_count = len(states)

        # Calculate statistics
        total_open = sum(s.mouth_open for s in states)
        avg_open = total_open / frame_count
        max_open = max(s.mouth_open for s in states)

        # Compute max delta (velocity) between adjacent frames
        max_velocity = 0.0
        for i in range(1, frame_count):
            delta = abs(states[i].mouth_open - states[i - 1].mouth_open)
            if delta > max_velocity:
                max_velocity = delta

        # Pitch extremes
        min_pitch = min(s.head_pitch for s in states)
        max_pitch = max(s.head_pitch for s in states)

        # Blink count (frames with blink > 0.5)
        blink_frames = sum(1 for s in states if s.blink > 0.5)

        # Viseme distribution
        viseme_counts: Dict[str, int] = {}
        for s in states:
            v_name = s.viseme.value if isinstance(s.viseme, Viseme) else str(s.viseme)
            viseme_counts[v_name] = viseme_counts.get(v_name, 0) + 1

        result: Dict[str, Any] = {
            "status": "success",
            "engine": "mock_lip_sync_renderer",
            "frame_count": frame_count,
            "duration": round(duration, 4),
            "audio_path": audio_path,
            "metrics": {
                "avg_mouth_open": round(avg_open, 4),
                "max_mouth_open": round(max_open, 4),
                "max_frame_delta": round(max_velocity, 4),
                "pitch_range": (round(min_pitch, 2), round(max_pitch, 2)),
                "active_blink_frames": blink_frames,
                "viseme_counts": viseme_counts,
            },
        }

        # If output_path is provided, write manifest JSON
        if output_path:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "meta": result,
                "frames": [s.to_dict() for s in states],
            }
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            result["output_file"] = str(out_file)

        return result
