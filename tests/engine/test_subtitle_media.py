"""Filter discovery, explicit tools and opt-in real local ASS rendering."""
import json
import os
from pathlib import Path
import subprocess

import pytest

from airap.compositor.ffmpeg_pipeline import FFmpegPipeline
from airap.compositor.video_builder import VideoBuilder
from airap.config import VideoConfig
from airap.director.timeline import Timeline


def test_explicit_ffmpeg_and_ffprobe_are_forwarded_without_discovery(monkeypatch):
    def forbidden(name):
        raise AssertionError('Explicit references must not fall back to discovery')
    monkeypatch.setattr(FFmpegPipeline, '_find_binary', staticmethod(forbidden))
    builder = VideoBuilder(ffmpeg_bin='/tools/selected ffmpeg', ffprobe_bin='/tools/selected ffprobe')
    assert builder.pipeline.ffmpeg_path == '/tools/selected ffmpeg'
    assert builder.pipeline.ffprobe_path == '/tools/selected ffprobe'
    assert builder.synthetic_gen.pipeline is builder.pipeline


def test_none_keeps_legacy_discovery_and_explicit_paths_keep_whitespace(monkeypatch):
    discovered = []
    def find(name):
        discovered.append(name)
        return '/found/' + name
    monkeypatch.setattr(FFmpegPipeline, '_find_binary', staticmethod(find))
    defaults = VideoBuilder()
    assert (defaults.pipeline.ffmpeg_path, defaults.pipeline.ffprobe_path) == ('/found/ffmpeg', '/found/ffprobe')
    assert discovered == ['ffmpeg', 'ffprobe']
    explicit = FFmpegPipeline(ffmpeg_path='/tools/ 中文 ffmpeg ', ffprobe_path='/tools/probe')
    assert explicit.ffmpeg_path == '/tools/ 中文 ffmpeg '
    assert discovered == ['ffmpeg', 'ffprobe']


@pytest.mark.parametrize('field', ['ffmpeg_bin', 'ffprobe_bin'])
@pytest.mark.parametrize('value', ['', '   ', '\x00bad', 'bad\npath', 'bad\x7f', '\ud800', False, [], 'x' * 4097])
def test_explicit_empty_or_invalid_tool_references_do_not_fall_back(monkeypatch, field, value):
    monkeypatch.setattr(FFmpegPipeline, '_find_binary', staticmethod(lambda name: pytest.fail('Unexpected discovery')))
    values = {'ffmpeg_bin': '/explicit/ffmpeg', 'ffprobe_bin': '/explicit/ffprobe'}
    values[field] = value
    with pytest.raises(ValueError, match='Explicit'):
        VideoBuilder(**values)


def test_selected_tools_are_used_in_argv_without_a_shell(monkeypatch, tmp_path):
    calls = []
    def run(command, **kwargs):
        assert kwargs.get('shell', False) is False
        calls.append(command)
        stdout = json.dumps({'streams': []}) if command[0] == '/chosen/probe' else ''
        return subprocess.CompletedProcess(command, 0, stdout, '')
    monkeypatch.setattr(subprocess, 'run', run)
    pipe = FFmpegPipeline(ffmpeg_path='/chosen/render', ffprobe_path='/chosen/probe')
    pipe.run_command(['ffmpeg', '-version'])
    source = tmp_path / 'sample.mp4'
    source.write_bytes(b'local fixture')
    assert pipe.probe_file(str(source)) == {'streams': []}
    assert calls[0] == ['/chosen/render', '-version']
    assert calls[1][0] == '/chosen/probe'
    assert calls[1][-1] == str(source)


def test_nonexistent_explicit_ffmpeg_does_not_use_path_or_clobber_output(tmp_path):
    target = tmp_path / 'old.mp4'
    target.write_bytes(b'previous accepted file')
    missing = str(tmp_path / 'missing-ffmpeg')
    builder = VideoBuilder(VideoConfig(width=160, height=90, fps=24), ffmpeg_bin=missing,
                           ffprobe_bin=str(tmp_path / 'missing-ffprobe'))
    assert builder.pipeline.is_available() is False
    with pytest.raises(FileNotFoundError):
        builder.build_video(Timeline(duration=1), output_path=str(target), burn_subtitles=False)
    assert target.read_bytes() == b'previous accepted file'
    assert not list(tmp_path.glob('.airap_render_*'))


def test_filter_parser_understands_three_flags_legacy_rows_and_media_links(monkeypatch):
    listing = '''Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Commands
  A = Audio input/output
  | = Source or sink
 ... = fake V->V header
 ... ass             V->V       Render ASS subtitles
 TSC commands        V->V       Three capability flags
 .SC slice_commands  N->V       Dynamic input
 ..C command_only    A->A       Command support
 T.. timeline        AA->A      Multiple inputs
 .S. slice           V->VV      Multiple outputs
 ... source          |->V       No inputs
 ... sink            V->|       No outputs
 TS oldscale         V->V       Legacy two columns
 .. oldass           V->V       Legacy no flags
 .T. invalid_flags   V->V       Invalid column order
 .... too_many       V->V       Too many flags
 ... missing_links   not-a-link Header-like text
 ... no_links
'''
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, listing if '-filters' in command else 'version', '')
    monkeypatch.setattr(subprocess, 'run', run)
    pipe = FFmpegPipeline(ffmpeg_path='/chosen/render', ffprobe_path='/chosen/probe')
    expected = {'ass', 'commands', 'slice_commands', 'command_only', 'timeline', 'slice',
                'source', 'sink', 'oldscale', 'oldass'}
    assert pipe.get_available_filters() == expected
    assert pipe.has_filter('ass')
    assert len(calls) == 2  # Successful discovery is cached.


@pytest.mark.parametrize('failure', ['filters', 'version', 'missing', 'timeout'])
def test_failed_capability_command_cannot_report_ass_available(monkeypatch, failure):
    def run(command, **kwargs):
        if failure == 'missing':
            raise FileNotFoundError('No selected executable')
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 15)
        failed = '-filters' in command if failure == 'filters' else '-version' in command
        return subprocess.CompletedProcess(command, 3 if failed else 0,
                                           ' ... ass V->V Not a valid success result\n', '')
    monkeypatch.setattr(subprocess, 'run', run)
    pipe = FFmpegPipeline(ffmpeg_path='/chosen/render', ffprobe_path='/chosen/probe')
    assert pipe.get_available_filters() == set()
    assert pipe.has_filter('ass') is False


@pytest.fixture(scope='module')
def real_ass_tools():
    ffmpeg, ffprobe = os.environ.get('AIRAP_TEST_FFMPEG'), os.environ.get('AIRAP_TEST_FFPROBE')
    if ffmpeg is None and ffprobe is None:
        pytest.skip('Real ASS tests require explicit AIRAP_TEST_FFMPEG and AIRAP_TEST_FFPROBE')
    if not ffmpeg or not ffprobe:
        pytest.fail('Both explicit ASS tool paths are required; empty values do not select PATH')
    pipe = FFmpegPipeline(ffmpeg_path=ffmpeg, ffprobe_path=ffprobe)
    assert pipe.is_available(), 'Selected ASS FFmpeg must execute'
    assert pipe.has_filter('ass'), 'Selected FFmpeg must actually advertise ass support'
    result = subprocess.run([ffprobe, '-version'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, 'Selected FFprobe must execute'
    return ffmpeg, ffprobe


ASS_SCRIPT = '''[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Unicode MS,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,15,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.25,0:00:00.75,Default,,0,0,0,,字幕 TEST
'''


def decoded_frame_hashes(pipe, path):
    result = pipe.run_command(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0',
                               '-f', 'framemd5', '-'])
    return [line.rsplit(',', 1)[1].strip() for line in result.stdout.splitlines()
            if line and not line.startswith('#')]


@pytest.mark.parametrize('filename', [
    'plain.ass', 'caption space.ass', "apostrophe's.ass", 'colon:comma,brackets[ok];semi.ass',
    '反斜杠\\中文.ass', "组合 space's:,[中]\\字.ass", ' leading and trailing .ass ',
])
def test_real_ass_burn_survives_paths_and_changes_only_caption_time(tmp_path, real_ass_tools, filename):
    ffmpeg, ffprobe = real_ass_tools
    ass = tmp_path / filename
    ass.write_text(ASS_SCRIPT, encoding='utf-8')
    builder = VideoBuilder(VideoConfig(width=320, height=180, fps=24, preset='ultrafast', crf=0),
                           ffmpeg_bin=ffmpeg, ffprobe_bin=ffprobe)
    plain, burned = tmp_path / 'off.mp4', tmp_path / 'required.mp4'
    off = builder.build_video(Timeline(duration=1), ass_subtitle_path=str(ass),
                              output_path=str(plain), burn_subtitles=False, enable_effects=False)
    required = builder.build_video(Timeline(duration=1), ass_subtitle_path=str(ass),
                                   output_path=str(burned), burn_subtitles=True, enable_effects=False)
    assert off.subtitles_burned is False
    assert required.subtitles_burned is True and required.duration_verified
    before, after = decoded_frame_hashes(builder.pipeline, plain), decoded_frame_hashes(builder.pipeline, burned)
    assert len(before) == len(after) == 24
    assert before[:6] == after[:6]  # Before 0.25 seconds.
    assert before[18:] == after[18:]  # After 0.75 seconds.
    assert all(left != right for left, right in zip(before[6:18], after[6:18]))
    builder.pipeline.run_command(['ffmpeg', '-v', 'error', '-i', str(burned), '-f', 'null', '-'])
    probe = builder.pipeline.probe_file(str(burned))
    assert {stream['codec_type'] for stream in probe['streams']} >= {'audio', 'video'}
    assert not list(tmp_path.glob('.airap_render_*'))
