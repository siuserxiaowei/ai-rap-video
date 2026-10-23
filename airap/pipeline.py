"""Main Pipeline Orchestrator for AIRapStudio."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from airap.config import ProjectConfig


@dataclass
class RapVideoGenerationRequest:
    lyrics_text: str
    bpm: float = 130.0
    theme: str = "cyberpunk_street"
    audio_path: Optional[str] = None
    character_image_path: Optional[str] = None
    output_filename: str = "final_rap_mv.mp4"
    aspect_ratio: str = "9:16"  # "9:16" or "16:9"


@dataclass
class RapVideoGenerationResult:
    success: bool
    output_video_path: str
    duration_seconds: float
    total_bars: int
    bpm: float
    metadata: Dict[str, Any]


class RapPipelineOrchestrator:
    """End-to-end pipeline orchestrating lyrics, audio, avatar, subtitles, and composition."""

    def __init__(self, config: Optional[ProjectConfig] = None):
        self.config = config or ProjectConfig()
        self.output_dir = self.config.ensure_output_dir()

    def run(self, request: RapVideoGenerationRequest) -> RapVideoGenerationResult:
        """Execute the end-to-end AI Rap Video generation."""
        # 1. Update config from request
        self.config.beat.bpm = request.bpm
        self.config.style.theme = request.theme
        if request.aspect_ratio == "16:9":
            self.config.video.width = 1920
            self.config.video.height = 1080
        else:
            self.config.video.width = 1080
            self.config.video.height = 1920

        # Lazy import of modules after worktree merges
        from airap.lyrics.bar_scheduler import BarScheduler
        from airap.lyrics.flow_analyzer import FlowAnalyzer
        from airap.audio.beat_detector import BeatGridGenerator, SyntheticBeatGenerator
        from airap.audio.vocal_aligner import VocalAligner
        from airap.avatar.lipsync_engine import MockLipSyncRenderer
        from airap.subtitles.kinetic_builder import KineticSubtitleBuilder
        from airap.subtitles.ass_exporter import AssExporter
        from airap.director.timeline import TimelineDirector
        from airap.compositor.video_builder import VideoBuilder

        # Step 1: Lyrics & Flow Analysis
        flow_analyzer = FlowAnalyzer()
        cadence_info = flow_analyzer.analyze_flow(request.lyrics_text)

        scheduler = BarScheduler(bpm=request.bpm)
        bars = scheduler.schedule_lyrics(request.lyrics_text)
        total_duration = bars[-1].end_time if bars else 10.0

        # Step 2: Audio & Beat Track
        audio_file = request.audio_path
        if not audio_file or not os.path.exists(audio_file):
            beat_gen = SyntheticBeatGenerator(sample_rate=44100)
            audio_file = str(self.output_dir / "generated_beat.wav")
            beat_gen.generate_rap_beat_wav(
                output_path=audio_file,
                bpm=request.bpm,
                duration_seconds=total_duration
            )

        beat_grid_gen = BeatGridGenerator(bpm=request.bpm)
        beat_grid = beat_grid_gen.generate_grid(duration_seconds=total_duration)

        vocal_aligner = VocalAligner()
        word_intervals = vocal_aligner.align_lyrics(bars)

        # Step 3: Avatar & Lip-Sync Mock/Engine
        lipsync = MockLipSyncRenderer(fps=self.config.video.fps)
        avatar_frames = lipsync.render_sequence(word_intervals, total_duration)

        # Step 4: Kinetic Subtitles
        subtitle_builder = KineticSubtitleBuilder()
        kinetic_lines = subtitle_builder.build_lines(bars)
        ass_exporter = AssExporter(
            width=self.config.video.width,
            height=self.config.video.height,
            font_size=self.config.style.font_size
        )
        ass_path = str(self.output_dir / "rap_lyrics.ass")
        ass_exporter.export(kinetic_lines, ass_path)

        # Step 5: Director & Timeline
        director = TimelineDirector(min_cut_duration=self.config.beat.min_cut_duration)
        timeline = director.plan_timeline(bars, beat_grid, total_duration)

        # Step 6: Final Compositor Rendering
        target_video = str(self.output_dir / request.output_filename)
        builder = VideoBuilder(config=self.config.video)
        builder.build_video(
            timeline=timeline,
            audio_path=audio_file,
            ass_subtitle_path=ass_path,
            output_path=target_video,
            duration=total_duration
        )

        return RapVideoGenerationResult(
            success=True,
            output_video_path=target_video,
            duration_seconds=total_duration,
            total_bars=len(bars),
            bpm=request.bpm,
            metadata={
                "cadence": cadence_info,
                "aspect_ratio": request.aspect_ratio,
                "theme": request.theme,
                "audio_path": audio_file,
                "subtitle_path": ass_path
            }
        )
