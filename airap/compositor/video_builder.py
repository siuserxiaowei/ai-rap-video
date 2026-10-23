"""End-to-end composite runner for AIRapStudio video generation."""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from airap.config import VideoConfig
from airap.director.timeline import CutPoint, ShotType, Timeline
from airap.compositor.ffmpeg_pipeline import (
    FFmpegExecutionError,
    FFmpegPipeline,
    FilterGraphBuilder,
    FilterGraphResult,
    SyntheticPatternGenerator,
)

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """Detailed outcome of video composition rendering."""
    success: bool
    output_path: str
    duration: float
    file_size_bytes: int
    filter_graph: str
    ffmpeg_command: List[str]
    cuts_count: int
    error_message: Optional[str] = None


class VideoBuilder:
    """
    End-to-end video composition engine.
    Orchestrates cut assembly, synthetic shot generation, audio synchronization,
    beat visual effects, and ASS subtitle burn-in via FFmpeg.
    """

    def __init__(
        self,
        config: Optional[VideoConfig] = None,
        ffmpeg_bin: Optional[str] = None
    ):
        self.config = config or VideoConfig()
        self.pipeline = FFmpegPipeline(ffmpeg_path=ffmpeg_bin)
        self.synthetic_gen = SyntheticPatternGenerator(pipeline=self.pipeline)

    def build_video(
        self,
        timeline: Timeline,
        audio_path: Optional[str] = None,
        ass_subtitle_path: Optional[str] = None,
        output_path: str = "output.mp4",
        duration: Optional[float] = None,
        burn_subtitles: Optional[bool] = None,
        enable_effects: bool = True
    ) -> RenderResult:
        """
        Render final MP4 video from multi-track timeline.

        Args:
            timeline: Timeline object containing VideoTrack, AudioTrack, EffectTrack, etc.
            audio_path: Optional path to master audio file.
            ass_subtitle_path: Optional path to ASS subtitle file.
            output_path: Target output .mp4 file path.
            duration: Video duration override.
            burn_subtitles: Whether to burn in ASS subtitles (auto-detects filter capability if None).
            enable_effects: Whether to include beat-driven visual impact effects.

        Returns:
            RenderResult containing output status, size, and metadata.
        """
        target_path = Path(output_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        width = getattr(self.config, "width", 1080)
        height = getattr(self.config, "height", 1920)
        fps = getattr(self.config, "fps", 30)
        preset = getattr(self.config, "preset", "fast")
        crf = getattr(self.config, "crf", 18)
        bitrate = getattr(self.config, "bitrate", "8M")

        # 1. Determine final target duration
        target_duration = duration
        if target_duration is None or target_duration <= 0:
            if timeline.duration > 0:
                target_duration = timeline.duration
            elif timeline.video_track.total_duration() > 0:
                target_duration = timeline.video_track.total_duration()
            else:
                target_duration = 10.0

        target_duration = round(target_duration, 3)

        # 2. Ensure VideoTrack has cuts
        cuts = list(timeline.video_track.cuts)
        if not cuts:
            # Procedural fallback cut
            cuts = [
                CutPoint(
                    start_time=0.0,
                    end_time=target_duration,
                    shot_type=ShotType.CLOSE_UP,
                    scene_id="scene_001"
                )
            ]

        # Use a temporary scratch directory for generated synthetic media
        temp_dir = tempfile.mkdtemp(prefix="airap_render_")
        temp_paths_to_clean: List[str] = [temp_dir]

        try:
            # 3. Resolve or generate clip for each cut
            clip_inputs: List[str] = []
            for idx, cut in enumerate(cuts):
                cut_duration = max(0.1, cut.duration)
                if cut.source_clip and os.path.exists(cut.source_clip):
                    clip_inputs.append(str(Path(cut.source_clip).resolve()))
                else:
                    # Generate placeholder visual corresponding to shot framing
                    gen_path = os.path.join(temp_dir, f"shot_{idx:03d}_{cut.shot_type}.mp4")
                    self.synthetic_gen.generate_shot_clip(
                        output_path=gen_path,
                        shot_type=cut.shot_type,
                        duration=cut_duration,
                        width=width,
                        height=height,
                        fps=fps
                    )
                    clip_inputs.append(gen_path)

            # 4. Resolve or generate master audio
            effective_audio = audio_path
            if not effective_audio and timeline.audio_track and timeline.audio_track.audio_path:
                effective_audio = timeline.audio_track.audio_path

            if not effective_audio or not os.path.exists(effective_audio):
                bpm = 130.0
                if timeline.audio_track and timeline.audio_track.bpm:
                    bpm = timeline.audio_track.bpm
                gen_audio_path = os.path.join(temp_dir, "synthetic_beat.wav")
                self.synthetic_gen.generate_audio_clip(
                    output_path=gen_audio_path,
                    duration=target_duration,
                    bpm=bpm
                )
                effective_audio = gen_audio_path

            # 5. Resolve subtitles and burning capability
            effective_ass = ass_subtitle_path
            if not effective_ass and timeline.subtitle_track and timeline.subtitle_track.ass_path:
                effective_ass = timeline.subtitle_track.ass_path

            has_ass_filter = self.pipeline.has_filter("ass")
            should_burn_subtitles = False

            if effective_ass and os.path.exists(effective_ass):
                if burn_subtitles is True:
                    should_burn_subtitles = True
                elif burn_subtitles is None:
                    # Auto-detect: burn if ffmpeg supports 'ass' filter
                    should_burn_subtitles = has_ass_filter
                    if not has_ass_filter:
                        logger.info(
                            "FFmpeg does not support 'ass' filter in this environment; "
                            "subtitles will not be burned in."
                        )

            # 6. Build filter graph
            effects = timeline.effect_track.effects if enable_effects else []
            graph_builder = FilterGraphBuilder(
                target_width=width,
                target_height=height,
                fps=fps
            )
            fg_result = graph_builder.build_full_graph(
                clip_count=len(clip_inputs),
                ass_path=effective_ass if should_burn_subtitles else None,
                effects=effects,
                burn_subtitles=should_burn_subtitles
            )

            # 7. Assemble FFmpeg execution command
            cmd: List[str] = ["ffmpeg", "-y"]

            # Video inputs
            for clip_p in clip_inputs:
                cmd.extend(["-i", clip_p])

            # Audio input
            audio_idx = len(clip_inputs)
            cmd.extend(["-i", effective_audio])

            # Complex filter graph
            cmd.extend(["-filter_complex", fg_result.filter_complex])

            # Stream mappings
            cmd.extend(["-map", f"[{fg_result.final_video_label}]"])
            cmd.extend(["-map", f"{audio_idx}:a"])

            # Encoders & constraints
            cmd.extend([
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", str(crf),
                "-b:v", bitrate,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{target_duration:.3f}",
                "-shortest",
                str(target_path)
            ])

            # 8. Execute render
            self.pipeline.run_command(cmd, timeout=300.0)

            # 9. Verify and collect results
            if not target_path.exists():
                raise RuntimeError(f"Render failed: Output file was not created at {target_path}")

            file_size = target_path.stat().st_size
            if file_size == 0:
                raise RuntimeError(f"Render failed: Output file at {target_path} is 0 bytes")

            return RenderResult(
                success=True,
                output_path=str(target_path),
                duration=target_duration,
                file_size_bytes=file_size,
                filter_graph=fg_result.filter_complex,
                ffmpeg_command=cmd,
                cuts_count=len(cuts)
            )

        finally:
            # Clean up temporary scratch assets
            for p in temp_paths_to_clean:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                elif os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
