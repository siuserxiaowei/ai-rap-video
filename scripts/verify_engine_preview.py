#!/usr/bin/env python3
# coding: utf-8
"""Exercise the real local preview CLI, probe/decode outputs, retain no media."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from datetime import datetime, timezone
from fractions import Fraction


ROOT = Path(__file__).resolve().parents[1]


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def invoke(python, arguments, expected_success=True):
    result = subprocess.run(
        [python, '-m', 'airap.cli', *arguments, '--json'], cwd=ROOT,
        capture_output=True, text=True, timeout=120,
    )
    assert (result.returncode == 0) is expected_success, 'Unexpected CLI exit status'
    value = json.loads(result.stdout)
    assert value['success'] is expected_success
    assert 'Traceback' not in result.stderr
    return value


def validate_output(filename, result, dimensions, audio_source, ffmpeg, ffprobe):
    metadata = result['metadata']
    for name in ('is_generated_ai_video', 'vocals_generated', 'lipsync_rendered',
                 'character_image_used', 'theme_applied'):
        assert metadata[name] is False, name
    assert metadata['render_kind'] == 'procedural_preview'
    assert metadata['visual_source'] == 'procedural_placeholder'
    assert metadata['audio_source'] == audio_source
    assert metadata['duration_verified'] is True
    assert type(metadata['subtitles_burned']) is bool
    assert metadata['avatar_frames'] == 0
    assert Path(result['output_video_path']).resolve() == filename.resolve()

    inspected = subprocess.run(
        [ffprobe, '-v', 'error', '-show_streams', '-show_format',
         '-print_format', 'json', str(filename)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    probe = json.loads(inspected.stdout)
    video = next(item for item in probe['streams'] if item['codec_type'] == 'video')
    audio = next(item for item in probe['streams'] if item['codec_type'] == 'audio')
    assert (video['width'], video['height']) == dimensions
    fps = float(Fraction(video['avg_frame_rate']))
    duration = float(video['duration'])
    assert math.isfinite(duration) and duration > 0
    assert math.isclose(fps, 30, rel_tol=0.001)
    assert abs(duration - result['duration_seconds']) < 0.001
    assert abs(duration - metadata['requested_duration']) <= max(0.1, 2 / fps)
    assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac'
    # Decode every audio/video packet. A nonempty/probeable container alone is
    # insufficient evidence that the composed result can actually be decoded.
    decoded = subprocess.run(
        [ffmpeg, '-v', 'error', '-i', str(filename), '-map', '0:v:0',
         '-map', '0:a:0', '-f', 'null', '-'],
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert not decoded.stderr.strip(), 'Decode produced media errors'
    return {
        'dimensions': list(dimensions), 'fps': fps,
        'requested_duration': metadata['requested_duration'],
        'measured_video_duration': duration,
        'video_codec': video['codec_name'], 'audio_codec': audio['codec_name'],
        'file_bytes': filename.stat().st_size, 'sha256': digest(filename),
        'full_audio_video_decode': 'passed', 'audio_source': audio_source,
        'render_kind': metadata['render_kind'],
        'subtitles_burned': metadata['subtitles_burned'],
        'is_generated_ai_video': False, 'lipsync_rendered': False,
        'vocals_generated': False, 'character_image_used': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--artifact', required=True, type=Path)
    args = parser.parse_args()
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    assert ffmpeg and ffprobe, 'FFmpeg and FFprobe are required'
    proof = {
        'kind': 'real_local_cli_ffprobe_decode_smoke', 'status': 'passed',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'synthetic_assets_only': True, 'provider_requests': 0,
        'browser_verification': False, 'media_retained': False,
        'cases': [],
    }
    with tempfile.TemporaryDirectory(prefix='airap preview acceptance ') as folder:
        output_dir = Path(folder)
        lyrics = output_dir / 'synthetic lyrics.txt'
        lyrics.write_text('节拍落在代码里 这是本机合成预览\n', encoding='utf-8')
        audio_file = output_dir / 'synthetic tone.wav'
        with wave.open(str(audio_file), 'wb') as audio:
            audio.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
            audio.writeframes(b''.join(
                struct.pack('<h', int(5000 * math.sin(2 * math.pi * 440 * index / 44100)))
                for index in range(44100)
            ))
        common = ['--lyrics-file', str(lyrics), '--bpm', '240',
                  '--output-dir', str(output_dir)]
        for command, aspect, name, dimensions, supplied in (
            ('preview', '9:16', 'portrait.mp4', (1080, 1920), False),
            ('generate', '16:9', 'landscape.mp4', (1920, 1080), True),
        ):
            arguments = [command, *common, '--aspect', aspect, '--output', name]
            if supplied:
                arguments.extend(['--audio', str(audio_file)])
            result = invoke(args.python, arguments)
            proof['cases'].append(validate_output(
                output_dir / name, result, dimensions,
                'provided_audio' if supplied else 'synthetic_beat', ffmpeg, ffprobe,
            ))
        previous = digest(output_dir / 'portrait.mp4')
        missing = invoke(args.python, [
            'preview', *common, '--output', 'portrait.mp4',
            '--audio', str(output_dir / 'does-not-exist.wav'),
        ], expected_success=False)
        assert digest(output_dir / 'portrait.mp4') == previous
        invalid = invoke(args.python, [
            'preview', *common, '--output', 'invalid.mp4', '--bpm', 'nan',
        ], expected_success=False)
        assert not (output_dir / 'invalid.mp4').exists()
        proof['failure_cases'] = {
            'missing_audio_rejected': not missing['success'],
            'existing_output_preserved': True,
            'nonfinite_bpm_rejected': not invalid['success'],
        }
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n',
                             encoding='utf-8')
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
