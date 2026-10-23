"""Main Pipeline Orchestrator for AIRapStudio."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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

        # Lazy imports of fully integrated modules
        from airap.lyrics.bar_scheduler import BarScheduler
        from airap.lyrics.flow_analyzer import FlowAnalyzer
        from airap.audio.beat_detector import SyntheticRapBeatGenerator, generate_beat_grid
        from airap.audio.vocal_aligner import RuleBasedAligner
        from airap.avatar.lipsync_engine import MockLipSyncRenderer
        from airap.avatar.phoneme_viseme import TimedPhoneme
        from airap.subtitles.kinetic_builder import KineticSubtitleBuilder, WordHighlight
        from airap.subtitles.ass_exporter import ASSExporter, AspectRatio
        from airap.director.timeline import TimelineDirector
        from airap.compositor.video_builder import VideoBuilder

        # Step 1: Lyrics & Flow Analysis
        flow_analyzer = FlowAnalyzer(default_bpm=request.bpm)
        raw_lines = [l.strip() for l in request.lyrics_text.strip().splitlines() if l.strip()]
        cadence_info = flow_analyzer.analyze_verse(raw_lines, bpm=request.bpm)

        scheduler = BarScheduler(bpm=request.bpm)
        bars = scheduler.schedule(request.lyrics_text)
        total_duration = bars[-1].end_time if bars else 8.0

        # Step 2: Audio & Beat Track
        audio_file = request.audio_path
        if not audio_file or not os.path.exists(audio_file):
            beat_gen = SyntheticRapBeatGenerator(sample_rate=44100)
            audio_file = str(self.output_dir / "generated_beat.wav")
            beat_gen.generate_wav(
                output_path=audio_file,
                bpm=request.bpm,
                duration=total_duration,
                pattern="trap"
            )

        beat_grid = generate_beat_grid(bpm=request.bpm, duration=total_duration)

        vocal_aligner = RuleBasedAligner()
        alignment_result = vocal_aligner.align(
            lyrics=request.lyrics_text,
            audio_duration=total_duration,
            beat_grid=beat_grid
        )

        # Step 3: Avatar & Lip-Sync Frame Engine
        timed_phonemes = [
            TimedPhoneme(phoneme=p.phoneme, start=p.start, end=p.end)
            for w in alignment_result.words
            for p in w.phonemes
        ]
        lipsync = MockLipSyncRenderer()
        avatar_timeline = lipsync.generate_states(
            audio_duration=total_duration,
            phonemes=timed_phonemes,
            bpm=request.bpm,
            fps=self.config.video.fps
        )

        # Step 4: Kinetic Subtitles Generation
        subtitle_builder = KineticSubtitleBuilder()
        for b in bars:
            words_for_line = []
            for w in b.words:
                words_for_line.append(
                    WordHighlight(
                        start_ms=int(w.start_time * 1000),
                        end_ms=int(w.end_time * 1000),
                        text=w.text,
                        is_rhyme=bool(b.rhyme_tag)
                    )
                )
            if words_for_line:
                subtitle_builder.create_line(
                    bar_index=b.index,
                    words=words_for_line,
                    start_time=b.start_time,
                    end_time=b.end_time,
                )

        target_ar = (
            AspectRatio.HORIZONTAL_16_9
            if request.aspect_ratio == "16:9"
            else AspectRatio.VERTICAL_9_16
        )
        ass_exporter = ASSExporter(
            aspect_ratio=target_ar,
            style_config=self.config.style
        )
        ass_path = str(self.output_dir / "rap_lyrics.ass")
        ass_exporter.export_to_file(subtitle_builder.lines, ass_path, aspect_ratio=target_ar)

        # Step 5: Director & Timeline
        director = TimelineDirector(
            width=self.config.video.width,
            height=self.config.video.height,
            fps=self.config.video.fps,
            min_cut_duration=self.config.beat.min_cut_duration
        )
        timeline = director.plan_timeline(
            bars=bars,
            beat_grid=beat_grid,
            total_duration=total_duration,
            bpm=request.bpm,
            audio_path=audio_file,
            ass_subtitle_path=ass_path
        )

        # Step 6: Final Compositor Rendering via FFmpeg
        target_video = str(self.output_dir / request.output_filename)
        builder = VideoBuilder(config=self.config.video)
        render_result = builder.build_video(
            timeline=timeline,
            audio_path=audio_file,
            ass_subtitle_path=ass_path,
            output_path=target_video,
            duration=total_duration
        )

        return RapVideoGenerationResult(
            success=render_result.success,
            output_video_path=render_result.output_path,
            duration_seconds=render_result.duration,
            total_bars=len(bars),
            bpm=request.bpm,
            metadata={
                "cadence": cadence_info.dominant_cadence,
                "aspect_ratio": request.aspect_ratio,
                "theme": request.theme,
                "audio_path": audio_file,
                "subtitle_path": ass_path,
                "avatar_frames": len(avatar_timeline),
                "cuts_count": len(timeline.video_track.cuts),
                "effects_count": len(timeline.effect_track.effects)
            }
        )
