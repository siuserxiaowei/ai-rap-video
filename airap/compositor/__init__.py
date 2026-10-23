"""AIRap Compositor Module: FFmpeg pipeline wrapper, filter graph generator, and video builder."""

from airap.compositor.ffmpeg_pipeline import (
    FFmpegExecutionError,
    FFmpegPipeline,
    FilterGraphBuilder,
    FilterGraphResult,
    SyntheticPatternGenerator,
)
from airap.compositor.video_builder import (
    RenderResult,
    VideoBuilder,
)

__all__ = [
    "FFmpegExecutionError",
    "FFmpegPipeline",
    "FilterGraphBuilder",
    "FilterGraphResult",
    "SyntheticPatternGenerator",
    "RenderResult",
    "VideoBuilder",
]
