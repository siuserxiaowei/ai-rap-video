#!/usr/bin/env python3
# coding: utf-8
"""Verify real timed Chinese captions, explicit CLI tools, streams and decode."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from airap.compositor.video_builder import VideoBuilder
from airap.config import VideoConfig
from airap.director.timeline import CutPoint, ShotType, Timeline
from verify_engine_preview import digest, invoke, validate_output


def frame_rgb(ffmpeg, filename, timestamp, width, height):
    result = subprocess.run(
        [ffmpeg, '-v', 'error', '-ss', str(timestamp), '-i', str(filename),
         '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
        check=True, capture_output=True, timeout=30,
    )
    assert len(result.stdout) == width * height * 3, 'Decoded frame dimensions differ'
    return result.stdout


def write_frame_png(filename, rgb, width, height):
    """Losslessly encode the actual decoded frame; no text is drawn here."""
    def chunk(kind, content):
        return struct.pack('>I', len(content)) + kind + content + struct.pack('>I', zlib.crc32(kind + content))
    rows = b''.join(b'\0' + rgb[start:start + width * 3]
                    for start in range(0, len(rgb), width * 3))
    data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
    filename.write_bytes(data)


def pixel_difference(left, right, width, height):
    changed = [index for index in range(width * height)
               if left[index * 3:index * 3 + 3] != right[index * 3:index * 3 + 3]]
    bounds = None
    if changed:
        xs, ys = [value % width for value in changed], [value // width for value in changed]
        bounds = [min(xs), min(ys), max(xs), max(ys)]
    return {'changed_pixels': len(changed), 'bounds_xyxy': bounds}


def controlled_caption(ffmpeg, ffprobe, font, media):
    folder = media / "controlled output's [中],:v1"
    folder.mkdir(parents=True, exist_ok=True)
    caption = folder / "caption's [中文],:mix\\take.ass"
    caption.write_text(f'''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,20,20,35,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.25,0:00:00.75,Default,,0,0,0,,中文烧录预览
''', encoding='utf-8')
    builder = VideoBuilder(VideoConfig(width=640, height=360, fps=30, preset='ultrafast', crf=0),
                           ffmpeg_bin=ffmpeg, ffprobe_bin=ffprobe)
    source = folder / 'black-source.mp4'
    builder.synthetic_gen.generate_clip(str(source), duration=1, width=640, height=360,
                                        fps=30, pattern_type='color', color='black')
    timeline = Timeline(duration=1)
    timeline.video_track.cuts = [CutPoint(0, 1, ShotType.CLOSE_UP, source_clip=str(source))]
    off, required = folder / 'off.mp4', folder / 'required.mp4'
    baseline = builder.build_video(timeline, ass_subtitle_path=str(caption),
                                    output_path=str(off), burn_subtitles=False, enable_effects=False)
    burned = builder.build_video(timeline, ass_subtitle_path=str(caption),
                                  output_path=str(required), burn_subtitles=True, enable_effects=False)
    assert baseline.subtitles_burned is False and burned.subtitles_burned is True
    assert baseline.duration_verified and burned.duration_verified
    samples = []
    image = media / 'controlled-chinese-frame.png'
    for timestamp in (0.1, 0.5, 0.9):
        plain = frame_rgb(ffmpeg, off, timestamp, 640, 360)
        actual = frame_rgb(ffmpeg, required, timestamp, 640, 360)
        difference = pixel_difference(plain, actual, 640, 360)
        if timestamp == 0.5:
            assert 500 < difference['changed_pixels'] < 640 * 360 // 2
            assert difference['bounds_xyxy'][1] > 180
            write_frame_png(image, actual, 640, 360)
        else:
            assert difference['changed_pixels'] == 0, 'Caption changed frames outside its event'
        samples.append(dict(timestamp=timestamp, **difference))
    for filename in (off, required):
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(filename), '-map', '0:v:0',
                        '-map', '0:a:0', '-f', 'null', '-'], check=True,
                       capture_output=True, timeout=30)
    return {'status': 'passed', 'source': 'synthetic_black', 'caption_text': '中文烧录预览',
            'event_seconds': [0.25, 0.75], 'samples': samples,
            'off_subtitles_burned': False, 'required_subtitles_burned': True,
            'full_audio_video_decode': 'passed', 'required_video': str(required),
            'required_sha256': digest(required), 'frame_png': str(image), 'frame_sha256': digest(image)}


def cli_cases(python, ffmpeg, ffprobe, font, media):
    folder = media / "CLI examples' 中文[,]:v1"
    folder.mkdir(parents=True, exist_ok=True)
    lyrics = folder / 'lyrics-中文.txt'
    lyrics.write_text('中文烧录预览\n', encoding='utf-8')
    common = ['--lyrics-file', str(lyrics), '--bpm', '240', '--output-dir', str(folder),
              '--ffmpeg', ffmpeg, '--ffprobe', ffprobe, '--subtitle-font', font]
    cases = []
    for name, aspect, dimensions, mode in (
        ('portrait-required', '9:16', (1080, 1920), 'required'),
        ('landscape-required', '16:9', (1920, 1080), 'required'),
        ('portrait-auto', '9:16', (1080, 1920), 'auto'),
        ('portrait-off', '9:16', (1080, 1920), 'off'),
    ):
        arguments = ['preview', *common, '--aspect', aspect, '--subtitle-mode', mode,
                     '--output', name + '.mp4']
        result = invoke(python, arguments)
        assert result['metadata']['subtitle_mode'] == mode
        assert result['metadata']['subtitle_font_requested'] == font
        assert result['metadata']['subtitles_burned'] is (mode != 'off')
        filename = folder / (name + '.mp4')
        item = validate_output(filename, result, dimensions, 'synthetic_beat', ffmpeg, ffprobe)
        item.update(name=name, mode=mode, font_requested=font, video=str(filename),
                    argv=[python, '-m', 'airap.cli', *arguments, '--json'])
        if mode == 'required':
            picture = media / (name + '-frame.png')
            write_frame_png(picture, frame_rgb(ffmpeg, filename, 0.5, *dimensions), *dimensions)
            item.update(frame_png=str(picture), frame_sha256=digest(picture))
        cases.append(item)

    previous = folder / 'portrait-required.mp4'
    previous_hash = digest(previous)
    before = {str(item.relative_to(folder)) for item in folder.rglob('*')}
    # This fixture deliberately selects the documented existing no-ASS binary.
    failure = invoke(python, ['preview', *common, '--subtitle-mode', 'required',
                             '--ffmpeg', '/opt/homebrew/bin/ffmpeg',
                             '--ffprobe', '/opt/homebrew/bin/ffprobe',
                             '--output', previous.name], expected_success=False)
    assert digest(previous) == previous_hash
    assert before == {str(item.relative_to(folder)) for item in folder.rglob('*')}
    return cases, {'unsupported_required_rejected': not failure['success'],
                   'existing_output_preserved': True, 'no_new_assets_on_preflight_failure': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    parser.add_argument('--font', default='Arial Unicode MS')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--media-dir', required=True, type=Path)
    parser.add_argument('--artifact', required=True, type=Path)
    args = parser.parse_args()
    media = args.media_dir.resolve()
    media.mkdir(parents=True, exist_ok=True)
    control = controlled_caption(args.ffmpeg, args.ffprobe, args.font, media)
    cases, failure = cli_cases(args.python, args.ffmpeg, args.ffprobe, args.font, media)
    proof = {'status': 'passed', 'checked_at': datetime.now(timezone.utc).isoformat(),
             'kind': 'real_ASS_pixels_and_CLI_decode', 'controlled_caption': control,
             'cli_cases': cases, 'failure_case': failure, 'synthetic_assets_only': True,
             'provider_requests': 0, 'paid_generations': 0, 'browser_verification': False,
             'media_committed': False, 'media_retained_locally_for_review': True,
             'visual_review': {'status': 'pending_human_image_inspection',
                               'scope': 'Synthetic caption media frames; no browser/UI verification'}}
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
