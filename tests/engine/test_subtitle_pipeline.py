"""Configuration and preflight contracts; controlled renderer, no tool execution."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from airap.config import ProjectConfig, StyleConfig, VideoConfig
from airap.pipeline import RapPipelineOrchestrator, RapVideoGenerationRequest


def request():
    return RapVideoGenerationRequest(lyrics_text='本机字幕测试 flow', bpm=300)


@pytest.fixture
def config(tmp_path):
    return ProjectConfig(output_dir=tmp_path / 'output')


@pytest.fixture
def fake_builder():
    result = SimpleNamespace(success=True, output_path='fixture-preview.mp4', duration=0.8,
                             requested_duration=0.8, duration_verified=True,
                             subtitles_burned=False, error_message=None)
    with patch('airap.compositor.video_builder.VideoBuilder') as factory:
        factory.return_value.pipeline.has_filter.return_value = True
        factory.return_value.build_video.return_value = result
        yield factory, result


@pytest.fixture
def beat():
    def create(*, output_path, **kwargs):
        Path(output_path).write_bytes(b'local synthetic beat fixture')
    with patch('airap.audio.beat_detector.SyntheticRapBeatGenerator.generate_wav', side_effect=create) as mocked:
        yield mocked


def executable(tmp_path, name):
    path = tmp_path / name
    path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    path.chmod(0o755)
    return path


def test_project_config_appends_compatible_defaults():
    config = ProjectConfig('name', Path('output'), VideoConfig(), None, StyleConfig())
    assert config.ffmpeg_path is None
    assert config.ffprobe_path is None
    assert config.subtitle_mode == 'auto'
    assert config.style.font_name == 'Arial Black'


@pytest.mark.parametrize('mode,burn', [('auto', None), ('required', True), ('off', False)])
def test_modes_forward_and_preflight_only_required(config, fake_builder, beat, mode, burn):
    config.subtitle_mode = mode
    fake_builder[1].subtitles_burned = mode == 'required'
    orchestrator = RapPipelineOrchestrator(config)
    result = orchestrator.run(request())
    fake_builder[0].assert_called_once_with(config=config.video)
    kwargs = fake_builder[0].return_value.build_video.call_args.kwargs
    if mode == 'auto':
        assert 'burn_subtitles' not in kwargs  # old fakebuilder remains compatible
    else:
        assert kwargs['burn_subtitles'] is burn
    if mode == 'required':
        fake_builder[0].return_value.pipeline.has_filter.assert_called_once_with('ass')
    else:
        fake_builder[0].return_value.pipeline.has_filter.assert_not_called()
    assert result.metadata['subtitle_mode'] == mode
    assert result.metadata['subtitles_burned'] is fake_builder[1].subtitles_burned
    assert result.metadata['subtitle_font_requested'] == config.style.font_name
    assert 'subtitle_font_resolved' not in result.metadata
    assert result.metadata['render_kind'] == 'procedural_preview'
    assert result.metadata['is_generated_ai_video'] is False


def test_required_unsupported_fails_before_assets_and_preserves_output(config, fake_builder, beat):
    config.subtitle_mode = 'required'
    config.output_dir.mkdir()
    target = config.output_dir / request().output_filename
    target.write_bytes(b'original output sentinel')
    fake_builder[0].return_value.pipeline.has_filter.return_value = False
    with pytest.raises(RuntimeError, match='no ASS filter'):
        RapPipelineOrchestrator(config).run(request())
    beat.assert_not_called()
    fake_builder[0].return_value.build_video.assert_not_called()
    assert list(config.output_dir.iterdir()) == [target]
    assert target.read_bytes() == b'original output sentinel'


def test_required_preflight_error_does_not_write_assets(config, fake_builder, beat):
    config.subtitle_mode = 'required'
    fake_builder[0].return_value.pipeline.has_filter.side_effect = RuntimeError('fixture filter query failed')
    with pytest.raises(RuntimeError, match='fixture filter query failed'):
        RapPipelineOrchestrator(config).run(request())
    assert not config.output_dir.exists()
    beat.assert_not_called()


@pytest.mark.parametrize('reported_burn', [False, None, 1, 'true'])
def test_preflight_does_not_replace_actual_required_burn(config, fake_builder, beat, reported_burn):
    config.subtitle_mode = 'required'
    fake_builder[1].subtitles_burned = reported_burn
    with pytest.raises(RuntimeError, match='not confirmed by the renderer'):
        RapPipelineOrchestrator(config).run(request())
    fake_builder[0].return_value.pipeline.has_filter.assert_called_once_with('ass')
    fake_builder[0].return_value.build_video.assert_called_once()


def test_required_success_without_burn_field_is_rejected(config, fake_builder, beat):
    config.subtitle_mode = 'required'
    del fake_builder[1].subtitles_burned
    with pytest.raises(RuntimeError, match='not confirmed by the renderer'):
        RapPipelineOrchestrator(config).run(request())


def test_off_success_reporting_burned_subtitles_is_rejected(config, fake_builder, beat):
    config.subtitle_mode = 'off'
    fake_builder[1].subtitles_burned = True
    with pytest.raises(RuntimeError, match='off mode was violated'):
        RapPipelineOrchestrator(config).run(request())
    fake_builder[0].return_value.pipeline.has_filter.assert_not_called()


@pytest.mark.parametrize('reported_burn', [False, True])
def test_auto_preserves_actual_renderer_burn_flag(config, fake_builder, beat, reported_burn):
    config.subtitle_mode = 'auto'
    fake_builder[1].subtitles_burned = reported_burn
    result = RapPipelineOrchestrator(config).run(request())
    assert result.success is True
    assert result.metadata['subtitles_burned'] is reported_burn


@pytest.mark.parametrize('mode,reported_burn', [('required', False), ('off', True)])
def test_renderer_failure_is_preserved_without_mode_success_claim(config, fake_builder, beat, mode, reported_burn):
    config.subtitle_mode = mode
    fake_builder[1].success = False
    fake_builder[1].subtitles_burned = reported_burn
    fake_builder[1].error_message = 'fixture render failure'
    result = RapPipelineOrchestrator(config).run(request())
    assert result.success is False
    assert result.metadata['error'] == 'fixture render failure'
    assert result.metadata['subtitles_burned'] is reported_burn


def test_selected_toolchain_is_used_for_preflight_and_render(config, tmp_path, fake_builder, beat):
    config.subtitle_mode = 'required'
    fake_builder[1].subtitles_burned = True
    config.ffmpeg_path = str(executable(tmp_path, 'ffmpeg 画面'))
    config.ffprobe_path = str(executable(tmp_path, 'ffprobe 画面'))
    result = RapPipelineOrchestrator(config).run(request())
    fake_builder[0].assert_called_once_with(config=config.video, ffmpeg_bin=config.ffmpeg_path,
                                          ffprobe_bin=config.ffprobe_path)
    fake_builder[0].return_value.pipeline.has_filter.assert_called_once_with('ass')
    assert result.metadata['subtitle_mode'] == 'required'


@pytest.mark.parametrize('field,keyword', [('ffmpeg_path', 'ffmpeg_bin'), ('ffprobe_path', 'ffprobe_bin')])
def test_single_selected_tool_does_not_override_other_default(config, tmp_path, fake_builder, beat, field, keyword):
    binary = executable(tmp_path, 'selected')
    setattr(config, field, str(binary))
    RapPipelineOrchestrator(config).run(request())
    fake_builder[0].assert_called_once_with(config=config.video, **{keyword: str(binary)})


def test_bare_reference_is_resolved_only_by_its_own_name(config, tmp_path, fake_builder, beat):
    binary = executable(tmp_path, 'special-ffmpeg')
    config.ffmpeg_path = 'special-ffmpeg'
    with patch('airap.pipeline.shutil.which', return_value=str(binary)) as locate:
        RapPipelineOrchestrator(config).run(request())
    locate.assert_called_once_with('special-ffmpeg')
    fake_builder[0].assert_called_once_with(config=config.video, ffmpeg_bin=str(binary))


@pytest.mark.parametrize('field', ['ffmpeg_path', 'ffprobe_path'])
@pytest.mark.parametrize('invalid', ['', ' \t', '\nffmpeg', 'tool\x00', '\ud800', 123, '中' * 1366])
def test_invalid_tool_reference_rejected_without_writes(config, fake_builder, beat, field, invalid):
    setattr(config, field, invalid)
    with pytest.raises(ValueError):
        RapPipelineOrchestrator(config).run(request())
    fake_builder[0].assert_not_called()
    beat.assert_not_called()
    assert not config.output_dir.exists()


@pytest.mark.parametrize('field', ['ffmpeg_path', 'ffprobe_path'])
def test_explicit_missing_binary_never_falls_back(config, fake_builder, beat, field):
    setattr(config, field, 'does-not-exist-fixture-tool')
    with patch('airap.pipeline.shutil.which', return_value=None) as locate:
        with pytest.raises(ValueError, match='executable local file'):
            RapPipelineOrchestrator(config).run(request())
    locate.assert_called_once_with('does-not-exist-fixture-tool')
    fake_builder[0].assert_not_called()
    beat.assert_not_called()
    assert not config.output_dir.exists()


@pytest.mark.parametrize('kind', ['directory', 'not_executable'])
def test_non_executable_file_and_directory_are_rejected(config, tmp_path, fake_builder, kind):
    candidate = tmp_path / 'tool'
    if kind == 'directory':
        candidate.mkdir()
    else:
        candidate.write_text('not an executable', encoding='utf-8')
        candidate.chmod(0o644)
    config.ffmpeg_path = str(candidate)
    with pytest.raises(ValueError, match='executable local file'):
        RapPipelineOrchestrator(config).run(request())
    fake_builder[0].assert_not_called()
    assert not config.output_dir.exists()


@pytest.mark.parametrize('invalid', ['', ' \t', 'Font,Corrupted', 'Font\nInjected', 'Font\x00', 'Font\u200b', '\ud800', 123, '中' * 86])
def test_font_validation_blocks_ass_style_corruption(config, fake_builder, beat, invalid):
    config.style.font_name = invalid
    with pytest.raises(ValueError):
        RapPipelineOrchestrator(config).run(request())
    fake_builder[0].assert_not_called()
    beat.assert_not_called()
    assert not config.output_dir.exists()


def test_requested_font_is_written_to_ass_without_resolution_claim(config, fake_builder, beat):
    config.style.font_name = 'Arial Unicode MS 中文'
    result = RapPipelineOrchestrator(config).run(request())
    ass = Path(result.metadata['subtitle_path']).read_text(encoding='utf-8')
    assert config.style.font_name in ass
    assert result.metadata['subtitle_font_requested'] == 'Arial Unicode MS 中文'
    assert not any('resolved' in field for field in result.metadata)


@pytest.mark.parametrize('mode', ['', 'AUTO', 'sometimes', None, True, []])
def test_mode_validation_before_assets(config, fake_builder, beat, mode):
    config.subtitle_mode = mode
    with pytest.raises(ValueError, match='Subtitle mode'):
        RapPipelineOrchestrator(config).run(request())
    fake_builder[0].assert_not_called()
    beat.assert_not_called()
    assert not config.output_dir.exists()
