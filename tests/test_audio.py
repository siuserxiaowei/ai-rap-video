"""Comprehensive test suite for AIRap Audio & Beat DSP processing subsystem."""

import math
import tempfile
from pathlib import Path

import pytest

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
from airap.config import BeatGridConfig


# =============================================================================
# 1. BeatGrid Generation and Timing Tests
# =============================================================================

class TestBeatGrid:
    def test_basic_grid_generation_120bpm(self):
        """At 120 BPM, quarter notes are spaced exactly 0.5s apart."""
        grid = generate_beat_grid(bpm=120.0, duration=4.0, start_offset=0.0)

        assert grid.bpm == 120.0
        assert grid.quarter_interval == pytest.approx(0.5, rel=1e-4)
        assert grid.eighth_interval == pytest.approx(0.25, rel=1e-4)
        assert grid.sixteenth_interval == pytest.approx(0.125, rel=1e-4)

        # 4 seconds at 0.5s per beat = 9 quarter beats (0.0, 0.5, 1.0, ..., 4.0)
        assert len(grid.beats) == 9
        assert grid.beats[0] == 0.0
        assert grid.beats[1] == 0.5
        assert grid.beats[-1] == 4.0

        # Downbeats every 4 beats: beats 0 (0.0), 4 (2.0), 8 (4.0)
        assert len(grid.downbeats) == 3
        assert grid.downbeats == [0.0, 2.0, 4.0]

        # Eighth notes: 4s / 0.25s + 1 = 17 notes
        assert len(grid.eighth_notes) == 17
        # Sixteenth notes: 4s / 0.125s + 1 = 33 notes
        assert len(grid.sixteenth_notes) == 33

    def test_grid_with_start_offset(self):
        """Offset shifts all beats accordingly."""
        offset = 0.3
        grid = generate_beat_grid(bpm=120.0, duration=2.3, start_offset=offset)
        assert grid.beats[0] == pytest.approx(0.3, abs=1e-4)
        assert grid.beats[1] == pytest.approx(0.8, abs=1e-4)
        assert grid.downbeats[0] == pytest.approx(0.3, abs=1e-4)

    def test_grid_from_config(self):
        """Instantiation via BeatGridConfig."""
        cfg = BeatGridConfig(bpm=140.0, time_signature=(4, 4))
        grid = BeatGrid.from_config(cfg, duration=8.0)
        assert grid.bpm == 140.0
        assert grid.beats_per_bar == 4
        assert len(grid.beats) > 0

    def test_nearest_beat_and_downbeat(self):
        grid = generate_beat_grid(bpm=120.0, duration=4.0)  # beats at 0, 0.5, 1.0, 1.5, 2.0...
        assert grid.get_nearest_beat(0.48) == 0.5
        assert grid.get_nearest_beat(0.22) == 0.0
        assert grid.get_nearest_downbeat(1.8) == 2.0
        assert grid.get_nearest_downbeat(0.9) == 0.0

    def test_quantize(self):
        grid = generate_beat_grid(bpm=120.0, duration=4.0)
        # 1/4 quantize (step = 0.5)
        assert grid.quantize(0.47, "1/4") == 0.5
        assert grid.quantize(0.12, "1/4") == 0.0
        # 1/8 quantize (step = 0.25)
        assert grid.quantize(0.27, "1/8") == 0.25
        # 1/16 quantize (step = 0.125)
        assert grid.quantize(0.13, "1/16") == 0.125
        # 1/1 quantize (downbeat step = 2.0)
        assert grid.quantize(1.9, "1/1") == 2.0

    def test_active_bar_and_beat(self):
        grid = generate_beat_grid(bpm=120.0, duration=8.0)
        bar, beat = grid.get_active_bar_and_beat(2.5)  # 2.5s = 5 beats -> bar 1, beat 1
        assert bar == 1
        assert beat == pytest.approx(1.0, abs=1e-2)

    def test_get_events_in_range(self):
        grid = generate_beat_grid(bpm=120.0, duration=4.0)
        events = grid.get_events_in_range(0.5, 1.0)
        assert len(events) > 0
        assert all(0.5 <= e.time <= 1.0 for e in events)

    def test_invalid_parameters_raise(self):
        with pytest.raises(ValueError, match="BPM must be positive"):
            generate_beat_grid(bpm=-10.0, duration=5.0)
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            generate_beat_grid(bpm=120.0, duration=-1.0)


# =============================================================================
# 2. WAV Audio I/O and RMS Energy Detection Tests
# =============================================================================

class TestWavIOAndEnergy:
    def test_wav_write_and_read_roundtrip(self, tmp_path: Path):
        wav_file = tmp_path / "roundtrip_test.wav"
        original_samples = [0.0, 0.5, -0.5, 0.9, -0.9, 0.0]
        sr = 44100

        write_wav(wav_file, original_samples, sample_rate=sr, num_channels=1)
        assert wav_file.exists()

        read_samples, read_sr = read_wav(wav_file)
        assert read_sr == sr
        assert len(read_samples) == len(original_samples)
        for orig, read in zip(original_samples, read_samples):
            assert read == pytest.approx(orig, abs=0.01)

    def test_stereo_wav_read_converts_to_mono(self, tmp_path: Path):
        wav_file = tmp_path / "stereo_test.wav"
        samples = [0.4, -0.4, 0.8, -0.8]
        write_wav(wav_file, samples, sample_rate=44100, num_channels=2)

        read_samples, sr = read_wav(wav_file)
        assert sr == 44100
        assert len(read_samples) == len(samples)
        for orig, read in zip(samples, read_samples):
            assert read == pytest.approx(orig, abs=0.01)

    def test_read_nonexistent_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_wav(tmp_path / "does_not_exist.wav")

    def test_compute_rms_math(self):
        """RMS of constant DC signal of amplitude A is A."""
        dc_samples = [0.75] * 2048
        rms = compute_rms(dc_samples, frame_size=1024, hop_size=512)
        assert len(rms) > 0
        for val in rms:
            assert val == pytest.approx(0.75, abs=1e-4)

    def test_compute_energy_curve(self):
        samples = [0.5 * math.sin(2 * math.pi * 440 * i / 44100) for i in range(44100)]
        times, energies = compute_energy_curve(samples, sample_rate=44100, normalize=True)
        assert len(times) == len(energies)
        assert len(times) > 0
        assert max(energies) == pytest.approx(1.0, abs=1e-4)
        assert min(energies) >= 0.0


# =============================================================================
# 3. Synthetic Rap Beat Generator Tests
# =============================================================================

class TestSyntheticBeatGenerator:
    def test_generate_808_kick(self):
        sr = 44100
        dur = 0.5
        kick = generate_808_kick(duration=dur, sample_rate=sr)
        assert len(kick) == int(dur * sr)
        assert max(kick) <= 1.0
        assert min(kick) >= -1.0
        # Check non-silent
        assert max(abs(x) for x in kick) > 0.5
        # Check no NaN / Inf
        assert all(math.isfinite(x) for x in kick)

    def test_generate_snare(self):
        sr = 44100
        dur = 0.25
        snare = generate_snare(duration=dur, sample_rate=sr, seed=123)
        assert len(snare) == int(dur * sr)
        assert max(snare) <= 1.0
        assert min(snare) >= -1.0
        assert max(abs(x) for x in snare) > 0.4
        assert all(math.isfinite(x) for x in snare)

    def test_generate_hihat_open_and_closed(self):
        sr = 44100
        closed = generate_hihat(duration=0.05, sample_rate=sr, is_open=False)
        open_hat = generate_hihat(sample_rate=sr, is_open=True)
        assert len(closed) < len(open_hat)
        assert max(abs(x) for x in closed) > 0.1
        assert max(abs(x) for x in open_hat) > 0.1

    def test_full_beat_generation_patterns(self, tmp_path: Path):
        synth = SyntheticRapBeatGenerator(sample_rate=44100)

        for pattern in ["trap", "boom_bap", "basic"]:
            samples = synth.generate_samples(bpm=130.0, duration=2.0, pattern=pattern)
            assert len(samples) == int(2.0 * 44100)
            assert max(samples) <= 1.0
            assert min(samples) >= -1.0
            assert max(abs(x) for x in samples) > 0.3

            # Generate and verify WAV file output
            out_file = tmp_path / f"beat_{pattern}.wav"
            ret_path = synth.generate_wav(out_file, bpm=130.0, duration=2.0, pattern=pattern)
            assert ret_path.exists()

            read_s, read_sr = read_wav(ret_path)
            assert read_sr == 44100
            assert len(read_s) == len(samples)


# =============================================================================
# 4. Beat and Transient Detection Tests
# =============================================================================

class TestBeatDetector:
    def test_transient_detection_on_synthetic_beat(self):
        """Transient detector should reliably identify hits in synthetic beat."""
        synth = SyntheticRapBeatGenerator(sample_rate=44100)
        samples = synth.generate_samples(bpm=120.0, duration=2.0, pattern="basic")

        onsets = detect_transients(samples, sample_rate=44100, threshold=0.15, min_distance_sec=0.1)
        assert len(onsets) >= 3

        # First onset should be near t = 0.0
        assert onsets[0] == pytest.approx(0.0, abs=0.1)

    def test_bpm_estimation(self):
        """Onsets at 0.5s intervals correspond to 120 BPM."""
        regular_onsets = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
        bpm = estimate_bpm(regular_onsets)
        assert bpm == pytest.approx(120.0, abs=2.0)

    def test_beat_detector_end_to_end(self, tmp_path: Path):
        synth = SyntheticRapBeatGenerator(sample_rate=44100)
        wav_path = tmp_path / "detect_test.wav"
        synth.generate_wav(wav_path, bpm=130.0, duration=3.0, pattern="trap")

        detector = BeatDetector(threshold=0.15)
        res = detector.detect_from_file(wav_path, generate_grid=True)

        assert isinstance(res, DetectionResult)
        assert len(res.onset_times) > 0
        assert len(res.energy_times) > 0
        assert len(res.energy_values) == len(res.energy_times)
        assert res.beat_grid is not None
        assert res.estimated_bpm > 0


# =============================================================================
# 5. Stem Separation Tests
# =============================================================================

class TestStemSeparator:
    def test_stem_type_parsing(self):
        assert StemType.from_str("vocal") == StemType.VOCAL
        assert StemType.from_str("vocals") == StemType.VOCAL
        assert StemType.from_str("vox") == StemType.VOCAL
        assert StemType.from_str("drums") == StemType.DRUMS
        assert StemType.from_str("drum") == StemType.DRUMS
        assert StemType.from_str("bass") == StemType.BASS
        assert StemType.from_str("other") == StemType.OTHER
        assert StemType.from_str("instrumental") == StemType.OTHER

        with pytest.raises(ValueError):
            StemType.from_str("unknown_stem")

    def test_mock_stem_separator(self, tmp_path: Path):
        synth = SyntheticRapBeatGenerator(sample_rate=44100)
        wav_path = tmp_path / "source.wav"
        synth.generate_wav(wav_path, bpm=120.0, duration=1.5)

        separator = MockStemSeparator()
        assert separator.is_available() is True

        out_dir = tmp_path / "stems"
        res = separator.separate(wav_path, output_dir=out_dir)

        assert isinstance(res, SeparationResult)
        assert res.success is True
        assert res.duration == pytest.approx(1.5, abs=0.05)

        # Check all 4 stems exist and are non-empty WAVs
        assert res.vocal_path is not None and res.vocal_path.exists()
        assert res.drums_path is not None and res.drums_path.exists()
        assert res.bass_path is not None and res.bass_path.exists()
        assert res.other_path is not None and res.other_path.exists()

        # Verify stem audio readable
        v_samples, v_sr = read_wav(res.vocal_path)
        assert v_sr == 44100
        assert len(v_samples) > 0

    def test_mock_stem_separator_nonexistent_file(self, tmp_path: Path):
        separator = MockStemSeparator()
        res = separator.separate(tmp_path / "missing.wav")
        assert res.success is False
        assert "not found" in res.message.lower()

    def test_demucs_adapter_fallback(self, tmp_path: Path):
        synth = SyntheticRapBeatGenerator(sample_rate=44100)
        wav_path = tmp_path / "demucs_src.wav"
        synth.generate_wav(wav_path, bpm=120.0, duration=1.0)

        # Force nonexistent binary
        adapter = DemucsCLIAdapter(demucs_bin="/nonexistent/bin/demucs", fallback_to_mock=True)
        assert adapter.is_available() is False

        res = adapter.separate(wav_path, output_dir=tmp_path / "demucs_out")
        assert res.success is True
        assert res.vocal_path.exists()
        assert res.drums_path.exists()

    def test_demucs_adapter_raises_without_fallback(self, tmp_path: Path):
        wav_path = tmp_path / "demucs_src2.wav"
        write_wav(wav_path, [0.0] * 1000)

        adapter = DemucsCLIAdapter(demucs_bin="/nonexistent/bin/demucs", fallback_to_mock=False)
        with pytest.raises(RuntimeError):
            adapter.separate(wav_path)

    def test_uvr5_adapter_fallback(self, tmp_path: Path):
        synth = SyntheticRapBeatGenerator(sample_rate=44100)
        wav_path = tmp_path / "uvr_src.wav"
        synth.generate_wav(wav_path, bpm=120.0, duration=1.0)

        adapter = UVR5CLIAdapter(uvr_bin="/nonexistent/bin/uvr5", fallback_to_mock=True)
        assert adapter.is_available() is False

        res = adapter.separate(wav_path, output_dir=tmp_path / "uvr_out")
        assert res.success is True
        assert res.vocal_path.exists()


# =============================================================================
# 6. Vocal Alignment and Phonetic Segmentation Tests
# =============================================================================

class TestVocalAligner:
    def test_decompose_word_to_phonemes(self):
        # English
        p_beat = decompose_word_to_phonemes("beat")
        assert p_beat == ["B", "IY", "T"]

        p_flow = decompose_word_to_phonemes("flow")
        assert p_flow == ["F", "L", "OW"]

        p_rap = decompose_word_to_phonemes("rap")
        assert "R" in p_beat or "R" in p_rap

        # Chinese characters
        p_shuo = decompose_word_to_phonemes("说")
        assert p_shuo == ["SH", "UO"]

        p_chang = decompose_word_to_phonemes("唱")
        assert p_chang == ["CH", "ANG"]

    def test_phoneme_and_word_interval_properties(self):
        p = PhonemeInterval(phoneme="IY", start=0.5, end=0.8, confidence=0.95)
        assert p.duration == pytest.approx(0.3, abs=1e-4)
        p_dict = p.to_dict()
        assert p_dict["phoneme"] == "IY"
        assert p_dict["duration"] == 0.3

        w = WordInterval(word="beat", start=0.4, end=0.9, phonemes=[p])
        assert w.duration == pytest.approx(0.5, abs=1e-4)
        w_dict = w.to_dict()
        assert w_dict["word"] == "beat"
        assert len(w_dict["phonemes"]) == 1

    def test_rule_based_aligner_multiline(self):
        lyrics = """
        Yo drop the beat on the one
        Feel the rhythm we having fun
        Rocking the mic with the flow
        """
        grid = generate_beat_grid(bpm=130.0, duration=8.0)
        aligner = RuleBasedAligner()
        res = aligner.align(lyrics, audio_duration=8.0, beat_grid=grid)

        assert isinstance(res, AlignmentResult)
        assert res.word_count > 0
        assert res.total_duration == 8.0

        # Invariant 1: Word intervals must be strictly monotonically increasing and non-overlapping
        for i in range(len(res.words) - 1):
            assert res.words[i].start < res.words[i].end
            assert res.words[i].end <= res.words[i + 1].start + 1e-4

        # Invariant 2: Last word must not exceed total audio duration
        assert res.words[-1].end <= 8.0 + 1e-4

        # Invariant 3: Phoneme intervals partition the word interval
        for w in res.words:
            assert len(w.phonemes) > 0
            assert w.phonemes[0].start == pytest.approx(w.start, abs=1e-3)
            assert w.phonemes[-1].end == pytest.approx(w.end, abs=1e-3)
            for j in range(len(w.phonemes) - 1):
                assert w.phonemes[j].end == pytest.approx(w.phonemes[j + 1].start, abs=1e-3)

        # Invariant 4: Last word of each line is tagged as rhyme
        rhyme_words = [w.word for w in res.words if w.is_rhyme]
        assert "one" in rhyme_words
        assert "fun" in rhyme_words
        assert "flow" in rhyme_words

    def test_active_word_and_phoneme_lookup(self):
        lyrics = "Rap flow"
        res = align_lyrics(lyrics, audio_duration=3.0)
        assert res.word_count == 2

        first_word = res.words[0]
        mid_time = (first_word.start + first_word.end) / 2.0
        active_w = res.get_active_word(mid_time)
        assert active_w is not None
        assert active_w.word == "Rap"

        active_p = res.get_active_phoneme(mid_time)
        assert active_p is not None

    def test_srt_and_ass_exporters(self):
        lyrics = "Drop the mic\nTake the crown"
        res = align_lyrics(lyrics, audio_duration=4.0)

        srt = res.to_srt()
        assert "00:00:" in srt
        assert "-->" in srt
        assert "Drop the mic" in srt
        assert "Take the crown" in srt

        ass = res.to_ass()
        assert "[Script Info]" in ass
        assert "[Events]" in ass
        assert "Dialogue:" in ass
        assert r"{\k" in ass

    def test_edge_cases_empty_lyrics_and_short_duration(self):
        aligner = RuleBasedAligner()
        empty_res = aligner.align("", audio_duration=5.0)
        assert empty_res.word_count == 0

        zero_res = aligner.align("Hello", audio_duration=0.0)
        assert zero_res.word_count == 0

        single_word = aligner.align("Rap", audio_duration=2.0)
        assert single_word.word_count == 1
        assert single_word.words[0].word == "Rap"
        assert single_word.words[0].end <= 2.0
