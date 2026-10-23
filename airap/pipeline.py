"""Local procedural preview orchestration; no AI vocals or avatar rendering."""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from airap.config import ProjectConfig

MAX_LYRICS_BYTES = 64 * 1024
MAX_PREVIEW_SECONDS = 120.0


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
    """Compose procedural placeholders, audio and optional burned subtitles."""

    def __init__(self, config: Optional[ProjectConfig] = None):
        self.config = config or ProjectConfig()
        # Defer writes until the entire request has passed validation.
        self.output_dir = Path(self.config.output_dir)

    def run(self, request: RapVideoGenerationRequest) -> RapVideoGenerationResult:
        """Create a local procedural preview, never an AI performance video."""
        audio_file = self._validate_request(request)
        # The compositor does not apply the requested theme to its visuals.
        self.config.beat.bpm = request.bpm
        if request.aspect_ratio == "16:9":
            self.config.video.width = 1920
            self.config.video.height = 1080
        else:
            self.config.video.width = 1080
            self.config.video.height = 1920

        # Lazy imports of fully integrated modules
        from airap.lyrics.bar_scheduler import BarScheduler, split_into_bars
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
        scheduler = BarScheduler(bpm=request.bpm)
        raw_lines = split_into_bars(request.lyrics_text, target_bars=None)
        if not raw_lines:
            raise ValueError("Lyrics must contain at least one non-header bar")
        # Check the duration budget before expensive planning or generated assets.
        if len(raw_lines) * scheduler.bar_duration > MAX_PREVIEW_SECONDS:
            raise ValueError("Local procedural previews are limited to 120 seconds; shorten the lyrics")
        flow_analyzer = FlowAnalyzer(default_bpm=request.bpm)
        cadence_info = flow_analyzer.analyze_verse(raw_lines, bpm=request.bpm)
        bars = scheduler.schedule(raw_lines, target_bars=None)
        total_duration = bars[-1].end_time
        if not math.isfinite(total_duration) or not 0 < total_duration <= MAX_PREVIEW_SECONDS:
            raise ValueError("Local procedural previews require a finite duration up to 120 seconds")

        # Each run owns its generated assets; supplied media is never replaced.
        self.output_dir = self.config.ensure_output_dir()
        asset_dir = Path(tempfile.mkdtemp(prefix="preview-assets-", dir=self.output_dir))

        # Step 2: Use supplied audio, or synthesize an instrumental beat only.
        audio_source = "provided_audio" if audio_file is not None else "synthetic_beat"
        if audio_file is None:
            beat_gen = SyntheticRapBeatGenerator(sample_rate=44100)
            audio_file = str(asset_dir / "generated_beat.wav")
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

        # Step 3: Planning-only avatar states; these never reach the compositor
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
        ass_path = str(asset_dir / "rap_lyrics.ass")
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
                "theme": None,
                "requested_theme": request.theme,
                "theme_applied": False,
                "render_kind": "procedural_preview",
                "is_generated_ai_video": False,
                "visual_source": "procedural_placeholder",
                "audio_source": audio_source,
                "vocals_generated": False,
                "lipsync_rendered": False,
                "character_image_used": False,
                "lyrics_truncated": False,
                "subtitles_burned": getattr(render_result, "subtitles_burned", False),
                "duration_verified": getattr(render_result, "duration_verified", False),
                "requested_duration": getattr(render_result, "requested_duration", total_duration),
                "error": getattr(render_result, "error_message", None),
                "audio_path": audio_file,
                "subtitle_path": ass_path,
                "avatar_frames": 0,
                "planned_avatar_states": len(avatar_timeline),
                "avatar_states_are_planning_data": True,
                "cuts_count": len(timeline.video_track.cuts),
                "effects_count": len(timeline.effect_track.effects)
            }
        )

    def _validate_request(self, request: RapVideoGenerationRequest) -> Optional[str]:
        """Reject ignored or invalid inputs before generating any files."""
        if not isinstance(request, RapVideoGenerationRequest):
            raise ValueError("Expected a RapVideoGenerationRequest")
        if not isinstance(request.lyrics_text, str) or not request.lyrics_text.strip():
            raise ValueError("Lyrics must be nonempty text")
        try:
            lyrics_size = len(request.lyrics_text.encode("utf-8"))
        except UnicodeError:
            raise ValueError("Lyrics must be valid UTF-8 text") from None
        if lyrics_size > MAX_LYRICS_BYTES:
            raise ValueError("Lyrics exceed the 64 KiB UTF-8 limit")
        try:
            valid_bpm = type(request.bpm) in (int, float) and math.isfinite(request.bpm) and 40 <= request.bpm <= 300
        except OverflowError:
            valid_bpm = False
        if not valid_bpm:
            raise ValueError("BPM must be a finite number between 40 and 300")
        if request.aspect_ratio not in ("9:16", "16:9"):
            raise ValueError("Aspect ratio must be 9:16 or 16:9")
        filename = request.output_filename
        if not isinstance(filename, str) or not filename or any(c in filename for c in ("/", "\\", ":")):
            raise ValueError("Output filename must be an MP4 basename")
        try:
            valid_filename = (len(filename.encode("utf-8")) <= 255 and
                              not any(ord(c) < 32 or ord(c) == 127 for c in filename) and
                              Path(filename).suffix.lower() == ".mp4" and
                              Path(filename).stem not in ("", ".", ".."))
        except (ValueError, UnicodeError):
            valid_filename = False
        if not valid_filename:
            raise ValueError("Output filename must be an MP4 basename")
        if not isinstance(request.theme, str) or len(request.theme) > 256:
            raise ValueError("Requested theme must be text up to 256 characters")
        try:
            request.theme.encode("utf-8")
        except UnicodeError:
            raise ValueError("Requested theme must be valid UTF-8 text") from None
        if request.character_image_path is not None:
            raise ValueError("Character images are unsupported: this preview has no image renderer")
        if request.audio_path is None:
            return None
        try:
            if not isinstance(request.audio_path, (str, os.PathLike)) or not os.fspath(request.audio_path):
                raise ValueError()
            audio = Path(request.audio_path).resolve(strict=True)
            if not audio.is_file():
                raise ValueError()
            with audio.open("rb") as stream:
                stream.read(1)
            target = (self.output_dir / filename).resolve()
            if target == audio or (target.exists() and target.samefile(audio)):
                raise ValueError("Output must not overwrite supplied audio")
        except (OSError, TypeError, ValueError, RuntimeError):
            raise ValueError("Supplied audio must be a readable local file distinct from the output") from None
        return str(audio)
