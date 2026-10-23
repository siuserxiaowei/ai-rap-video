"""CLI for local procedural previews; no AI vocals or rendered lip-sync."""

import argparse
import json
import math
from pathlib import Path
import stat
import sys

from airap.pipeline import RapPipelineOrchestrator, RapVideoGenerationRequest
from airap.config import ProjectConfig


MAX_LYRICS_BYTES = 64 * 1024


class CLIInputError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CLIInputError(message)


def _parser():
    parser = _Parser(description=(
        'AIRapStudio: local procedural video preview. '
        'No AI vocals, character animation or rendered lip-sync.'))
    parser.add_argument('--json', action='store_true', help='Print one machine-readable JSON result')
    commands = parser.add_subparsers(dest='command')
    preview = commands.add_parser('preview', aliases=['generate'], help=(
        'Compose a local procedural preview (generate is a legacy alias)'))
    lyrics = preview.add_mutually_exclusive_group(required=True)
    lyrics.add_argument('--lyrics', help='Lyrics text; existing local file paths remain supported for compatibility')
    lyrics.add_argument('--lyrics-file', type=Path, help='Explicit UTF-8 lyrics file, at most 64 KiB')
    preview.add_argument('--bpm', type=float, default=130.0, help='Finite tempo, 40–300 BPM (default: 130)')
    preview.add_argument('--audio', default=None, help='Readable local source audio; omitted means a synthetic beat, not vocals')
    preview.add_argument('--theme', default='cyberpunk_street', help='Requested theme recorded for planning; not claimed as applied')
    preview.add_argument('--aspect', choices=['9:16', '16:9'], default='9:16', help='Aspect ratio')
    preview.add_argument('--output', default='output_rap.mp4', help='Output .mp4 basename; use --output-dir for its directory')
    preview.add_argument('--output-dir', type=Path, default=Path('./output'), help='Local output directory (default: ./output)')
    preview.add_argument('--json', action='store_true', default=argparse.SUPPRESS,
                         help='Print one machine-readable JSON result')
    version = commands.add_parser('version', help='Show version')
    version.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
    return parser


def _read_lyrics(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise CLIInputError('lyrics file must be a readable regular local file')
    with path.open('rb') as source:
        raw = source.read(MAX_LYRICS_BYTES + 1)
    if len(raw) > MAX_LYRICS_BYTES:
        raise CLIInputError('lyrics file exceeds 64 KiB UTF-8')
    try:
        return raw.decode('utf-8')
    except UnicodeError:
        raise CLIInputError('lyrics file must contain valid UTF-8 text') from None


def _lyrics_input(args):
    source_path = args.lyrics_file
    text = args.lyrics
    if source_path is None and text is not None and '\n' not in text and '\r' not in text:
        # Do not pass arbitrarily long literal lyrics to a filesystem syscall.
        # Missing paths retain the legacy interpretation as literal text;
        # --lyrics-file makes the user's file intent explicit.
        try:
            candidate = Path(text)
            if len(text.encode('utf-8')) <= 4096 and candidate.is_file():
                source_path = candidate
        except (OSError, ValueError):
            pass
    if source_path is not None:
        text = _read_lyrics(source_path)
    if not isinstance(text, str) or not text.strip():
        raise CLIInputError('lyrics must contain nonblank text')
    try:
        size = len(text.encode('utf-8'))
    except UnicodeError:
        raise CLIInputError('lyrics must contain valid UTF-8 text') from None
    if size > MAX_LYRICS_BYTES:
        raise CLIInputError('lyrics exceed 64 KiB UTF-8')
    return text, source_path


def _validate_output(args, lyrics_path):
    name = args.output
    if (not name or Path(name).name != name or '/' in name or '\\' in name
            or Path(name).suffix.lower() != '.mp4'
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise CLIInputError('--output must be a .mp4 basename; choose the directory with --output-dir')
    target = (args.output_dir / name).resolve()
    for source in (lyrics_path, Path(args.audio) if args.audio else None):
        if source is not None and source.resolve() == target:
            raise CLIInputError('output must not overwrite a supplied input file')


def _validate_audio(path):
    if path is None:
        return
    if not path or not Path(path).is_file():
        raise CLIInputError('supplied audio must be a readable regular local file')
    with Path(path).open('rb') as source:
        source.read(1)


def _message(value):
    return ''.join(char if char.isprintable() else ' ' for char in str(value))[:512]


def _error(code, message, json_mode, metadata=None):
    result = {'success': False, 'error': {'code': code, 'message': _message(message)}}
    if metadata is not None:
        result['metadata'] = metadata
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    else:
        print('Local procedural preview failed: ' + result['error']['message'], file=sys.stderr)
    return 1 if code != 'INVALID_INPUT' else 2


def _metadata(result):
    metadata = result.metadata
    if not isinstance(metadata, dict):
        raise ValueError('preview returned invalid metadata')
    if 'render_kind' in metadata and metadata['render_kind'] != 'procedural_preview':
        raise ValueError('result is not a procedural preview')
    for field in ('is_generated_ai_video', 'vocals_generated', 'lipsync_rendered', 'character_image_used', 'theme_applied'):
        if field in metadata and metadata[field] is not False:
            raise ValueError('preview metadata contradicts supported local capabilities')
    for field in ('subtitles_burned', 'duration_verified', 'theme_applied'):
        if field in metadata and type(metadata[field]) is not bool:
            raise ValueError('preview returned an invalid capability flag')
    if 'visual_source' in metadata and metadata['visual_source'] != 'procedural_placeholder':
        raise ValueError('preview returned an unsupported visual source')
    if 'audio_source' in metadata and metadata['audio_source'] not in ('provided_audio', 'synthetic_beat'):
        raise ValueError('preview returned an unsupported audio source')
    # Validate serialization before any output so --json is one valid document.
    json.dumps(metadata, ensure_ascii=False, allow_nan=False).encode('utf-8')
    return metadata


def _flag(metadata, name):
    return 'yes' if metadata.get(name) is True else 'no' if metadata.get(name) is False else 'unknown'


def _print_preview(result, metadata):
    print('Local procedural preview completed. This is not AI video generation.')
    print('   Output: ' + str(result.output_video_path))
    print(f'   Duration: {result.duration_seconds:.2f}s | Bars: {result.total_bars}')
    print('   Visual source: ' + str(metadata.get('visual_source', 'unknown')))
    sources = {'provided_audio': 'provided source audio (content not independently verified)',
               'synthetic_beat': 'synthetic instrumental beat; no generated vocals'}
    print('   Audio source: ' + sources.get(metadata.get('audio_source'), 'unknown'))
    print('   AI vocals generated: ' + _flag(metadata, 'vocals_generated')
          + ' | Lip-sync rendered: ' + _flag(metadata, 'lipsync_rendered')
          + ' | Character image used: ' + _flag(metadata, 'character_image_used'))
    print('   Subtitles burned: ' + _flag(metadata, 'subtitles_burned')
          + ' | Duration verified: ' + _flag(metadata, 'duration_verified'))
    if 'requested_theme' in metadata:
        print('   Requested theme: ' + _message(metadata['requested_theme'])
              + ' | Theme applied: ' + _flag(metadata, 'theme_applied'))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_mode = '--json' in arguments
    parser = _parser()
    try:
        args = parser.parse_args(arguments)
    except CLIInputError as exc:
        return _error('INVALID_INPUT', exc, json_mode)
    if args.command == 'version':
        from airap import __version__
        print(json.dumps({'version': __version__}) if args.json else f'AIRapStudio version {__version__}')
        return 0
    if args.command not in ('preview', 'generate'):
        if json_mode:
            return _error('INVALID_INPUT', 'choose preview, generate or version', True)
        parser.print_help()
        return 2
    try:
        if not math.isfinite(args.bpm) or not 40 <= args.bpm <= 300:
            raise CLIInputError('BPM must be finite and between 40 and 300')
        lyrics, lyrics_path = _lyrics_input(args)
        _validate_audio(args.audio)
        _validate_output(args, lyrics_path)
        request = RapVideoGenerationRequest(lyrics_text=lyrics, bpm=args.bpm, theme=args.theme,
                                            audio_path=args.audio, output_filename=args.output,
                                            aspect_ratio=args.aspect)
        orchestrator = RapPipelineOrchestrator(config=ProjectConfig(output_dir=args.output_dir))
        result = orchestrator.run(request)
    except (ValueError, OSError) as exc:
        return _error('INVALID_INPUT', exc, json_mode)
    except Exception as exc:
        return _error('PREVIEW_FAILED', exc, json_mode)
    try:
        metadata = _metadata(result)
        if result.success is not True:
            reason = metadata.get('error') or 'renderer reported an unsuccessful result'
            return _error('PREVIEW_FAILED', reason, json_mode, metadata)
        if not isinstance(result.duration_seconds, (float, int)) or isinstance(result.duration_seconds, bool):
            raise ValueError('preview returned invalid duration')
        if not math.isfinite(result.duration_seconds) or result.duration_seconds <= 0:
            raise ValueError('preview returned invalid duration')
        output = {'success': True, 'output_video_path': result.output_video_path,
                  'duration_seconds': result.duration_seconds, 'total_bars': result.total_bars,
                  'bpm': result.bpm, 'metadata': metadata}
        encoded = json.dumps(output, ensure_ascii=False, allow_nan=False)
        if json_mode:
            print(encoded)
        else:
            _print_preview(result, metadata)
        return 0
    except Exception as exc:
        return _error('INVALID_RESULT', exc, json_mode)


if __name__ == '__main__':
    raise SystemExit(main())
