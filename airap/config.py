"""Configuration schemas and data contracts for AIRap engine."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class VideoConfig:
    width: int = 1080
    height: int = 1920  # Default 9:16 vertical short format
    fps: int = 30
    crf: int = 18
    preset: str = "fast"
    bitrate: str = "8M"


@dataclass
class BeatGridConfig:
    bpm: float = 130.0
    time_signature: Tuple[int, int] = (4, 4)
    min_cut_duration: float = 0.8  # Minimum seconds between scene transitions
    shake_intensity: float = 0.05
    zoom_scale: float = 1.05


@dataclass
class StyleConfig:
    theme: str = "cyberpunk_street"
    primary_color: str = "&H00FFFF00"  # Yellow in ASS format
    highlight_color: str = "&H000000FF"  # Red / Bright highlight
    font_name: str = "Arial Black"
    font_size: int = 48
    enable_rhyme_highlight: bool = True
    enable_impact_shake: bool = True
    enable_glitch_transitions: bool = True


@dataclass
class ProjectConfig:
    project_name: str = "rap_session_001"
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    video: VideoConfig = field(default_factory=VideoConfig)
    beat: BeatGridConfig = field(default_factory=BeatGridConfig)
    style: StyleConfig = field(default_factory=StyleConfig)

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir
