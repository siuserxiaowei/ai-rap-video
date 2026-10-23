"""Tests for director timeline, beat effects, and FFmpeg video compositor."""

import os
import tempfile
from pathlib import Path
import pytest

from airap.config import VideoConfig
from airap.director.timeline import (
    CutPoint,
    CutScheduler,
    ShotType,
    Timeline,
    TimelineDirector,
    VideoTrack,
    AudioTrack,
    SubtitleTrack,
    EffectTrack,
)
from airap.director.beat_effects import (
    BeatEffectScheduler,
    BeatEffectType,
    FlashGlitch,
    ShakeEffect,
    ZoomPulse,
)
from airap.compositor.ffmpeg_pipeline import (
    FFmpegPipeline,
    FilterGraphBuilder,
    SyntheticPatternGenerator,
)
from airap.compositor.video_builder import VideoBuilder, RenderResult


class MockBar:
    """Mock Bar structure matching lyrics flow scheduler output."""
    def __init__(self, bar_index: int, start_time: float, end_time: float):
        self.bar_index = bar_index
        self.start_time = start_time
        self.end_time = end_time


class MockBeat:
    """Mock Beat point matching audio beat detector output."""
    def __init__(self, time: float, is_downbeat: bool = False, is_drop: bool = False, is_snare: bool = False):
        self.time = time
        self.is_downbeat = is_downbeat
        self.is_drop = is_drop
        self.is_snare = is_snare


class MockBeatGrid:
    """Mock BeatGrid container."""
    def __init__(self, beats, duration: float = 10.0):
        self.beats = beats
        self.duration = duration
        self.sections = []


# -------------------------------------------------------------------------
# Timeline & Track Tests
# -------------------------------------------------------------------------

def test_cut_point_duration_and_dict():
    cut = CutPoint(
        start_time=1.5,
        end_time=4.2,
        shot_type=ShotType.CLOSE_UP,
        scene_id="scene_001",
        description="MC verse 1"
    )
    assert round(cut.duration, 2) == 2.7
    d = cut.to_dict()
    assert d["start_time"] == 1.5
    assert d["end_time"] == 4.2
    assert d["duration"] == 2.7
    assert d["shot_type"] == "close_up"
    assert d["scene_id"] == "scene_001"


def test_video_track_add_and_query():
    vt = VideoTrack()
    cut1 = CutPoint(start_time=0.0, end_time=3.0, shot_type=ShotType.CLOSE_UP)
    cut2 = CutPoint(start_time=3.0, end_time=7.5, shot_type=ShotType.MEDIUM)
    cut3 = CutPoint(start_time=7.5, end_time=12.0, shot_type=ShotType.B_ROLL)

    # Add out of order to verify sorting
    vt.add_cut(cut2)
    vt.add_cut(cut1)
    vt.add_cut(cut3)

    assert len(vt.cuts) == 3
    assert vt.cuts[0].start_time == 0.0
    assert vt.cuts[1].start_time == 3.0
    assert vt.cuts[2].start_time == 7.5
    assert vt.total_duration() == 12.0
    assert vt.validate() is True

    # Query timestamp
    assert vt.get_cut_at(1.5) == cut1
    assert vt.get_cut_at(5.0) == cut2
    assert vt.get_cut_at(10.0) == cut3
    assert vt.get_cut_at(15.0) is None


def test_effect_track_range_query():
    et = EffectTrack()
    zp = ZoomPulse(start_time=1.0, duration=0.15)
    se = ShakeEffect(start_time=2.0, duration=0.30)
    fg = FlashGlitch(start_time=4.0, duration=0.10)

    et.add_effect(se)
    et.add_effect(zp)
    et.add_effect(fg)

    assert len(et.effects) == 3
    # Check sorting
    assert et.effects[0] == zp

    # Query active effects at specific timestamps
    active_at_1 = et.get_effects_at(1.05)
    assert len(active_at_1) == 1
    assert active_at_1[0] == zp

    # Query range
    in_range = et.get_effects_in_range(0.5, 2.5)
    assert len(in_range) == 2
    assert zp in in_range
    assert se in in_range
    assert fg not in in_range


def test_timeline_structure_and_dict():
    timeline = Timeline(duration=10.0, width=1080, height=1920, fps=30)
    cut = CutPoint(start_time=0.0, end_time=10.0, shot_type=ShotType.CLOSE_UP)
    timeline.video_track.add_cut(cut)
    timeline.audio_track = AudioTrack(audio_path="/tmp/audio.wav", duration=10.0, bpm=130.0)
    timeline.subtitle_track = SubtitleTrack(ass_path="/tmp/subs.ass")

    d = timeline.to_dict()
    assert d["duration"] == 10.0
    assert d["resolution"] == "1080x1920"
    assert d["fps"] == 30
    assert d["cuts_count"] == 1
    assert d["audio_track"] == "/tmp/audio.wav"
    assert d["subtitle_track"] == "/tmp/subs.ass"


# -------------------------------------------------------------------------
# Cut Scheduler Tests
# -------------------------------------------------------------------------

def test_cut_scheduler_4bar_alignment():
    # At 120 BPM:
    # 1 beat = 0.5s, 1 bar (4 beats) = 2.0s
    # 4 bars = 8.0s
    scheduler = CutScheduler(bpm=120.0, bar_interval=4, min_cut_duration=1.0)
    cuts = scheduler.schedule_cuts(total_duration=24.0)

    assert len(cuts) == 3
    assert cuts[0].start_time == 0.0
    assert cuts[0].end_time == 8.0
    assert cuts[1].start_time == 8.0
    assert cuts[1].end_time == 16.0
    assert cuts[2].start_time == 16.0
    assert cuts[2].end_time == 24.0

    # Verify shot rotation: CLOSE_UP -> MEDIUM -> CLOSE_UP -> B_ROLL
    assert cuts[0].shot_type == ShotType.CLOSE_UP
    assert cuts[1].shot_type == ShotType.MEDIUM
    assert cuts[2].shot_type == ShotType.CLOSE_UP


def test_cut_scheduler_8bar_alignment():
    # At 120 BPM: 8 bars = 16.0s
    scheduler = CutScheduler(bpm=120.0, bar_interval=8, min_cut_duration=1.0)
    cuts = scheduler.schedule_cuts(total_duration=32.0)

    assert len(cuts) == 2
    assert cuts[0].start_time == 0.0
    assert cuts[0].end_time == 16.0
    assert cuts[1].start_time == 16.0
    assert cuts[1].end_time == 32.0


def test_cut_scheduler_min_duration_rule():
    # Total duration is 9.0s with 8.0s chunks
    # Remaining 1.0s fragment should not create a sub-min cut if min_cut_duration=1.5s
    scheduler = CutScheduler(bpm=120.0, bar_interval=4, min_cut_duration=1.5)
    cuts = scheduler.schedule_cuts(total_duration=9.0)

    # The 1.0s remainder is merged into the previous cut so we get 1 cut of 9.0s
    assert len(cuts) == 1
    assert cuts[0].start_time == 0.0
    assert cuts[0].end_time == 9.0


def test_cut_scheduler_with_explicit_bars():
    # 8 bars of 2.0s each
    mock_bars = [MockBar(i, i * 2.0, (i + 1) * 2.0) for i in range(8)]
    scheduler = CutScheduler(min_cut_duration=1.0)
    cuts = scheduler.schedule_cuts(total_duration=16.0, bars=mock_bars, bar_interval=4)

    assert len(cuts) == 2
    assert cuts[0].start_time == 0.0
    assert cuts[0].end_time == 8.0
    assert cuts[1].start_time == 8.0
    assert cuts[1].end_time == 16.0


# -------------------------------------------------------------------------
# Beat Effects Tests
# -------------------------------------------------------------------------

def test_beat_effects_properties_and_filters():
    zp = ZoomPulse(start_time=1.0, duration=0.15, zoom_scale=1.08, intensity=1.0)
    assert zp.effect_type == BeatEffectType.ZOOM_PULSE
    assert zp.end_time == 1.15
    assert zp.is_active_at(1.05) is True
    assert zp.is_active_at(1.20) is False
    zp_filter = zp.get_ffmpeg_filter(width=1080, height=1920)
    assert "zoompan" in zp_filter
    assert "1080x1920" in zp_filter

    se = ShakeEffect(start_time=2.0, duration=0.3, amplitude_px=15.0)
    assert se.effect_type == BeatEffectType.SHAKE
    assert se.end_time == 2.3
    se_filter = se.get_ffmpeg_filter(width=1080, height=1920)
    assert "crop" in se_filter
    assert "scale=1080:1920" in se_filter
    assert "sin(" in se_filter

    fg = FlashGlitch(start_time=3.0, duration=0.12, flash_type="color_invert")
    assert fg.effect_type == BeatEffectType.FLASH_GLITCH
    fg_filter = fg.get_ffmpeg_filter()
    assert "negate" in fg_filter

    fg_white = FlashGlitch(start_time=3.0, duration=0.12, flash_type="white_flash")
    fg_white_filter = fg_white.get_ffmpeg_filter()
    assert "eq=brightness" in fg_white_filter


def test_beat_effect_scheduler_procedural():
    scheduler = BeatEffectScheduler()
    # At 120 BPM, bar = 2.0s. Over 8 seconds, 4 bars:
    # Beat 1 (downbeat) on bars 0, 1, 2, 3 -> ZoomPulse
    # Beat 3 on bars 0, 1, 2, 3 -> ZoomPulse
    effects = scheduler.schedule_beat_effects(bpm=120.0, duration=8.0)
    assert len(effects) > 0
    zoom_effects = [e for e in effects if e.effect_type == BeatEffectType.ZOOM_PULSE]
    assert len(zoom_effects) >= 4


def test_beat_effect_scheduler_from_grid():
    mock_beats = [
        MockBeat(time=0.0, is_downbeat=True),
        MockBeat(time=1.0, is_snare=True),
        MockBeat(time=2.0, is_downbeat=True, is_drop=True),
    ]
    grid = MockBeatGrid(beats=mock_beats, duration=4.0)
    scheduler = BeatEffectScheduler()
    effects = scheduler.schedule_beat_effects(bpm=120.0, duration=4.0, beat_grid=grid)

    assert any(e.effect_type == BeatEffectType.ZOOM_PULSE for e in effects)
    assert any(e.effect_type == BeatEffectType.SHAKE for e in effects)


# -------------------------------------------------------------------------
# Timeline Director Tests
# -------------------------------------------------------------------------

def test_timeline_director_plan():
    director = TimelineDirector(min_cut_duration=1.0, default_bar_interval=4)
    timeline = director.plan_timeline(total_duration=16.0, bpm=120.0)

    assert timeline.duration == 16.0
    assert len(timeline.video_track.cuts) == 2
    assert len(timeline.effect_track.effects) > 0
    assert timeline.video_track.cuts[0].duration == 8.0
    assert timeline.video_track.cuts[1].duration == 8.0


# -------------------------------------------------------------------------
# FFmpeg Pipeline & Filter Graph Builder Tests
# -------------------------------------------------------------------------

def test_ffmpeg_availability():
    pipe = FFmpegPipeline()
    assert pipe.is_available() is True
    filters = pipe.get_available_filters()
    assert len(filters) > 0
    assert "scale" in filters
    assert "crop" in filters


def test_filter_graph_builder_syntax():
    builder = FilterGraphBuilder(target_width=1080, target_height=1920, fps=30)
    effects = [
        ZoomPulse(start_time=1.0, duration=0.15),
        ShakeEffect(start_time=2.0, duration=0.25)
    ]
    fg = builder.build_full_graph(
        clip_count=3,
        ass_path="/tmp/test_lyrics.ass",
        effects=effects,
        burn_subtitles=True
    )

    assert fg.input_count == 3
    assert fg.has_subtitles is True
    assert fg.has_effects is True
    assert "scale=1080:1920" in fg.filter_complex
    assert "crop=1080:1920" in fg.filter_complex
    assert "concat=n=3:v=1:a=0" in fg.filter_complex
    assert "ass=filename=" in fg.filter_complex
    assert "/tmp/test_lyrics.ass" in fg.filter_complex
    assert fg.final_video_label == "v_sub"


def test_filter_graph_builder_16_9_aspect():
    builder = FilterGraphBuilder(target_width=1920, target_height=1080, fps=30)
    fg = builder.build_full_graph(clip_count=1, burn_subtitles=False)

    assert fg.input_count == 1
    assert "scale=1920:1080" in fg.filter_complex
    assert "crop=1920:1080" in fg.filter_complex
    assert fg.has_subtitles is False
    assert fg.final_video_label == "v_prep_0"


# -------------------------------------------------------------------------
# Synthetic Pattern Generator & End-to-End Compositor Tests
# -------------------------------------------------------------------------

def test_synthetic_pattern_generator(tmp_path):
    gen = SyntheticPatternGenerator()

    # Generate synthetic video clip
    clip_p = str(tmp_path / "syn_clip.mp4")
    gen.generate_clip(
        output_path=clip_p,
        duration=1.0,
        width=320,
        height=568,
        fps=24,
        pattern_type="testsrc2"
    )
    assert os.path.exists(clip_p)
    assert os.path.getsize(clip_p) > 0

    # Generate shot clip
    shot_p = str(tmp_path / "shot_close.mp4")
    gen.generate_shot_clip(
        output_path=shot_p,
        shot_type=ShotType.CLOSE_UP,
        duration=1.0,
        width=320,
        height=568,
        fps=24
    )
    assert os.path.exists(shot_p)
    assert os.path.getsize(shot_p) > 0

    # Generate synthetic audio clip
    audio_p = str(tmp_path / "syn_beat.wav")
    gen.generate_audio_clip(output_path=audio_p, duration=1.0, bpm=130.0)
    assert os.path.exists(audio_p)
    assert os.path.getsize(audio_p) > 0


def test_video_builder_end_to_end(tmp_path):
    # Setup director and timeline with multiple cuts
    director = TimelineDirector(min_cut_duration=0.5, default_bar_interval=1)
    timeline = director.plan_timeline(total_duration=2.0, bpm=130.0)

    output_file = str(tmp_path / "rendered_rap.mp4")
    cfg = VideoConfig(width=320, height=568, fps=24, preset="ultrafast", crf=26)
    builder = VideoBuilder(config=cfg)

    result = builder.build_video(
        timeline=timeline,
        output_path=output_file,
        duration=2.0,
        enable_effects=True
    )

    assert result.success is True
    assert os.path.exists(result.output_path)
    assert result.file_size_bytes > 0
    assert result.duration == 2.0
    assert result.cuts_count >= 1

    # Probe rendered output with FFmpegPipeline
    meta = builder.pipeline.probe_file(result.output_path)
    streams = meta.get("streams", [])
    assert len(streams) >= 2  # video and audio streams
    v_stream = next(s for s in streams if s.get("codec_type") == "video")
    a_stream = next(s for s in streams if s.get("codec_type") == "audio")

    assert v_stream["width"] == 320
    assert v_stream["height"] == 568
    assert a_stream["codec_name"] == "aac"


def test_video_builder_16_9_rendering(tmp_path):
    director = TimelineDirector(min_cut_duration=0.5, default_bar_interval=1)
    timeline = director.plan_timeline(total_duration=1.0, bpm=130.0)

    output_file = str(tmp_path / "rendered_16_9.mp4")
    cfg = VideoConfig(width=640, height=360, fps=24, preset="ultrafast")
    builder = VideoBuilder(config=cfg)

    result = builder.build_video(
        timeline=timeline,
        output_path=output_file,
        duration=1.0,
        enable_effects=False
    )

    assert result.success is True
    meta = builder.pipeline.probe_file(result.output_path)
    streams = meta.get("streams", [])
    v_stream = next(s for s in streams if s.get("codec_type") == "video")
    assert v_stream["width"] == 640
    assert v_stream["height"] == 360


def test_video_track_overlap_validation():
    vt = VideoTrack()
    cut1 = CutPoint(start_time=0.0, end_time=4.0, shot_type=ShotType.CLOSE_UP)
    cut2 = CutPoint(start_time=3.0, end_time=6.0, shot_type=ShotType.MEDIUM)  # Overlaps!
    vt.add_cut(cut1)
    vt.add_cut(cut2)

    assert vt.validate() is False


def test_ffmpeg_execution_error_handling():
    pipeline = FFmpegPipeline()
    with pytest.raises(Exception):
        pipeline.run_command(["ffmpeg", "-invalid_argument_xyz", "none"])


def test_filter_graph_builder_path_escaping():
    path_with_specials = "/User/test:folder/my'rap:subs.ass"
    escaped = FilterGraphBuilder.escape_filter_path(path_with_specials)
    assert "\\:" in escaped
    assert "\\'" in escaped
