"""End-to-end integration tests for AIRapStudio pipeline and CLI."""

import os
from pathlib import Path
import pytest

from airap.config import ProjectConfig
from airap.pipeline import (
    RapPipelineOrchestrator,
    RapVideoGenerationRequest,
    RapVideoGenerationResult,
)


@pytest.fixture
def temp_project_dir(tmp_path):
    output_dir = tmp_path / "test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def test_rap_pipeline_end_to_end(temp_project_dir):
    """Test full pipeline execution producing an actual rendered MP4 video."""
    config = ProjectConfig(output_dir=temp_project_dir)
    orchestrator = RapPipelineOrchestrator(config=config)

    sample_lyrics = """
    Spitting code in the digital haze
    Fast flow navigating the cyber maze
    Kick and the snare on the eighty-eight
    AI rap studio opens up the gate
    """

    req = RapVideoGenerationRequest(
        lyrics_text=sample_lyrics,
        bpm=130.0,
        theme="cyberpunk_street",
        aspect_ratio="9:16",
        output_filename="test_mv.mp4",
    )

    result = orchestrator.run(req)

    assert isinstance(result, RapVideoGenerationResult)
    assert result.success is True
    assert result.total_bars >= 4
    assert result.duration_seconds > 0

    # Verify physical file existence
    output_path = Path(result.output_video_path)
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    # Verify generated subtitle and beat files exist
    assert Path(result.metadata["subtitle_path"]).exists()
    assert Path(result.metadata["audio_path"]).exists()


def test_rap_pipeline_16_9_horizontal(temp_project_dir):
    """Test full pipeline execution in 16:9 horizontal aspect ratio."""
    config = ProjectConfig(output_dir=temp_project_dir)
    orchestrator = RapPipelineOrchestrator(config=config)

    sample_lyrics = """
    Wide screen perspective glowing in neon blue
    Dropping heavy bars for the entire crew
    """

    req = RapVideoGenerationRequest(
        lyrics_text=sample_lyrics,
        bpm=120.0,
        theme="dark_trap",
        aspect_ratio="16:9",
        output_filename="test_mv_16_9.mp4",
    )

    result = orchestrator.run(req)

    assert result.success is True
    assert Path(result.output_video_path).exists()
    assert result.metadata["aspect_ratio"] == "16:9"
