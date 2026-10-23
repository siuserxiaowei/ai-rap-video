"""AIRap Audio & Beat DSP Processing Subsystem.

Contains:
- beat_detector: BeatGrid generator, onset/energy detection, synthetic rap beat generator
- stem_separator: StemSeparator interface, MockStemSeparator, Demucs/UVR5 CLI adapters
- vocal_aligner: WordInterval/PhonemeInterval models, rule-based forced aligner
"""

from airap.audio.beat_detector import (
    BeatDetector,
    BeatEvent,
    BeatGrid,
    BeatType,
    DetectionResult,
    SyntheticRapBeatGenerator,
    compute_energy_curve,
    compute_rms,
    detect_transients,
    estimate_bpm,
    generate_808_kick,
    generate_beat_grid,
    generate_hihat,
    generate_snare,
    read_wav,
    write_wav,
)
from airap.audio.stem_separator import (
    DemucsCLIAdapter,
    MockStemSeparator,
    SeparationResult,
    StemSeparator,
    StemType,
    UVR5CLIAdapter,
)
from airap.audio.vocal_aligner import (
    AlignmentResult,
    PhonemeInterval,
    RuleBasedAligner,
    WordInterval,
    align_lyrics,
    decompose_word_to_phonemes,
)

__all__ = [
    # Beat Detection & Grid
    "BeatType",
    "BeatEvent",
    "BeatGrid",
    "generate_beat_grid",
    "DetectionResult",
    "BeatDetector",
    "compute_rms",
    "compute_energy_curve",
    "detect_transients",
    "estimate_bpm",
    # Audio I/O
    "read_wav",
    "write_wav",
    # Synthesis
    "generate_808_kick",
    "generate_snare",
    "generate_hihat",
    "SyntheticRapBeatGenerator",
    # Stem Separation
    "StemType",
    "SeparationResult",
    "StemSeparator",
    "MockStemSeparator",
    "DemucsCLIAdapter",
    "UVR5CLIAdapter",
    # Vocal Alignment
    "PhonemeInterval",
    "WordInterval",
    "AlignmentResult",
    "RuleBasedAligner",
    "align_lyrics",
    "decompose_word_to_phonemes",
]
