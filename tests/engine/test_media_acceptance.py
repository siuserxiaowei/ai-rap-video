"""Local composition acceptance: adverse probes and small real FFmpeg files."""
import copy
import os
from pathlib import Path
import re

import pytest

from airap.compositor.video_builder import RenderResult, VideoBuilder
from airap.config import VideoConfig
from airap.director.timeline import AudioTrack, CutPoint, ShotType, SubtitleTrack, Timeline


def metadata(duration='1.0', fps='24/1'):
    return {'streams': [
        {'codec_type': 'video', 'width': 160, 'height': 90,
         'avg_frame_rate': fps, 'duration': duration},
        {'codec_type': 'audio', 'codec_name': 'aac'}], 'format': {'duration': '99'}}


def stub_builder(monkeypatch, tmp_path, probe=None, fps=24):
    builder = VideoBuilder(VideoConfig(width=160, height=90, fps=fps, preset='ultrafast'))
    calls = []
    def generate(**kwargs):
        Path(kwargs['output_path']).write_bytes(b'scratch input')
        return kwargs['output_path']
    def run(cmd, **kwargs):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b'verified candidate')
    monkeypatch.setattr(builder.synthetic_gen, 'generate_shot_clip', generate)
    monkeypatch.setattr(builder.synthetic_gen, 'generate_audio_clip', generate)
    monkeypatch.setattr(builder.pipeline, 'run_command', run)
    monkeypatch.setattr(builder.pipeline, 'has_filter', lambda name: False)
    monkeypatch.setattr(builder.pipeline, 'probe_file', lambda path: copy.deepcopy(probe if probe is not None else metadata()))
    return builder, calls


def test_accepted_output_uses_measured_duration_and_replaces_only_after_probe(monkeypatch, tmp_path):
    output = tmp_path / 'final.mp4'
    output.write_bytes(b'previous accepted output')
    builder, calls = stub_builder(monkeypatch, tmp_path)
    def probe(path):
        assert output.read_bytes() == b'previous accepted output'
        assert Path(path).parent.parent == output.parent
        assert Path(path) != output
        return metadata('0.96')
    monkeypatch.setattr(builder.pipeline, 'probe_file', probe)
    result = builder.build_video(Timeline(duration=1), output_path=str(output))
    assert result.success and result.duration_verified
    assert result.duration == 0.96
    assert result.requested_duration == 1.0
    assert result.subtitles_burned is False
    assert result.output_path == str(output)
    assert result.file_size_bytes == len(b'verified candidate')
    assert output.read_bytes() == b'verified candidate'
    assert calls[-1][-1] != str(output)
    assert not list(tmp_path.glob('.airap_render_*'))


def invalid_probes():
    cases = [{}, {'streams': []}, {'streams': [{'codec_type': 'audio'}]}]
    for field, value in [('duration', 'NaN'), ('duration', 'inf'), ('duration', '0'),
                         ('duration', '-1'), ('duration', '.5'), ('duration', '1.3'),
                         ('width', 159), ('height', 91), ('width', True),
                         ('avg_frame_rate', '23/1'), ('avg_frame_rate', '0/0'),
                         ('avg_frame_rate', 'NaN')]:
        item = metadata()
        item['streams'][0][field] = value
        cases.append(item)
    video_only = metadata()
    video_only['streams'].pop()
    cases.append(video_only)
    no_video_duration = metadata()
    del no_video_duration['streams'][0]['duration']
    cases.append(no_video_duration)  # Container duration cannot prove video duration.
    cover_only = metadata()
    cover_only['streams'][0]['disposition'] = {'attached_pic': 1}
    cases.append(cover_only)
    return cases


@pytest.mark.parametrize('probe', invalid_probes())
def test_bad_probe_cannot_clobber_previous_output(monkeypatch, tmp_path, probe):
    output = tmp_path / 'final.mp4'
    output.write_bytes(b'previous output')
    builder, _ = stub_builder(monkeypatch, tmp_path, probe)
    with pytest.raises(RuntimeError):
        builder.build_video(Timeline(duration=1), output_path=str(output))
    assert output.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.airap_render_*'))


@pytest.mark.parametrize(('measured', 'accepted'), [('0.81', True), ('0.79', False)])
def test_duration_tolerance_includes_two_frames_at_low_fps(monkeypatch, tmp_path, measured, accepted):
    builder, _ = stub_builder(monkeypatch, tmp_path, metadata(measured, '10/1'), fps=10)
    output = tmp_path / 'final.mp4'
    if accepted:
        assert builder.build_video(Timeline(duration=1), output_path=str(output)).duration_verified
    else:
        with pytest.raises(RuntimeError, match='duration'):
            builder.build_video(Timeline(duration=1), output_path=str(output))
        assert not output.exists()


def test_video_time_base_fallback_does_not_use_container_duration(monkeypatch, tmp_path):
    probe = metadata()
    video = probe['streams'][0]
    video.update(duration='N/A', duration_ts=25, time_base='1/24',
                 avg_frame_rate='0/0', r_frame_rate='24/1')
    builder, _ = stub_builder(monkeypatch, tmp_path, probe)
    result = builder.build_video(Timeline(duration=1), output_path=str(tmp_path / 'final.mp4'))
    assert result.duration == pytest.approx(25 / 24)


@pytest.mark.parametrize('stage', ['execution', 'missing', 'empty', 'replace'])
def test_render_and_atomic_replace_failures_preserve_previous_output(monkeypatch, tmp_path, stage):
    output = tmp_path / 'final.mp4'
    output.write_bytes(b'old')
    builder, _ = stub_builder(monkeypatch, tmp_path)
    def fail(cmd, **kwargs):
        if stage != 'missing':
            Path(cmd[-1]).write_bytes(b'partial' if stage == 'execution' else b'')
        if stage == 'execution':
            raise RuntimeError('FFmpeg failed')
    if stage == 'replace':
        def deny(*args):
            raise OSError('replace failed')
        monkeypatch.setattr(os, 'replace', deny)
    else:
        monkeypatch.setattr(builder.pipeline, 'run_command', fail)
    with pytest.raises((RuntimeError, OSError)):
        builder.build_video(Timeline(duration=1), output_path=str(output))
    assert output.read_bytes() == b'old'
    assert not list(tmp_path.glob('.airap_render_*'))


@pytest.mark.parametrize('kind', ['audio', 'timeline_audio', 'clip', 'subtitle', 'timeline_subtitle'])
def test_missing_explicit_media_never_falls_back(monkeypatch, tmp_path, kind):
    builder, calls = stub_builder(monkeypatch, tmp_path)
    timeline, kwargs = Timeline(duration=1), {}
    missing = str(tmp_path / 'missing.input')
    if kind == 'audio': kwargs['audio_path'] = missing
    elif kind == 'timeline_audio': timeline.audio_track = AudioTrack(audio_path=missing)
    elif kind == 'clip': timeline.video_track.cuts = [CutPoint(0, 1, ShotType.CLOSE_UP, source_clip=missing)]
    elif kind == 'subtitle': kwargs.update(ass_subtitle_path=missing, burn_subtitles=False)
    else: timeline.subtitle_track = SubtitleTrack(ass_path=missing)
    with pytest.raises(FileNotFoundError):
        builder.build_video(timeline, output_path=str(tmp_path / 'final.mp4'), **kwargs)
    assert calls == []
    assert not list(tmp_path.glob('.airap_render_*'))


@pytest.mark.parametrize('kind', ['audio', 'clip', 'subtitle', 'hardlink', 'symlink'])
def test_never_overwrite_input_including_aliases(monkeypatch, tmp_path, kind):
    builder, calls = stub_builder(monkeypatch, tmp_path)
    source = tmp_path / 'input.mp4'
    source.write_bytes(b'original input')
    target = source
    timeline, kwargs = Timeline(duration=1), {}
    if kind == 'clip': timeline.video_track.cuts = [CutPoint(0, 1, ShotType.CLOSE_UP, source_clip=str(source))]
    elif kind == 'subtitle': kwargs.update(ass_subtitle_path=str(source), burn_subtitles=False)
    else:
        kwargs['audio_path'] = str(source)
        if kind in ('hardlink', 'symlink'):
            target = tmp_path / 'alias.mp4'
            os.link(source, target) if kind == 'hardlink' else target.symlink_to(source)
    with pytest.raises(ValueError, match='overwrite'):
        builder.build_video(timeline, output_path=str(target), **kwargs)
    assert source.read_bytes() == b'original input'
    assert target.read_bytes() == b'original input'
    assert calls == []


def test_ass_capability_and_actual_graph_are_reported(monkeypatch, tmp_path):
    ass = tmp_path / 'lyrics.ass'
    ass.write_text('[Script Info]\n', encoding='utf-8')
    builder, _ = stub_builder(monkeypatch, tmp_path)
    output = str(tmp_path / 'final.mp4')
    with pytest.raises(RuntimeError, match='ASS'):
        builder.build_video(Timeline(duration=1), ass_subtitle_path=str(ass), output_path=output, burn_subtitles=True)
    automatic = builder.build_video(Timeline(duration=1), ass_subtitle_path=str(ass), output_path=output)
    assert not automatic.subtitles_burned
    assert 'ass=filename' not in automatic.filter_graph
    monkeypatch.setattr(builder.pipeline, 'has_filter', lambda name: True)
    included = builder.build_video(Timeline(duration=1), ass_subtitle_path=str(ass), output_path=output, burn_subtitles=True)
    assert included.subtitles_burned
    assert 'ass=filename' in included.filter_graph
    with pytest.raises(ValueError, match='ASS'):
        builder.build_video(Timeline(duration=1), output_path=output, burn_subtitles=True)


@pytest.mark.parametrize('duration', [0, -1, True, float('nan'), float('inf')])
def test_invalid_requested_duration_is_not_silently_substituted(monkeypatch, tmp_path, duration):
    builder, calls = stub_builder(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        builder.build_video(Timeline(duration=1), duration=duration, output_path=str(tmp_path / 'final.mp4'))
    assert calls == []


def test_render_result_new_fields_are_backward_compatible_defaults():
    result = RenderResult(True, 'old.mp4', 1, 10, '', [], 1)
    assert result.requested_duration is None
    assert result.duration_verified is False
    assert result.subtitles_burned is False


def test_shot_labels_cannot_choose_scratch_file_paths(monkeypatch, tmp_path):
    builder, _ = stub_builder(monkeypatch, tmp_path)
    paths = []
    def generate(**kwargs):
        path = Path(kwargs['output_path'])
        assert path.name == 'shot_000.mp4'
        assert path.parent.name.startswith('.airap_render_')
        assert path.parent.parent == tmp_path
        paths.append(path)
        path.write_bytes(b'procedural input')
    monkeypatch.setattr(builder.synthetic_gen, 'generate_shot_clip', generate)
    timeline = Timeline(duration=1)
    timeline.video_track.cuts = [CutPoint(0, 1, '../../outside')]
    assert builder.build_video(timeline, output_path=str(tmp_path / 'final.mp4')).success
    assert len(paths) == 1


def test_small_real_ffmpeg_output_is_probed_and_fully_decodes(tmp_path):
    builder = VideoBuilder(VideoConfig(width=160, height=90, fps=24, preset='ultrafast', crf=30))
    output = tmp_path / 'real.mp4'
    result = builder.build_video(Timeline(duration=.7), output_path=str(output),
                                 burn_subtitles=False, enable_effects=False)
    probe = builder.pipeline.probe_file(str(output))
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    assert any(s['codec_type'] == 'audio' for s in probe['streams'])
    assert (video['width'], video['height'], video['avg_frame_rate']) == (160, 90, '24/1')
    assert result.duration == float(video['duration'])
    assert abs(result.duration - .7) <= max(.1, 2 / 24)
    assert result.requested_duration == .7 and result.duration_verified
    assert not result.subtitles_burned
    builder.pipeline.run_command(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'null', '-'])
    assert not list(tmp_path.glob('.airap_render_*'))


def test_real_short_input_is_rejected_without_clobbering_old_output(tmp_path):
    builder = VideoBuilder(VideoConfig(width=160, height=90, fps=24, preset='ultrafast', crf=30))
    clip = tmp_path / 'short.mp4'
    builder.synthetic_gen.generate_shot_clip(str(clip), ShotType.CLOSE_UP, .25, width=160, height=90, fps=24)
    timeline = Timeline(duration=1)
    timeline.video_track.cuts = [CutPoint(0, 1, ShotType.CLOSE_UP, source_clip=str(clip))]
    output = tmp_path / 'previous.mp4'
    output.write_bytes(b'previous output')
    with pytest.raises(RuntimeError, match='duration'):
        builder.build_video(timeline, output_path=str(output), enable_effects=False)
    assert output.read_bytes() == b'previous output'
    assert not list(tmp_path.glob('.airap_render_*'))


@pytest.mark.parametrize('colors', [('red', 'blue'), ('blue', 'red')])
def test_real_long_sources_are_cut_at_the_timeline_boundary_in_order(tmp_path, colors):
    builder = VideoBuilder(VideoConfig(width=160, height=90, fps=24, preset='ultrafast', crf=30))
    sources = []
    for index, color in enumerate(colors):
        source = tmp_path / f'source_{index}.mp4'
        builder.synthetic_gen.generate_clip(str(source), duration=1.5 + index * .25,
                                            width=160, height=90, fps=24,
                                            pattern_type='color', color=color)
        sources.append(source)
    timeline = Timeline(duration=1)
    timeline.video_track.cuts = [
        CutPoint(0, .25, ShotType.CLOSE_UP, source_clip=str(sources[0])),
        CutPoint(.25, 1, ShotType.MEDIUM, source_clip=str(sources[1])),
    ]
    output = tmp_path / 'ordered.mp4'
    result = builder.build_video(timeline, output_path=str(output), enable_effects=False)
    assert result.duration_verified and result.duration == pytest.approx(1.0)
    # Decode all frames and inspect numeric chroma statistics, without creating
    # screenshots or trusting the command string / total duration alone.
    decoded = builder.pipeline.run_command([
        'ffmpeg', '-v', 'error', '-i', str(output), '-an',
        '-vf', 'signalstats,metadata=mode=print:file=-', '-f', 'null', '-'])
    frames = []
    for line in decoded.stdout.splitlines():
        if line.startswith('frame:'):
            frames.append({'time': float(re.search(r'pts_time:([0-9.]+)', line).group(1))})
        elif line.startswith('lavfi.signalstats.UAVG='):
            frames[-1]['u'] = float(line.split('=', 1)[1])
        elif line.startswith('lavfi.signalstats.VAVG='):
            frames[-1]['v'] = float(line.split('=', 1)[1])
    assert len(frames) == 24
    assert frames[6]['time'] == pytest.approx(.25)
    measured_colors = ['red' if f['v'] - f['u'] > 70 else
                       'blue' if f['u'] - f['v'] > 70 else 'unexpected' for f in frames]
    assert measured_colors == [colors[0]] * 6 + [colors[1]] * 18
