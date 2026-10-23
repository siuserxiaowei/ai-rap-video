"""Command Line Interface for AIRapStudio."""

import argparse
import sys
from pathlib import Path

from airap.pipeline import RapPipelineOrchestrator, RapVideoGenerationRequest
from airap.config import ProjectConfig


def main():
    parser = argparse.ArgumentParser(
        description="AIRapStudio: Autonomous AI Rap Video Generation Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate a complete rap music video")
    gen_parser.add_argument("--lyrics", type=str, help="Rap lyrics text or file path", required=True)
    gen_parser.add_argument("--bpm", type=float, default=130.0, help="Tempo in BPM (default: 130)")
    gen_parser.add_argument("--audio", type=str, default=None, help="Path to audio file (optional)")
    gen_parser.add_argument("--theme", type=str, default="cyberpunk_street", help="Visual style theme")
    gen_parser.add_argument("--aspect", choices=["9:16", "16:9"], default="9:16", help="Aspect ratio")
    gen_parser.add_argument("--output", type=str, default="output_rap.mp4", help="Output video file name")

    # Version command
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    if args.command == "version":
        from airap import __version__
        print(f"AIRapStudio version {__version__}")
        sys.exit(0)

    if args.command == "generate":
        lyrics_content = args.lyrics
        if Path(args.lyrics).is_file():
            lyrics_content = Path(args.lyrics).read_text(encoding="utf-8")

        print("🎤 [AIRapStudio] Initiating autonomous generation...")
        print(f"   BPM: {args.bpm} | Aspect Ratio: {args.aspect} | Theme: {args.theme}")

        orchestrator = RapPipelineOrchestrator()
        req = RapVideoGenerationRequest(
            lyrics_text=lyrics_content,
            bpm=args.bpm,
            theme=args.theme,
            audio_path=args.audio,
            output_filename=args.output,
            aspect_ratio=args.aspect
        )

        try:
            result = orchestrator.run(req)
            print("🚀 [AIRapStudio] Rap Video Generation Succeeded!")
            print(f"   Output Video: {result.output_video_path}")
            print(f"   Duration: {result.duration_seconds:.2f}s | Bars: {result.total_bars}")
        except Exception as e:
            print(f"❌ [AIRapStudio] Generation failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
