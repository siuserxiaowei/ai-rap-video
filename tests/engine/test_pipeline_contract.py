"""Pipeline contract checks using real planning and a controlled compositor."""
from dataclasses import replace
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from airap.config import ProjectConfig
from airap.pipeline import MAX_LYRICS_BYTES, RapPipelineOrchestrator, RapVideoGenerationRequest


def preview_request(**changes):
    return RapVideoGenerationRequest(lyrics_text='Local synthetic rhythm flows', bpm=300, **changes)


@pytest.fixture
def orchestrator(tmp_path):
    return RapPipelineOrchestrator(ProjectConfig(output_dir=tmp_path / 'output'))


@pytest.fixture
def compositor():
    result = SimpleNamespace(success=True, output_path='fixture-output.mp4', duration=0.79,
                             requested_duration=0.8, duration_verified=True,
                             subtitles_burned=False, error_message=None)
    with patch('airap.compositor.video_builder.VideoBuilder.build_video', return_value=result) as builder:
        yield builder, result


@pytest.fixture
def synthetic_beat():
    def create(*, output_path, **kwargs):
        Path(output_path).write_bytes(b'local synthetic fixture')
    with patch('airap.audio.beat_detector.SyntheticRapBeatGenerator.generate_wav', side_effect=create) as generator:
        yield generator


@pytest.mark.parametrize('changes', [
    {'lyrics_text': ''}, {'lyrics_text': ' \n\t '}, {'lyrics_text': None},
    {'lyrics_text': '中' * (MAX_LYRICS_BYTES // 3 + 1)}, {'lyrics_text': '\ud800'},
    {'bpm': 39.99}, {'bpm': 300.01}, {'bpm': True}, {'bpm': '130'},
    {'bpm': float('nan')}, {'bpm': float('inf')}, {'bpm': 10 ** 1000},
    {'aspect_ratio': '1:1'}, {'output_filename': '../escape.mp4'},
    {'output_filename': '/tmp/escape.mp4'}, {'output_filename': 'a\\escape.mp4'},
    {'output_filename': 'a:escape.mp4'}, {'output_filename': 'a.mp4\n'},
    {'output_filename': 'a\x00.mp4'}, {'output_filename': '.mp4'},
    {'output_filename': 'a.mov'}, {'output_filename': 'x' * 256 + '.mp4'},
    {'character_image_path': 'portrait.jpg'}, {'character_image_path': ''},
    {'theme': '\ud800'}, {'theme': None},
])
def test_invalid_request_never_generates_assets(orchestrator, changes, compositor, synthetic_beat):
    request = replace(preview_request(), **changes)
    with pytest.raises(ValueError):
        orchestrator.run(request)
    compositor[0].assert_not_called()
    synthetic_beat.assert_not_called()
    assert not orchestrator.output_dir.exists()


@pytest.mark.parametrize('path_kind', ['missing', 'directory', 'empty', 'not_path'])
def test_supplied_audio_is_never_silently_replaced(orchestrator, tmp_path, path_kind, compositor, synthetic_beat):
    choices = {'missing': tmp_path / 'missing.wav', 'directory': tmp_path,
               'empty': '', 'not_path': 123}
    with pytest.raises(ValueError, match='readable local file'):
        orchestrator.run(preview_request(audio_path=choices[path_kind]))
    compositor[0].assert_not_called()
    synthetic_beat.assert_not_called()
    assert not orchestrator.output_dir.exists()


def test_unreadable_audio_rejects_without_fallback(orchestrator, tmp_path, synthetic_beat):
    source = tmp_path / 'audio.wav'
    source.write_bytes(b'private local fixture')
    with patch.object(Path, 'open', side_effect=PermissionError('fixture denial')):
        with pytest.raises(ValueError, match='readable local file'):
            orchestrator.run(preview_request(audio_path=str(source)))
    synthetic_beat.assert_not_called()
    assert not orchestrator.output_dir.exists()


def test_header_only_lyrics_do_not_create_an_arbitrary_fallback(orchestrator, compositor, synthetic_beat):
    with pytest.raises(ValueError, match='non-header bar'):
        orchestrator.run(replace(preview_request(), lyrics_text='[Verse 1]\n[Hook]'))
    assert not orchestrator.output_dir.exists()
    compositor[0].assert_not_called()
    synthetic_beat.assert_not_called()


def test_preview_metadata_distinguishes_plans_from_rendered_media(orchestrator, compositor, synthetic_beat):
    result = orchestrator.run(preview_request(theme='neon_theme'))
    assert result.success is True
    assert result.duration_seconds == 0.79  # measured renderer value, not the 0.8s schedule
    metadata = result.metadata
    assert metadata['render_kind'] == 'procedural_preview'
    assert metadata['is_generated_ai_video'] is False
    assert metadata['visual_source'] == 'procedural_placeholder'
    assert metadata['audio_source'] == 'synthetic_beat'
    for flag in ['vocals_generated', 'lipsync_rendered', 'character_image_used', 'subtitles_burned']:
        assert metadata[flag] is False
    assert metadata['duration_verified'] is True
    assert metadata['requested_duration'] == 0.8
    assert metadata['theme'] is None
    assert metadata['requested_theme'] == 'neon_theme'
    assert metadata['theme_applied'] is False
    assert metadata['avatar_frames'] == 0
    assert metadata['planned_avatar_states'] > 0
    assert metadata['avatar_states_are_planning_data'] is True
    assert Path(metadata['audio_path']).is_file()
    assert Path(metadata['subtitle_path']).is_file()
    synthetic_beat.assert_called_once()
    assert compositor[0].call_args.kwargs['duration'] == pytest.approx(0.8)


@pytest.mark.parametrize('aspect,dimensions', [('9:16', (1080, 1920)), ('16:9', (1920, 1080))])
def test_supplied_audio_forwarded_unchanged_with_honest_subtitle_flags(orchestrator, tmp_path, compositor, synthetic_beat, aspect, dimensions):
    audio = tmp_path / 'source.wav'
    audio.write_bytes(b'fixture source audio')
    compositor[1].subtitles_burned = True
    result = orchestrator.run(preview_request(audio_path=str(audio), aspect_ratio=aspect))
    assert result.metadata['audio_source'] == 'provided_audio'
    assert result.metadata['audio_path'] == str(audio.resolve())
    assert compositor[0].call_args.kwargs['audio_path'] == str(audio.resolve())
    assert result.metadata['subtitles_burned'] is True
    assert audio.read_bytes() == b'fixture source audio'
    assert (orchestrator.config.video.width, orchestrator.config.video.height) == dimensions
    synthetic_beat.assert_not_called()


def test_failure_and_unverified_duration_are_not_upgraded(orchestrator, compositor, synthetic_beat):
    compositor[1].success = False
    compositor[1].duration_verified = False
    compositor[1].error_message = 'fixture stream validation failed'
    result = orchestrator.run(preview_request())
    assert result.success is False
    assert result.metadata['duration_verified'] is False
    assert result.metadata['error'] == 'fixture stream validation failed'


def test_renderer_exception_propagates_without_success(orchestrator, compositor, synthetic_beat):
    compositor[0].side_effect = RuntimeError('fixture decoder failed')
    with pytest.raises(RuntimeError, match='fixture decoder failed'):
        orchestrator.run(preview_request())


def test_unique_assets_never_replace_supplied_media(orchestrator, compositor, synthetic_beat):
    orchestrator.output_dir.mkdir()
    supplied = orchestrator.output_dir / 'rap_lyrics.ass'
    supplied.write_bytes(b'supplied audio sentinel, filename deliberately collides')
    first = orchestrator.run(preview_request(audio_path=str(supplied)))
    second = orchestrator.run(preview_request())
    third = orchestrator.run(preview_request())
    assert supplied.read_bytes() == b'supplied audio sentinel, filename deliberately collides'
    assert first.metadata['subtitle_path'] != str(supplied)
    assert second.metadata['audio_path'] != third.metadata['audio_path']
    assert second.metadata['subtitle_path'] != third.metadata['subtitle_path']
    assert Path(second.metadata['audio_path']).exists()


def test_target_cannot_overwrite_audio_or_hardlink(orchestrator, tmp_path, compositor, synthetic_beat):
    orchestrator.output_dir.mkdir()
    audio = orchestrator.output_dir / 'source.mp4'
    audio.write_bytes(b'original media sentinel')
    alias = orchestrator.output_dir / 'hardlink.mp4'
    alias.hardlink_to(audio)
    for filename in ['source.mp4', 'hardlink.mp4']:
        with pytest.raises(ValueError, match='distinct from the output'):
            orchestrator.run(preview_request(audio_path=str(audio), output_filename=filename))
    assert audio.read_bytes() == b'original media sentinel'
    assert sorted(p.name for p in orchestrator.output_dir.iterdir()) == ['hardlink.mp4', 'source.mp4']
    synthetic_beat.assert_not_called()
    compositor[0].assert_not_called()


def test_utf8_limit_counts_bytes_and_bpm_endpoints_without_render(orchestrator):
    request = replace(preview_request(), lyrics_text='a' * MAX_LYRICS_BYTES, bpm=40)
    assert orchestrator._validate_request(request) is None
    assert orchestrator._validate_request(replace(request, bpm=300)) is None
    with pytest.raises(ValueError, match='64 KiB'):
        orchestrator._validate_request(replace(request, lyrics_text='a' * (MAX_LYRICS_BYTES + 1)))
    assert not orchestrator.output_dir.exists()


def test_more_than_sixteen_bars_are_preserved(orchestrator, compositor, synthetic_beat):
    lyrics = "\n".join(f"Line {index} keeps the full flow" for index in range(1, 18))
    result = orchestrator.run(replace(preview_request(), lyrics_text=lyrics))
    assert result.total_bars == 17
    assert result.metadata["lyrics_truncated"] is False
    assert compositor[0].call_args.kwargs["duration"] == pytest.approx(17 * 0.8)
    subtitle_text = Path(result.metadata["subtitle_path"]).read_text(encoding="utf-8")
    assert "Line 17" in re.sub(r"\{[^}]*\}", "", subtitle_text)


def test_over_120_seconds_is_rejected_before_planning_or_files(orchestrator, compositor, synthetic_beat):
    lyrics = "\n".join("Full line of local fixture lyrics" for _ in range(21))
    with patch("airap.lyrics.flow_analyzer.FlowAnalyzer.analyze_verse") as analyze:
        with pytest.raises(ValueError, match="120 seconds"):
            orchestrator.run(replace(preview_request(), lyrics_text=lyrics, bpm=40))
        analyze.assert_not_called()
    compositor[0].assert_not_called()
    synthetic_beat.assert_not_called()
    assert not orchestrator.output_dir.exists()
