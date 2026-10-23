"""FFmpeg command generator, execution wrapper, filter graph builder, and synthetic generator."""

import json
import logging
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class FFmpegExecutionError(RuntimeError):
    """Raised when an FFmpeg execution fails."""

    def __init__(self, cmd: List[str], returncode: int, stdout: str, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        msg = f"FFmpeg command failed with returncode {returncode}.\nCommand: {' '.join(cmd)}\nStderr:\n{stderr[-1000:]}"
        super().__init__(msg)


class FFmpegPipeline:
    """Wrapper and command executor for FFmpeg and FFprobe binaries."""

    def __init__(self, ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or self._find_binary("ffmpeg")
        self.ffprobe_path = ffprobe_path or self._find_binary("ffprobe")
        self._available_filters: Optional[Set[str]] = None

    @staticmethod
    def _find_binary(name: str) -> str:
        # Check standard PATH first
        found = shutil.which(name)
        if found:
            return found
        # Common macOS Homebrew / system paths
        candidates = [
            f"/opt/homebrew/bin/{name}",
            f"/usr/local/bin/{name}",
            f"/usr/bin/{name}"
        ]
        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        return name

    def is_available(self) -> bool:
        """Check if FFmpeg binary is available and executable."""
        try:
            res = subprocess.run(
                [self.ffmpeg_path, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return res.returncode == 0
        except (FileNotFoundError, PermissionError):
            return False

    def get_available_filters(self) -> Set[str]:
        """Query and cache list of filters supported by the current FFmpeg build."""
        if self._available_filters is not None:
            return self._available_filters

        filters: Set[str] = set()
        if not self.is_available():
            self._available_filters = filters
            return filters

        try:
            res = subprocess.run(
                [self.ffmpeg_path, "-filters"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            # Lines look like: " ... scale             V->V       Scale the input video size..."
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] in ("..", "TS", "T.", ".S", "T..", "..."):
                    filter_name = parts[1]
                    filters.add(filter_name)
        except Exception as e:
            logger.warning("Failed to query ffmpeg filters: %s", e)

        self._available_filters = filters
        return filters

    def has_filter(self, filter_name: str) -> bool:
        """Check whether a specific filter is compiled into FFmpeg."""
        return filter_name in self.get_available_filters()

    def run_command(
        self,
        cmd: List[str],
        timeout: float = 180.0,
        check: bool = True
    ) -> subprocess.CompletedProcess:
        """Execute FFmpeg command synchronously with timeout and error capture."""
        full_cmd = [self.ffmpeg_path if cmd[0] in ("ffmpeg", "") else cmd[0]] + cmd[1:]
        res = subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False
        )
        if check and res.returncode != 0:
            raise FFmpegExecutionError(full_cmd, res.returncode, res.stdout, res.stderr)
        return res

    def probe_file(self, file_path: str) -> Dict[str, Any]:
        """Probe media file metadata using ffprobe."""
        if not os.path.exists(file_path):
            return {}
        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode == 0 and res.stdout:
                return json.loads(res.stdout)
        except Exception as e:
            logger.warning("ffprobe probe failed for %s: %s", file_path, e)
        return {}


@dataclass
class FilterGraphResult:
    filter_complex: str
    final_video_label: str
    input_count: int
    has_subtitles: bool = False
    has_effects: bool = False


class FilterGraphBuilder:
    """
    High-performance filter graph builder for video composition.
    Handles aspect ratio fitting (scale + crop for 9:16 vertical or 16:9 horizontal),
    concatenation, beat-synced visual effects, and ASS subtitle burn-in.
    """

    def __init__(
        self,
        target_width: int = 1080,
        target_height: int = 1920,
        fps: int = 30
    ):
        self.target_width = target_width
        self.target_height = target_height
        self.fps = fps

    def build_prep_filter(self, input_idx: int, out_label: str) -> str:
        """
        Normalize input clip:
        - Scale to fill target bounds (force_original_aspect_ratio=increase)
        - Center-crop to exact target dimensions
        - Set sample aspect ratio to 1:1 and frame rate to target FPS
        """
        return (
            f"[{input_idx}:v]scale={self.target_width}:{self.target_height}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={self.target_width}:{self.target_height},"
            f"setsar=1,fps={self.fps}[{out_label}]"
        )

    def build_concat_filter(self, input_labels: List[str], out_label: str = "v_concat") -> str:
        """Concatenate normalized video streams."""
        n = len(input_labels)
        joined_inputs = "".join(f"[{lbl}]" for lbl in input_labels)
        return f"{joined_inputs}concat=n={n}:v=1:a=0[{out_label}]"

    @staticmethod
    def escape_filter_path(file_path: str) -> str:
        """Escape path for FFmpeg filter argument syntax."""
        p = str(Path(file_path).resolve())
        # Replace backslashes with forward slashes
        p = p.replace("\\", "/")
        # Escape colons, single quotes, brackets
        p = p.replace(":", "\\:").replace("'", "\\'")
        return p

    def build_ass_filter(self, in_label: str, ass_path: str, out_label: str = "v_sub") -> str:
        """Generate ASS subtitle burn-in filter."""
        escaped_path = self.escape_filter_path(ass_path)
        return f"[{in_label}]ass=filename='{escaped_path}'[{out_label}]"

    def build_effects_filter(
        self,
        in_label: str,
        effects: List[Any],
        out_label: str = "v_eff",
        max_effects: int = 16
    ) -> Tuple[List[str], str]:
        """
        Generate filter chain for beat effects (ZoomPulse, ShakeEffect, FlashGlitch).
        Uses each effect's get_ffmpeg_filter implementation.
        """
        if not effects:
            return [], in_label

        filter_chains: List[str] = []
        curr_label = in_label

        # Cap excessive chains to keep filtergraph lean and fast
        active_effects = effects
        if len(effects) > max_effects:
            from airap.director.beat_effects import BeatEffectType
            glitches = [
                e for e in effects
                if getattr(e, "effect_type", None) in (BeatEffectType.FLASH_GLITCH, "flash_glitch")
            ]
            shakes = [
                e for e in effects
                if getattr(e, "effect_type", None) in (BeatEffectType.SHAKE, "shake")
            ]
            others = [e for e in effects if e not in glitches and e not in shakes]
            remaining_quota = max(0, max_effects - len(glitches) - len(shakes))
            step = max(1, len(others) // remaining_quota) if remaining_quota > 0 and others else 1
            sampled_others = others[::step][:remaining_quota]
            active_effects = sorted(
                glitches + shakes + sampled_others,
                key=lambda e: getattr(e, "start_time", 0.0)
            )

        for idx, eff in enumerate(active_effects):
            next_label = f"veff_{idx}" if idx < len(active_effects) - 1 else out_label
            if hasattr(eff, "get_ffmpeg_filter"):
                filter_str = eff.get_ffmpeg_filter(self.target_width, self.target_height, self.fps)
            else:
                filter_str = "null"

            chain = f"[{curr_label}]{filter_str}[{next_label}]"
            filter_chains.append(chain)
            curr_label = next_label

        return filter_chains, curr_label

    def build_full_graph(
        self,
        clip_count: int,
        ass_path: Optional[str] = None,
        effects: Optional[List[Any]] = None,
        burn_subtitles: bool = True
    ) -> FilterGraphResult:
        """
        Assemble the complete complex filter graph string.
        1. Normalizes all clip inputs to target dimensions and aspect ratio
        2. Concatenates them into a unified video stream
        3. Applies beat-synchronized visual effects
        4. Burns in ASS kinetic subtitles if requested
        """
        if clip_count <= 0:
            raise ValueError("clip_count must be at least 1")

        graph_parts: List[str] = []

        # 1. Input normalization
        prep_labels: List[str] = []
        for i in range(clip_count):
            lbl = f"v_prep_{i}"
            graph_parts.append(self.build_prep_filter(i, lbl))
            prep_labels.append(lbl)

        # 2. Concat
        if clip_count > 1:
            concat_label = "v_concat"
            graph_parts.append(self.build_concat_filter(prep_labels, concat_label))
            current_label = concat_label
        else:
            current_label = prep_labels[0]

        # 3. Beat effects
        has_effects = False
        if effects:
            eff_chains, current_label = self.build_effects_filter(
                in_label=current_label,
                effects=effects,
                out_label="v_effects"
            )
            if eff_chains:
                graph_parts.extend(eff_chains)
                has_effects = True

        # 4. ASS subtitles
        has_subtitles = False
        if burn_subtitles and ass_path:
            sub_label = "v_sub"
            graph_parts.append(self.build_ass_filter(current_label, ass_path, sub_label))
            current_label = sub_label
            has_subtitles = True

        filter_complex_str = ";\n".join(graph_parts)
        return FilterGraphResult(
            filter_complex=filter_complex_str,
            final_video_label=current_label,
            input_count=clip_count,
            has_subtitles=has_subtitles,
            has_effects=has_effects
        )


class SyntheticPatternGenerator:
    """
    Generates synthetic solid, gradient, and animated test pattern video clips
    using FFmpeg lavfi source filters (testsrc2, color, smptebars, etc.)
    allowing the pipeline and tests to run autonomously without external media files.
    """

    def __init__(self, pipeline: Optional[FFmpegPipeline] = None):
        self.pipeline = pipeline or FFmpegPipeline()

    def generate_clip(
        self,
        output_path: str,
        duration: float,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        pattern_type: str = "testsrc2",
        color: str = "black"
    ) -> str:
        """
        Generate a synthetic video clip.

        Args:
            output_path: Path where MP4 file should be written.
            duration: Clip length in seconds.
            width: Video width.
            height: Video height.
            fps: Frame rate.
            pattern_type: "testsrc2", "color", "smptebars", or "rgbtestsrc".
            color: Hex or color name when using pattern_type="color".
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        dur_str = f"{max(0.1, duration):.3f}"

        if pattern_type == "color":
            lavfi_input = f"color=c={color}:s={width}x{height}:r={fps}:d={dur_str}"
        elif pattern_type in ("smptebars", "rgbtestsrc", "testsrc2", "testsrc"):
            lavfi_input = f"{pattern_type}=size={width}x{height}:rate={fps}:duration={dur_str}"
        else:
            lavfi_input = f"testsrc2=size={width}x{height}:rate={fps}:duration={dur_str}"

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", lavfi_input,
            "-t", dur_str,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(out_p)
        ]

        self.pipeline.run_command(cmd)
        return str(out_p)

    def generate_shot_clip(
        self,
        output_path: str,
        shot_type: Any,
        duration: float,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30
    ) -> str:
        """
        Generate visually distinct synthetic clips corresponding to rap shot framing:
        - Close-up: Punchy warm cyberpunk neon / magenta tone
        - Medium: Electric cyan / deep blue hip-hop aesthetic
        - B-Roll: Dynamic moving pattern with SMPTE / animated testsrc2
        """
        st = shot_type.value if hasattr(shot_type, "value") else str(shot_type).lower()

        if "close" in st:
            # Magenta / dark violent purple background with color styling
            return self.generate_clip(
                output_path=output_path,
                duration=duration,
                width=width,
                height=height,
                fps=fps,
                pattern_type="color",
                color="0x28063b"
            )
        elif "medium" in st:
            # Cyan / deep teal
            return self.generate_clip(
                output_path=output_path,
                duration=duration,
                width=width,
                height=height,
                fps=fps,
                pattern_type="color",
                color="0x002b3d"
            )
        else:
            # B-Roll / default: dynamic animated testsrc2
            return self.generate_clip(
                output_path=output_path,
                duration=duration,
                width=width,
                height=height,
                fps=fps,
                pattern_type="testsrc2"
            )

    def generate_audio_clip(
        self,
        output_path: str,
        duration: float,
        bpm: float = 130.0,
        sample_rate: int = 44100
    ) -> str:
        """
        Generate synthetic rhythmic beat WAV file using FFmpeg audio synthesizer
        (combining low frequency kick-like pulses with high snare click).
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        dur_str = f"{max(0.1, duration):.3f}"
        beat_interval = 60.0 / max(40.0, bpm)

        # Generate a pulse tone with audio synthesizer in FFmpeg
        # aevalsrc creates a repeating beat kick (60Hz tone burst every beat)
        audio_expr = (
            f"0.4*sin(2*PI*65*t)*pow(max(0,1-mod(t,{beat_interval})*8),3) + "
            f"0.15*(2*random(0)-1)*pow(max(0,1-mod(t+{beat_interval}/2,{beat_interval})*12),4)"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"aevalsrc='{audio_expr}':s={sample_rate}:d={dur_str}",
            "-t", dur_str,
            "-c:a", "pcm_s16le",
            str(out_p)
        ]

        self.pipeline.run_command(cmd)
        return str(out_p)
