"""CLI forwarding and honest subtitle reporting; no real ASS renderer here."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from airap import cli


@pytest.fixture
def engine(monkeypatch):
    state = SimpleNamespace(configs=[], requests=[], error=None, updates={}, success=True)
    class FakeEngine:
        def __init__(self, config):
            self.config = config
            state.configs.append(config)
        def run(self, request):
            state.requests.append(request)
            if state.error:
                raise state.error
            metadata = {
                'render_kind': 'procedural_preview', 'is_generated_ai_video': False,
                'visual_source': 'procedural_placeholder', 'audio_source': 'synthetic_beat',
                'vocals_generated': False, 'lipsync_rendered': False, 'character_image_used': False,
                'duration_verified': True, 'subtitles_burned': self.config.subtitle_mode == 'required',
                'subtitle_mode': self.config.subtitle_mode,
                'subtitle_font_requested': self.config.style.font_name,
            }
            metadata.update(copy.deepcopy(state.updates))
            return SimpleNamespace(success=state.success, output_video_path='/tmp/subtitle-preview.mp4',
                                   duration_seconds=1.0, total_bars=1, bpm=130.0, metadata=metadata)
    monkeypatch.setattr(cli, 'RapPipelineOrchestrator', FakeEngine)
    return state


def executable(path):
    path.write_text('#!/bin/sh\nexit 0\n')
    path.chmod(0o700)
    return str(path)


@pytest.mark.parametrize('command', ['preview', 'generate'])
def test_explicit_tool_paths_and_requested_font_forward_exactly(command, engine, capsys, tmp_path):
    ffmpeg = executable(tmp_path / "工具 ffmpeg's,clip\\name")
    ffprobe = executable(tmp_path / '工具 ffprobe:main')
    family = 'Arial Unicode MS 中文'
    assert cli.main([command, '--lyrics', 'Local synthetic caption', '--ffmpeg', ffmpeg,
                     '--ffprobe', ffprobe, '--subtitle-mode', 'required',
                     '--subtitle-font', family, '--json']) == 0
    config = engine.configs[0]
    assert (config.ffmpeg_path, config.ffprobe_path, config.subtitle_mode, config.style.font_name) == (
        ffmpeg, ffprobe, 'required', family)
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert data['metadata']['subtitle_mode'] == 'required'
    assert data['metadata']['subtitle_font_requested'] == family
    assert data['metadata']['subtitles_burned'] is True
    assert 'subtitle_font_resolved' not in data['metadata']
    assert 'resolved_font' not in data['metadata']
    assert len(output.out.splitlines()) == 1
    assert not output.err


@pytest.mark.parametrize('mode', ['auto', 'required', 'off'])
def test_all_subtitle_modes_forward_and_report_metadata(mode, engine, capsys):
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-mode', mode]) == 0
    output = capsys.readouterr().out
    assert engine.configs[0].subtitle_mode == mode
    assert 'Subtitle mode requested: ' + mode in output
    assert ('Subtitles burned: yes' if mode == 'required' else 'Subtitles burned: no') in output
    assert 'font resolution not verified' in output
    assert 'AI vocals generated: no' in output


def test_defaults_keep_discovery_and_existing_style_font(engine, monkeypatch, capsys):
    def no_explicit_lookup(_):
        pytest.fail('CLI should leave default executable discovery to the pipeline')
    monkeypatch.setattr(cli.shutil, 'which', no_explicit_lookup)
    assert cli.main(['preview', '--lyrics', 'Test', '--json']) == 0
    config = engine.configs[0]
    assert config.ffmpeg_path is None
    assert config.ffprobe_path is None
    assert config.subtitle_mode == 'auto'
    assert config.style.font_name == 'Arial Black'
    assert json.loads(capsys.readouterr().out)['metadata']['subtitle_font_requested'] == 'Arial Black'


def test_bare_references_use_only_the_exact_requested_path_command(engine, monkeypatch, capsys, tmp_path):
    executable(tmp_path / 'ffmpeg-local')
    executable(tmp_path / 'ffprobe-local')
    monkeypatch.setenv('PATH', str(tmp_path))
    assert cli.main(['preview', '--lyrics', 'Test', '--ffmpeg', 'ffmpeg-local',
                     '--ffprobe', 'ffprobe-local', '--json']) == 0
    assert engine.configs[0].ffmpeg_path == 'ffmpeg-local'
    assert engine.configs[0].ffprobe_path == 'ffprobe-local'
    assert json.loads(capsys.readouterr().out)['success'] is True


@pytest.mark.parametrize('flag', ['--ffmpeg', '--ffprobe'])
@pytest.mark.parametrize('reference', ['', '   ', 'x' * 4097, 'tool\x00name', 'tool\nname',
                                      'tool\x1bname', 'tool\u0085name', 'tool\ud800name'])
def test_empty_malformed_or_unbounded_tools_fail_before_engine(flag, reference, engine, capsys):
    assert cli.main(['preview', '--lyrics', 'Test', flag, reference, '--json']) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)['error']['code'] == 'INVALID_INPUT'
    assert not engine.configs
    assert 'Traceback' not in output.out + output.err


@pytest.mark.parametrize('flag', ['--ffmpeg', '--ffprobe'])
@pytest.mark.parametrize('kind', ['missing', 'directory', 'not-executable'])
def test_invalid_explicit_file_never_falls_back_to_path(flag, kind, engine, monkeypatch, capsys, tmp_path):
    path = tmp_path / kind
    if kind == 'directory':
        path.mkdir()
    elif kind == 'not-executable':
        path.write_text('local fixture')
        path.chmod(0o600)
    calls = []
    monkeypatch.setattr(cli.shutil, 'which', lambda name: calls.append(name) or sys.executable)
    assert cli.main(['preview', '--lyrics', 'Test', flag, str(path), '--json']) == 2
    assert not engine.configs
    assert calls == []
    assert json.loads(capsys.readouterr().out)['success'] is False


def test_missing_bare_command_does_not_try_another_name(engine, monkeypatch, capsys):
    names = []
    monkeypatch.setattr(cli.shutil, 'which', lambda name: names.append(name))
    assert cli.main(['preview', '--lyrics', 'Test', '--ffmpeg', 'missing-special-tool', '--json']) == 2
    assert names == ['missing-special-tool']
    assert not engine.configs
    assert json.loads(capsys.readouterr().out)['success'] is False


@pytest.mark.parametrize('family', ['', ' ', 'Arial,Other', 'Arial\nOther', 'Arial\rOther',
                                  'Arial\x00Other', 'Arial\u0085Other', 'Arial\u202eOther',
                                  'Arial\ud800Other', 'A' * 257, '中' * 86])
def test_font_must_be_bounded_utf8_single_safe_ass_family(family, engine, capsys):
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-font', family, '--json']) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)['error']['code'] == 'INVALID_INPUT'
    assert not engine.configs
    assert 'Traceback' not in output.out + output.err


@pytest.mark.parametrize('family', ['A' * 256, '中' * 85 + 'A', 'Requested Family:中文'])
def test_valid_font_boundary_is_preserved_as_request_without_resolution_claim(family, engine, capsys):
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-font', family]) == 0
    output = capsys.readouterr().out
    assert engine.configs[0].style.font_name == family
    assert 'Subtitle font requested: ' + family in output
    assert '(font resolution not verified)' in output
    assert 'font resolved:' not in output.lower()


def test_actual_auto_burn_status_comes_from_renderer_metadata(engine, capsys):
    engine.updates = {'subtitles_burned': True}
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-mode', 'auto']) == 0
    output = capsys.readouterr().out
    assert 'Subtitle mode requested: auto' in output
    assert 'Subtitles burned: yes' in output


@pytest.mark.parametrize('mode,burned', [('required', False), ('required', None), ('off', True)])
def test_required_or_off_contract_cannot_report_contradictory_success(mode, burned, engine, capsys):
    engine.updates = {'subtitles_burned': burned}
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-mode', mode, '--json']) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['success'] is False
    assert result['error']['code'] == 'INVALID_RESULT'


def test_mode_fallback_in_metadata_is_not_silently_accepted(engine, capsys):
    engine.updates = {'subtitle_mode': 'auto'}
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-mode', 'required', '--json']) == 1
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'INVALID_RESULT'


def test_unsupported_ass_error_remains_failure_with_one_json_document(engine, capsys):
    engine.error = ValueError('selected executable cannot burn required ASS subtitles')
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-mode', 'required', '--json']) == 2
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert data['success'] is False
    assert 'cannot burn required ASS' in data['error']['message']
    assert len(output.out.splitlines()) == 1
    assert 'completed' not in output.out


def test_failed_renderer_is_not_masked_by_required_mode(engine, capsys):
    engine.success = False
    engine.updates = {'subtitles_burned': False, 'error': 'ASS render failed'}
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-mode', 'required', '--json']) == 1
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'PREVIEW_FAILED'


def test_invalid_subtitle_mode_and_real_module_bad_tool_exit_without_rendering(engine, capsys, tmp_path):
    assert cli.main(['preview', '--lyrics', 'Test', '--subtitle-mode', 'always', '--json']) == 2
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'INVALID_INPUT'
    assert not engine.configs
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-m', 'airap.cli', 'preview', '--lyrics', 'Local fixture',
                             '--ffmpeg', str(tmp_path / 'missing-ffmpeg'), '--subtitle-mode', 'required',
                             '--json'], cwd=root, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert json.loads(result.stdout)['success'] is False
    assert 'Traceback' not in result.stderr
