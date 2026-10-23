"""End-to-end composite runner for AIRapStudio video generation."""

import logging
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional

from airap.config import VideoConfig
from airap.director.timeline import CutPoint, ShotType, Timeline
from airap.compositor.ffmpeg_pipeline import (
    FFmpegPipeline,
    FilterGraphBuilder,
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
    requested_duration: Optional[float] = None
    duration_verified: bool = False
    subtitles_burned: bool = False


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite positive number")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{field} must be a finite positive number") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a finite positive number")
    return number


def _readable_input(value: str, label: str, target: Path) -> str:
    source = Path(value).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Explicit {label} must be a readable local file")
    with source.open('rb') as stream:
        stream.read(1)
    if source == target or (target.exists() and os.path.samefile(source, target)):
        raise ValueError("Output must not overwrite any input file")
    return str(source)


def _probe_number(value: Any, field: str) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = float(Fraction(str(value)))
        if not math.isfinite(number) or number <= 0:
            raise ValueError()
        return number
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        raise RuntimeError(f"Output has no finite positive {field}") from None


def _verify_output(metadata: Dict[str, Any], width: int, height: int,
                   fps: float, requested_duration: float) -> float:
    streams = metadata.get('streams') if isinstance(metadata, dict) else None
    if not isinstance(streams, list):
        raise RuntimeError("Output could not be probed")
    videos = [s for s in streams if isinstance(s, dict) and s.get('codec_type') == 'video'
              and not s.get('disposition', {}).get('attached_pic')]
    audios = [s for s in streams if isinstance(s, dict) and s.get('codec_type') == 'audio']
    if not videos or not audios:
        raise RuntimeError("Output must contain both video and audio streams")
    video = videos[0]
    if (type(video.get('width')) is not int or type(video.get('height')) is not int
            or (video['width'], video['height']) != (width, height)):
        raise RuntimeError("Output video dimensions do not match the requested dimensions")
    rate = video.get('avg_frame_rate')
    if rate in (None, '', 'N/A', '0/0'):
        rate = video.get('r_frame_rate')
    measured_fps = _probe_number(rate, 'video FPS')
    if not math.isclose(measured_fps, fps, rel_tol=1e-4, abs_tol=1e-3):
        raise RuntimeError("Output video FPS does not match the requested FPS")
    duration = video.get('duration')
    if duration in (None, '', 'N/A'):
        # Derive from the video stream time base only, never container/audio duration.
        duration = (_probe_number(video.get('duration_ts'), 'video duration ticks')
                    * _probe_number(video.get('time_base'), 'video time base'))
    measured_duration = _probe_number(duration, 'video duration')
    tolerance = max(0.1, 2.0 / fps)
    if abs(measured_duration - requested_duration) > tolerance + 1e-9:
        raise RuntimeError("Output video duration does not match the requested duration")
    return measured_duration


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

        width = getattr(self.config, "width", 1080)
        height = getattr(self.config, "height", 1920)
        fps = getattr(self.config, "fps", 30)
        preset = getattr(self.config, "preset", "fast")
        crf = getattr(self.config, "crf", 18)
        bitrate = getattr(self.config, "bitrate", "8M")
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError("Video dimensions must be positive integers")
        fps = _positive_number(fps, 'FPS')
        if burn_subtitles is not None and type(burn_subtitles) is not bool:
            raise ValueError("burn_subtitles must be a boolean or None")

        # 1. Determine final target duration
        target_duration = duration
        if target_duration is None:
            if timeline.duration > 0:
                target_duration = timeline.duration
            elif timeline.video_track.total_duration() > 0:
                target_duration = timeline.video_track.total_duration()
            else:
                target_duration = 10.0

        target_duration = _positive_number(target_duration, 'Duration')

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

        # Resolve all explicit inputs before writing scratch media. Only absence
        # permits procedural fallback; missing supplied files are not absence.
        supplied_clips = {
            idx: _readable_input(cut.source_clip, 'video clip', target_path)
            for idx, cut in enumerate(cuts) if cut.source_clip is not None
        }
        effective_audio = audio_path
        if effective_audio is None and timeline.audio_track is not None:
            effective_audio = timeline.audio_track.audio_path
        if effective_audio is not None:
            effective_audio = _readable_input(effective_audio, 'audio', target_path)
        effective_ass = ass_subtitle_path
        if effective_ass is None and timeline.subtitle_track is not None:
            effective_ass = timeline.subtitle_track.ass_path
        if effective_ass is not None:
            effective_ass = _readable_input(effective_ass, 'subtitle', target_path)
        if burn_subtitles is True and effective_ass is None:
            raise ValueError("Explicit ASS subtitle burn requires a subtitle file")
        should_burn_subtitles = False
        if effective_ass is not None and burn_subtitles is not False:
            has_ass_filter = self.pipeline.has_filter('ass')
            if burn_subtitles is True and not has_ass_filter:
                raise RuntimeError("Explicit ASS subtitle burn is unsupported by this FFmpeg build")
            should_burn_subtitles = has_ass_filter
            if not should_burn_subtitles:
                logger.info("ASS filter unavailable; automatic subtitle burn omitted")

        # Same filesystem is required for atomic replacement of an accepted file.
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.mkdtemp(prefix=".airap_render_", dir=target_path.parent)
        staged_output = Path(temp_dir) / 'accepted.mp4'
        temp_paths_to_clean: List[str] = [temp_dir]

        try:
            # 3. Resolve or generate clip for each cut
            clip_inputs: List[str] = []
            for idx, cut in enumerate(cuts):
                cut_duration = max(0.1, cut.duration)
                if idx in supplied_clips:
                    clip_inputs.append(supplied_clips[idx])
                else:
                    # Generate placeholder visual corresponding to shot framing
                    gen_path = os.path.join(temp_dir, f"shot_{idx:03d}.mp4")
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
            if effective_audio is None:
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
                "-t", f"{target_duration:.6f}",
                "-shortest",
                str(staged_output)
            ])

            # 8. Execute render
            self.pipeline.run_command(cmd, timeout=300.0)

            # 9. Verify and collect results
            if not staged_output.is_file():
                raise RuntimeError("Render failed: Output file was not created")

            file_size = staged_output.stat().st_size
            if file_size == 0:
                raise RuntimeError("Render failed: Output file is empty")

            measured_duration = _verify_output(
                self.pipeline.probe_file(str(staged_output)), width, height, fps, target_duration)
            os.replace(staged_output, target_path)

            return RenderResult(
                success=True,
                output_path=str(target_path),
                duration=measured_duration,
                file_size_bytes=file_size,
                filter_graph=fg_result.filter_complex,
                ffmpeg_command=cmd,
                cuts_count=len(cuts),
                requested_duration=target_duration,
                duration_verified=True,
                subtitles_burned=bool(should_burn_subtitles and fg_result.has_subtitles)
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
