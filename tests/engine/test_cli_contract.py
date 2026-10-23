"""CLI contracts with fake renderer results; these do not verify media quality."""
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from airap import cli


@pytest.fixture
def fake_engine(monkeypatch):
    state = SimpleNamespace(configs=[], requests=[], init_error=None, run_error=None)
    state.result = SimpleNamespace(
        success=True, output_video_path='/tmp/procedural-preview.mp4', duration_seconds=2.0,
        total_bars=1, bpm=130.0, metadata={
            'render_kind': 'procedural_preview', 'is_generated_ai_video': False,
            'visual_source': 'procedural_placeholder', 'audio_source': 'synthetic_beat',
            'vocals_generated': False, 'lipsync_rendered': False, 'character_image_used': False,
            'subtitles_burned': False, 'duration_verified': True,
            'requested_theme': 'cyberpunk_street', 'theme': None, 'theme_applied': False,
            'avatar_frames': 0, 'planned_avatar_states': 60, 'error': None})
    class FakeOrchestrator:
        def __init__(self, config):
            if state.init_error:
                raise state.init_error
            state.configs.append(config)
        def run(self, request):
            state.requests.append(request)
            if state.run_error:
                raise state.run_error
            return state.result
    monkeypatch.setattr(cli, 'RapPipelineOrchestrator', FakeOrchestrator)
    return state


@pytest.mark.parametrize('command', ['preview', 'generate'])
def test_preferred_and_legacy_commands_preserve_request_and_output_directory(command, fake_engine, capsys, tmp_path):
    status = cli.main([command, '--lyrics', 'Synthetic local test', '--bpm', '120',
                       '--aspect', '16:9', '--theme', 'requested-only',
                       '--output', 'test.mp4', '--output-dir', str(tmp_path)])
    output = capsys.readouterr()
    assert status == 0
    assert 'Local procedural preview completed' in output.out
    assert 'AI vocals generated: no' in output.out
    assert 'Lip-sync rendered: no' in output.out
    assert 'synthetic instrumental beat' in output.out
    assert 'Subtitles burned: no' in output.out
    assert 'Theme applied: no' in output.out
    assert 'Generation Succeeded' not in output.out
    assert not output.err
    assert fake_engine.configs[0].output_dir == tmp_path
    request = fake_engine.requests[0]
    assert (request.lyrics_text, request.bpm, request.aspect_ratio, request.theme, request.output_filename) == (
        'Synthetic local test', 120, '16:9', 'requested-only', 'test.mp4')


@pytest.mark.parametrize('arguments', [
    ['--json', 'preview', '--lyrics', 'Test'], ['preview', '--lyrics', 'Test', '--json']])
def test_json_is_one_document_and_keeps_capability_metadata(arguments, fake_engine, capsys):
    assert cli.main(arguments) == 0
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert data['success'] is True
    assert data['metadata'] == fake_engine.result.metadata
    assert data['duration_seconds'] == 2.0
    assert data['output_video_path'] == fake_engine.result.output_video_path
    assert not output.err
    assert len(output.out.splitlines()) == 1


def test_audio_and_subtitles_report_returned_facts_without_inventing_vocals(fake_engine, capsys):
    fake_engine.result.metadata.update(audio_source='provided_audio', subtitles_burned=True, duration_verified=False)
    assert cli.main(['preview', '--lyrics', 'Test']) == 0
    output = capsys.readouterr().out
    assert 'provided source audio (content not independently verified)' in output
    assert 'Subtitles burned: yes' in output
    assert 'Duration verified: no' in output
    assert 'AI vocals generated: no' in output
    assert 'synthetic instrumental beat' not in output


def test_missing_metadata_is_unknown_instead_of_inferred_from_arguments(fake_engine, capsys):
    fake_engine.result.metadata = {}
    assert cli.main(['preview', '--lyrics', 'Test']) == 0
    output = capsys.readouterr().out
    assert 'Audio source: unknown' in output
    assert 'Subtitles burned: unknown' in output
    assert 'AI vocals generated: unknown' in output
    assert 'synthetic instrumental beat' not in output


@pytest.mark.parametrize('json_mode', [False, True])
def test_false_result_has_nonzero_exit_and_no_completion_message(json_mode, fake_engine, capsys):
    fake_engine.result.success = False
    fake_engine.result.metadata['error'] = 'render verification failed'
    status = cli.main(['preview', '--lyrics', 'Test'] + (['--json'] if json_mode else []))
    output = capsys.readouterr()
    assert status == 1
    assert 'completed' not in output.out.lower()
    assert 'Generation Succeeded' not in output.out
    if json_mode:
        result = json.loads(output.out)
        assert result['success'] is False
        assert result['error']['code'] == 'PREVIEW_FAILED'
        assert 'render verification failed' in result['error']['message']
        assert not output.err
    else:
        assert not output.out
        assert 'render verification failed' in output.err


@pytest.mark.parametrize('stage,error,expected', [
    ('init_error', PermissionError('output not writable'), 2),
    ('init_error', RuntimeError('initialization unavailable'), 1),
    ('run_error', ValueError('supplied audio is invalid'), 2),
    ('run_error', RuntimeError('renderer unavailable'), 1)])
def test_initialization_and_render_exceptions_are_graceful(stage, error, expected, fake_engine, capsys):
    setattr(fake_engine, stage, error)
    assert cli.main(['preview', '--lyrics', 'Test', '--json']) == expected
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert data['success'] is False
    assert str(error) in data['error']['message']
    assert 'Traceback' not in output.out + output.err


def test_explicit_and_legacy_file_lyrics_are_read_as_utf8(fake_engine, capsys, tmp_path):
    source = tmp_path / 'lyrics.txt'
    source.write_text('中文本地预览\n第二行', encoding='utf-8')
    for flag in ('--lyrics-file', '--lyrics'):
        assert cli.main(['preview', flag, str(source), '--json']) == 0
        assert fake_engine.requests[-1].lyrics_text == source.read_text(encoding='utf-8')
        assert json.loads(capsys.readouterr().out)['success'] is True


def test_large_valid_literal_is_not_mistaken_for_an_invalid_filesystem_path(fake_engine, capsys):
    text = 'word ' * 4000
    assert cli.main(['preview', '--lyrics', text, '--json']) == 0
    assert fake_engine.requests[0].lyrics_text == text
    assert json.loads(capsys.readouterr().out)['success'] is True


def test_lyrics_file_exact_utf8_byte_limit_and_bounded_read(fake_engine, capsys, tmp_path):
    source = tmp_path / 'lyrics.txt'
    source.write_bytes(b'a' * cli.MAX_LYRICS_BYTES)
    assert cli.main(['preview', '--lyrics-file', str(source), '--json']) == 0
    assert len(fake_engine.requests[-1].lyrics_text) == cli.MAX_LYRICS_BYTES
    capsys.readouterr()
    source.write_text('中' * (cli.MAX_LYRICS_BYTES // 3 + 1), encoding='utf-8')
    assert cli.main(['preview', '--lyrics-file', str(source), '--json']) == 2
    assert '64 KiB' in json.loads(capsys.readouterr().out)['error']['message']
    class ReadSpy(io.BytesIO):
        def read(self, count=-1):
            assert count == cli.MAX_LYRICS_BYTES + 1
            return super().read(count)
    class FileFixture:
        def stat(self):
            return SimpleNamespace(st_mode=stat.S_IFREG)
        def open(self, mode):
            assert mode == 'rb'
            return ReadSpy(b'a' * (cli.MAX_LYRICS_BYTES + 50))
    with pytest.raises(cli.CLIInputError, match='64 KiB'):
        cli._read_lyrics(FileFixture())


@pytest.mark.parametrize('kind', ['missing', 'directory', 'bad-utf8', 'blank'])
def test_invalid_explicit_files_fail_before_initialization(kind, fake_engine, capsys, tmp_path):
    source = tmp_path / kind
    if kind == 'directory':
        source.mkdir()
    elif kind == 'bad-utf8':
        source.write_bytes(b'\xff')
    elif kind == 'blank':
        source.write_text(' \n\t')
    assert cli.main(['preview', '--lyrics-file', str(source), '--json']) == 2
    assert json.loads(capsys.readouterr().out)['success'] is False
    assert not fake_engine.configs


@pytest.mark.parametrize('value', ['nan', 'inf', '-inf', '39', '301'])
def test_invalid_bpm_fails_before_initialization(value, fake_engine, capsys):
    assert cli.main(['preview', '--lyrics', 'Test', '--bpm=' + value, '--json']) == 2
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'INVALID_INPUT'
    assert not fake_engine.configs


@pytest.mark.parametrize('value', ['../escape.mp4', '/tmp/absolute.mp4', 'sub/a.mp4',
                                  'sub\\a.mp4', 'wrong.mov', '', 'bad\x00.mp4'])
def test_output_must_be_basename_and_cannot_escape_output_dir(value, fake_engine, capsys):
    assert cli.main(['preview', '--lyrics', 'Test', '--output', value, '--json']) == 2
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'INVALID_INPUT'
    assert not fake_engine.configs


@pytest.mark.parametrize('source_flag', ['--lyrics-file', '--audio'])
def test_output_cannot_replace_supplied_lyrics_or_audio(source_flag, fake_engine, capsys, tmp_path):
    source = tmp_path / 'input.mp4'
    source.write_text('local synthetic fixture')
    args = ['preview', source_flag, str(source), '--output', 'input.mp4', '--output-dir', str(tmp_path), '--json']
    if source_flag == '--audio':
        args += ['--lyrics', 'Test']
    assert cli.main(args) == 2
    assert 'overwrite' in json.loads(capsys.readouterr().out)['error']['message']
    assert source.read_text() == 'local synthetic fixture'
    assert not fake_engine.configs


def test_missing_supplied_audio_is_never_silently_replaced(fake_engine, capsys, tmp_path):
    assert cli.main(['preview', '--lyrics', 'Test', '--audio', str(tmp_path / 'absent.wav'), '--json']) == 2
    assert json.loads(capsys.readouterr().out)['success'] is False
    assert not fake_engine.configs


@pytest.mark.parametrize('change', [
    {'vocals_generated': True}, {'lipsync_rendered': True}, {'theme_applied': True},
    {'render_kind': 'ai_video'}, {'subtitles_burned': 1}, {'duration_verified': 'yes'},
    {'audio_source': []}, {'score': float('nan')}, {'extra': object()}])
def test_contradictory_or_unserializable_metadata_never_reports_success(change, fake_engine, capsys):
    fake_engine.result.metadata.update(change)
    assert cli.main(['preview', '--lyrics', 'Test', '--json']) == 1
    data = json.loads(capsys.readouterr().out)
    assert data['success'] is False
    assert data['error']['code'] == 'INVALID_RESULT'


@pytest.mark.parametrize('duration', [None, True, 0, -1, float('nan'), float('inf')])
def test_invalid_success_duration_is_a_failure(duration, fake_engine, capsys):
    fake_engine.result.duration_seconds = duration
    assert cli.main(['preview', '--lyrics', 'Test', '--json']) == 1
    assert json.loads(capsys.readouterr().out)['success'] is False


@pytest.mark.parametrize('args', [
    ['preview', '--json'], ['preview', '--lyrics', ''],
    ['preview', '--lyrics', 'x', '--lyrics-file', 'y', '--json'],
    ['preview', '--lyrics', 'x', '--aspect', '1:1', '--json'], ['submit', '--json']])
def test_argument_errors_are_graceful_and_do_not_initialize(args, fake_engine, capsys):
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert 'Traceback' not in output.out + output.err
    if '--json' in args:
        assert json.loads(output.out)['success'] is False
    assert not fake_engine.configs


def test_real_module_version_and_missing_file_exit_codes_without_rendering(tmp_path):
    root = Path(__file__).resolve().parents[2]
    version = subprocess.run([sys.executable, '-m', 'airap.cli', 'version', '--json'],
                             cwd=root, capture_output=True, text=True, timeout=10)
    assert version.returncode == 0
    assert json.loads(version.stdout)['version']
    bad = subprocess.run([sys.executable, '-m', 'airap.cli', 'preview', '--lyrics-file',
                          str(tmp_path / 'missing.txt'), '--json'], cwd=root,
                         capture_output=True, text=True, timeout=10)
    assert bad.returncode == 2
    assert json.loads(bad.stdout)['success'] is False
    assert 'Traceback' not in bad.stderr
