"""Comprehensive unit and integration tests for AIRap Avatar & LipSync Engine.

Tests:
1. Phoneme to Viseme mapping (English ARPABET, Chinese Pinyin, syllables, silences)
2. Fast-cadence transition smoothing and co-articulation filter (140+ BPM anti-twitching)
3. Head motion transforms, Euler angles, quaternions, and beat-synced HeadBobber
4. Poisson eye-blink generator
5. FrameAvatarState data model serialization
6. LipSyncEngine adapters (LivePortrait, Hedra, Wav2Lip)
7. Deterministic MockLipSyncRenderer and headless manifest generation
"""

import math
from pathlib import Path
import pytest

from airap.avatar import (
    BlinkGenerator,
    CoArticulationFilter,
    EulerAngles,
    FrameAvatarState,
    HeadBobber,
    HeadMotionState,
    HedraAdapter,
    LivePortraitAdapter,
    MockLipSyncRenderer,
    PhonemeVisemeMapper,
    TimedPhoneme,
    TimedViseme,
    Viseme,
    Wav2LipAdapter,
)


# ==============================================================================
# 1. Phoneme to Viseme Mapping Tests
# ==============================================================================

class TestPhonemeVisemeMapping:
    """Test bi-lingual phoneme mapping for English and Chinese."""

    @pytest.fixture
    def mapper(self) -> PhonemeVisemeMapper:
        return PhonemeVisemeMapper()

    def test_english_arpabet_vowels(self, mapper: PhonemeVisemeMapper):
        """Verify standard English ARPABET vowels map to appropriate Visemes."""
        assert mapper.map_phoneme("AA") == Viseme.AA
        assert mapper.map_phoneme("AH") == Viseme.AA
        assert mapper.map_phoneme("AY") == Viseme.AA
        assert mapper.map_phoneme("AE") == Viseme.IH
        assert mapper.map_phoneme("EH") == Viseme.IH
        assert mapper.map_phoneme("ER") == Viseme.IH
        assert mapper.map_phoneme("IH") == Viseme.IH
        assert mapper.map_phoneme("EY") == Viseme.EE
        assert mapper.map_phoneme("IY") == Viseme.EE
        assert mapper.map_phoneme("AO") == Viseme.OH
        assert mapper.map_phoneme("OY") == Viseme.OH
        assert mapper.map_phoneme("AW") == Viseme.OU
        assert mapper.map_phoneme("OW") == Viseme.OU
        assert mapper.map_phoneme("UW") == Viseme.OU

    def test_english_arpabet_stress_digits(self, mapper: PhonemeVisemeMapper):
        """Verify trailing ARPABET stress numbers (0, 1, 2) are stripped correctly."""
        assert mapper.map_phoneme("AA1") == Viseme.AA
        assert mapper.map_phoneme("IY0") == Viseme.EE
        assert mapper.map_phoneme("UW2") == Viseme.OU
        assert mapper.map_phoneme("T1") == Viseme.TD
        assert mapper.map_phoneme("B0") == Viseme.MBP

    def test_english_consonants(self, mapper: PhonemeVisemeMapper):
        """Verify English consonant classifications."""
        # Bilabials
        assert mapper.map_phoneme("B") == Viseme.MBP
        assert mapper.map_phoneme("P") == Viseme.MBP
        assert mapper.map_phoneme("M") == Viseme.MBP
        # Labiodentals
        assert mapper.map_phoneme("F") == Viseme.FV
        assert mapper.map_phoneme("V") == Viseme.FV
        # Dentals
        assert mapper.map_phoneme("TH") == Viseme.TH
        assert mapper.map_phoneme("DH") == Viseme.TH
        # Alveolars
        assert mapper.map_phoneme("T") == Viseme.TD
        assert mapper.map_phoneme("D") == Viseme.TD
        assert mapper.map_phoneme("S") == Viseme.TD
        assert mapper.map_phoneme("Z") == Viseme.TD
        assert mapper.map_phoneme("N") == Viseme.TD
        assert mapper.map_phoneme("L") == Viseme.TD
        # Velars
        assert mapper.map_phoneme("K") == Viseme.KG
        assert mapper.map_phoneme("G") == Viseme.KG
        assert mapper.map_phoneme("NG") == Viseme.KG
        # Affricates
        assert mapper.map_phoneme("CH") == Viseme.CH_SH
        assert mapper.map_phoneme("SH") == Viseme.CH_SH
        assert mapper.map_phoneme("ZH") == Viseme.CH_SH

    def test_silence_and_pauses(self, mapper: PhonemeVisemeMapper):
        """Verify pauses and whitespace return SIL."""
        assert mapper.map_phoneme("SIL") == Viseme.SIL
        assert mapper.map_phoneme("SP") == Viseme.SIL
        assert mapper.map_phoneme("PAUSE") == Viseme.SIL
        assert mapper.map_phoneme("") == Viseme.SIL
        assert mapper.map_phoneme("   ") == Viseme.SIL

    def test_chinese_pinyin_initials_and_finals(self, mapper: PhonemeVisemeMapper):
        """Verify Chinese Pinyin initials and finals map to standard Visemes."""
        # Initials
        assert mapper.map_phoneme("b") == Viseme.MBP
        assert mapper.map_phoneme("m") == Viseme.MBP
        assert mapper.map_phoneme("f") == Viseme.FV
        assert mapper.map_phoneme("d") == Viseme.TD
        assert mapper.map_phoneme("g") == Viseme.KG
        assert mapper.map_phoneme("j") == Viseme.CH_SH
        assert mapper.map_phoneme("zh") == Viseme.CH_SH
        # Finals
        assert mapper.map_phoneme("a") == Viseme.AA
        assert mapper.map_phoneme("ia") == Viseme.AA
        assert mapper.map_phoneme("o") == Viseme.OH
        assert mapper.map_phoneme("uo") == Viseme.OH
        assert mapper.map_phoneme("e") == Viseme.EE
        assert mapper.map_phoneme("ou") == Viseme.OU
        assert mapper.map_phoneme("ang") == Viseme.AA
        assert mapper.map_phoneme("eng") == Viseme.OH
        assert mapper.map_phoneme("i") == Viseme.EE
        assert mapper.map_phoneme("u") == Viseme.OU

    def test_chinese_pinyin_syllables(self, mapper: PhonemeVisemeMapper):
        """Verify full Chinese pinyin syllables resolve to proper mouth shapes."""
        assert mapper.map_phoneme("shuo") == Viseme.OH  # final uo -> OH
        assert mapper.map_phoneme("rap") == Viseme.AA   # vowel a -> AA
        assert mapper.map_phoneme("da") == Viseme.AA    # final a -> AA
        assert mapper.map_phoneme("ni") == Viseme.EE    # final i -> EE
        assert mapper.map_phoneme("ku") == Viseme.OU    # final u -> OU
        assert mapper.map_phoneme("zhe") == Viseme.EE   # final e -> EE

    def test_map_timed_phonemes(self, mapper: PhonemeVisemeMapper):
        """Verify batch mapping of TimedPhoneme sequence."""
        timed_inputs = [
            TimedPhoneme(phoneme="B", start=0.0, end=0.1, stress=1.0),
            TimedPhoneme(phoneme="AA", start=0.1, end=0.3, stress=1.2),
            TimedPhoneme(phoneme="T", start=0.3, end=0.4, stress=1.0),
        ]
        visemes = mapper.map_timed_phonemes(timed_inputs)
        assert len(visemes) == 3
        assert visemes[0].viseme == Viseme.MBP
        assert visemes[1].viseme == Viseme.AA
        # Stress on AA should amplify mouth_open
        assert visemes[1].mouth_open > 0.90
        assert visemes[2].viseme == Viseme.TD


# ==============================================================================
# 2. Transition Smoothing & Co-articulation Filter Tests
# ==============================================================================

class TestCoArticulationFilter:
    """Test co-articulation smoothing at rapid 140+ BPM tempos."""

    def test_target_undershoot(self):
        """Verify rapid phonemes (<80ms) undergo target undershoot."""
        f = CoArticulationFilter(undershoot_min_duration=0.10)
        # For a full duration (150ms), target remains uncompressed
        open_full, wide_full = f.apply_undershoot(0.90, 0.50, duration=0.15)
        assert open_full == 0.90
        assert wide_full == 0.50

        # For an ultra-fast rap triplet (40ms), target should be compressed towards neutral
        open_short, wide_short = f.apply_undershoot(0.90, 0.50, duration=0.04)
        assert open_short < 0.90
        assert open_short > 0.40  # still distinct, but damped

    def test_cadence_smoothing_prevents_mouth_twitching(self):
        """Verify rapid alternation between AA (0.9) and MBP (0.0) is smoothed."""
        f = CoArticulationFilter(bpm=150.0, max_delta_per_second=7.0)

        # Simulate 10 frames at 30fps rapidly oscillating 0.9 -> 0.0 -> 0.9 -> 0.0
        fps = 30
        dt = 1.0 / fps
        timestamps = [i * dt for i in range(12)]
        raw_targets = [(0.90, 0.50) if i % 2 == 0 else (0.00, 0.30) for i in range(12)]

        smoothed = f.smooth_sequence(raw_targets, timestamps, bpm=150.0)
        assert len(smoothed) == len(raw_targets)

        # Check that maximum single-frame delta is capped by slew rate limiter
        max_allowed_delta = f.max_delta_per_second * dt + 1e-4
        for i in range(1, len(smoothed)):
            delta_open = abs(smoothed[i][0] - smoothed[i - 1][0])
            assert delta_open <= max_allowed_delta, (
                f"Frame {i} delta {delta_open:.4f} exceeded max allowed {max_allowed_delta:.4f}"
            )

    def test_filter_timed_visemes_continuous(self):
        """Verify filter_timed_visemes produces valid [0..1] range values."""
        f = CoArticulationFilter(bpm=140.0)
        timed = [
            TimedViseme(Viseme.SIL, 0.0, 0.1, 0.0, 0.0),
            TimedViseme(Viseme.AA, 0.1, 0.25, 0.9, 0.5),
            TimedViseme(Viseme.MBP, 0.25, 0.35, 0.0, 0.3),
            TimedViseme(Viseme.EE, 0.35, 0.5, 0.3, 0.9),
        ]
        frames = f.filter_timed_visemes(timed, total_duration=0.5, fps=30, bpm=140.0)
        assert len(frames) == 15  # 0.5s * 30fps = 15 frames

        for open_val, wide_val, vis in frames:
            assert 0.0 <= open_val <= 1.0
            assert 0.0 <= wide_val <= 1.0
            assert isinstance(vis, Viseme)


# ==============================================================================
# 3. Head Motion & Rotational Transform Tests
# ==============================================================================

class TestRotationalTransforms:
    """Test 3D Euler angles, rotation matrices, quaternions, and vectors."""

    def test_identity_rotation(self):
        """Zero Euler angles should yield 3x3 identity matrix and unit quaternion."""
        angles = EulerAngles(pitch=0.0, yaw=0.0, roll=0.0)
        mat = angles.to_rotation_matrix()
        # Identity matrix check
        expected = (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
        assert mat == expected

        # Quaternion check: w=1, x=0, y=0, z=0
        q = angles.to_quaternion()
        assert q == (1.0, 0.0, 0.0, 0.0)

    def test_matrix_orthogonality(self):
        """Rotation matrix M * M^T must equal Identity."""
        angles = EulerAngles(pitch=15.0, yaw=-10.0, roll=5.0)
        m = angles.to_rotation_matrix()

        # Compute M * M^T
        for i in range(3):
            for j in range(3):
                dot = sum(m[i][k] * m[j][k] for k in range(3))
                expected = 1.0 if i == j else 0.0
                assert math.isclose(dot, expected, abs_tol=1e-4)

    def test_quaternion_unit_norm(self):
        """Quaternion must be normalized: w^2 + x^2 + y^2 + z^2 == 1.0."""
        angles = EulerAngles(pitch=22.5, yaw=-18.0, roll=7.5)
        w, x, y, z = angles.to_quaternion()
        norm_sq = w * w + x * x + y * y + z * z
        assert math.isclose(norm_sq, 1.0, abs_tol=1e-5)

    def test_vector_rotation(self):
        """Rotating a vector along primary axes produces correct result."""
        # 90 degrees yaw (turning right around Y)
        angles = EulerAngles(pitch=0.0, yaw=90.0, roll=0.0)
        v = (1.0, 0.0, 0.0)
        rv = angles.rotate_vector(v)
        # In our coordinate system, rotating X vector by 90 yaw puts it onto -Z
        assert math.isclose(rv[0], 0.0, abs_tol=1e-4)
        assert math.isclose(rv[1], 0.0, abs_tol=1e-4)
        assert math.isclose(rv[2], -1.0, abs_tol=1e-4)

    def test_euler_lerp(self):
        """Linear interpolation between two head orientations."""
        a = EulerAngles(pitch=0.0, yaw=0.0, roll=0.0)
        b = EulerAngles(pitch=10.0, yaw=20.0, roll=30.0)
        mid = a.lerp(b, 0.5)
        assert math.isclose(mid.pitch, 5.0)
        assert math.isclose(mid.yaw, 10.0)
        assert math.isclose(mid.roll, 15.0)


class TestHeadBobber:
    """Test rap head nod generator synced to musical tempo."""

    def test_downbeat_dip_and_upbeat_raise(self):
        """Downbeats must trigger downward head dip (high pitch); upbeats raise head (low pitch)."""
        bpm = 120.0
        bobber = HeadBobber(bpm=bpm, intensity=1.0, base_pitch=2.0, pitch_amplitude=8.0)
        bp = bobber.beat_period  # 60 / 120 = 0.5 seconds

        # Test over 4 beats
        for beat_num in range(4):
            downbeat_time = beat_num * bp
            upbeat_time = downbeat_time + (bp / 2.0)

            motion_down = bobber.get_motion_at(downbeat_time)
            motion_up = bobber.get_motion_at(upbeat_time)

            # Downbeat pitch must be strictly greater than upbeat pitch (nod down vs raise up)
            assert motion_down.pitch > motion_up.pitch, (
                f"Beat {beat_num}: Downbeat pitch {motion_down.pitch} not > upbeat pitch {motion_up.pitch}"
            )
            # Downbeat pitch should dip significantly above resting base_pitch
            assert motion_down.pitch > bobber.base_pitch + 4.0

    def test_bar_accentuation(self):
        """Beat 1 (downbeat) should have stronger nod accent than offbeat beat 2."""
        bpm = 140.0
        bobber = HeadBobber(bpm=bpm)
        bp = bobber.beat_period

        # Beat 0 is the primary 1st downbeat of the bar
        pitch_beat0 = bobber.get_motion_at(0 * bp).pitch
        # Beat 1 is secondary offbeat
        pitch_beat1 = bobber.get_motion_at(1 * bp).pitch

        assert pitch_beat0 > pitch_beat1

    def test_generate_timeline(self):
        """Timeline generation outputs correct number of frames."""
        bobber = HeadBobber(bpm=130.0)
        timeline = bobber.generate_timeline(duration=1.0, fps=30)
        assert len(timeline) == 30
        assert all(isinstance(f, HeadMotionState) for f in timeline)


# ==============================================================================
# 4. Poisson Eye-Blink Generator Tests
# ==============================================================================

class TestBlinkGenerator:
    """Test Poisson eye-blink distribution and deterministic kinematics."""

    def test_deterministic_seed(self):
        """Same seed must produce identical blink timelines."""
        b1 = BlinkGenerator(seed=12345)
        b2 = BlinkGenerator(seed=12345)
        t1 = b1.generate_timeline(duration=10.0, fps=30)
        t2 = b2.generate_timeline(duration=10.0, fps=30)
        assert t1 == t2

    def test_blink_bounds_and_closure(self):
        """Blink values must stay strictly within [0.0, 1.0]."""
        b = BlinkGenerator(seed=42)
        timeline = b.generate_timeline(duration=15.0, fps=30)

        assert all(0.0 <= val <= 1.0 for val in timeline)
        # Over 15 seconds with lambda=0.30, there must be at least one blink event
        assert any(val > 0.8 for val in timeline), "Expected at least one full blink closure"

    def test_blink_smooth_kinematics(self):
        """Verify smooth opening and closing kinematics during a blink."""
        b = BlinkGenerator(seed=42)
        assert len(b._blink_timestamps) > 0
        first_blink = b._blink_timestamps[0]

        # Sample during blink
        v_before = b.get_blink_at(first_blink - 0.05)
        v_closed = b.get_blink_at(first_blink + (b.blink_duration * 0.35))
        v_after = b.get_blink_at(first_blink + b.blink_duration + 0.05)

        assert v_before == 0.0
        assert math.isclose(v_closed, 1.0, abs_tol=1e-2)
        assert v_after == 0.0


# ==============================================================================
# 5. FrameAvatarState Serialization Tests
# ==============================================================================

class TestFrameAvatarState:
    """Test data model conversions and dictionary roundtrips."""

    def test_to_dict_and_from_dict(self):
        """Test lossless serialization roundtrip."""
        state = FrameAvatarState(
            timestamp=1.234,
            viseme=Viseme.AA,
            mouth_open=0.85,
            mouth_wide=0.52,
            head_pitch=11.4,
            head_yaw=-3.2,
            head_roll=1.8,
            blink=0.0,
        )
        d = state.to_dict()
        assert d["viseme"] == "AA"
        assert d["mouth_open"] == 0.85

        restored = FrameAvatarState.from_dict(d)
        assert restored.timestamp == 1.234
        assert restored.viseme == Viseme.AA
        assert math.isclose(restored.mouth_open, 0.85)
        assert math.isclose(restored.head_pitch, 11.4)


# ==============================================================================
# 6. Adapter Abstraction Tests (LivePortrait, Hedra, Wav2Lip)
# ==============================================================================

class TestLipSyncAdapters:
    """Test adapter payloads for external facial animation engines."""

    @pytest.fixture
    def sample_states(self) -> list[FrameAvatarState]:
        return [
            FrameAvatarState(
                timestamp=0.0,
                viseme=Viseme.SIL,
                mouth_open=0.0,
                mouth_wide=0.0,
                head_pitch=2.0,
                head_yaw=0.0,
                head_roll=0.0,
                blink=0.0,
            ),
            FrameAvatarState(
                timestamp=0.033,
                viseme=Viseme.AA,
                mouth_open=0.8,
                mouth_wide=0.5,
                head_pitch=10.0,
                head_yaw=2.0,
                head_roll=-1.0,
                blink=0.0,
            ),
            FrameAvatarState(
                timestamp=0.067,
                viseme=Viseme.MBP,
                mouth_open=0.1,
                mouth_wide=0.3,
                head_pitch=5.0,
                head_yaw=1.0,
                head_roll=0.0,
                blink=1.0,
            ),
        ]

    def test_liveportrait_adapter(self, sample_states):
        """Verify LivePortrait payload format and driving vectors."""
        adapter = LivePortraitAdapter(source_image="portrait.png")
        payload = adapter.prepare_payload(sample_states)

        assert payload["engine"] == "live_portrait"
        assert payload["source_image"] == "portrait.png"
        assert payload["n_frames"] == 3
        assert payload["head_motion"]["pitch"] == [2.0, 10.0, 5.0]
        assert payload["retargeting"]["lip_open"] == [0.0, 0.8, 0.1]
        assert payload["retargeting"]["eye_blink"] == [0.0, 0.0, 1.0]

    def test_hedra_adapter(self, sample_states):
        """Verify Hedra character animation timeline payload."""
        adapter = HedraAdapter(default_character_id="rapper_guy")
        payload = adapter.prepare_payload(
            sample_states, audio_url="https://cdn.example.com/verse.mp3"
        )

        assert payload["engine"] == "hedra"
        assert payload["character_id"] == "rapper_guy"
        assert payload["audio_url"] == "https://cdn.example.com/verse.mp3"
        assert len(payload["timeline_keyframes"]) >= 1

    def test_wav2lip_adapter(self, sample_states):
        """Verify Wav2Lip blending masks and scale factors."""
        adapter = Wav2LipAdapter()
        payload = adapter.prepare_payload(sample_states, face_video_path="face.mp4")

        assert payload["engine"] == "wav2lip"
        assert payload["frame_count"] == 3
        assert len(payload["blending_weights"]) == 3
        # Blending weight increases with mouth openness
        assert payload["blending_weights"][1] > payload["blending_weights"][0]


# ==============================================================================
# 7. Deterministic MockLipSyncRenderer Tests
# ==============================================================================

class TestMockLipSyncRenderer:
    """Test deterministic mock renderer end-to-end."""

    def test_generate_states_deterministic(self):
        """Renderer produces identical states across runs given the same inputs."""
        renderer1 = MockLipSyncRenderer(seed=777)
        renderer2 = MockLipSyncRenderer(seed=777)

        phonemes = [
            TimedPhoneme("B", 0.0, 0.1),
            TimedPhoneme("AA", 0.1, 0.3, stress=1.2),
            TimedPhoneme("T", 0.3, 0.4),
            TimedPhoneme("SIL", 0.4, 0.6),
            TimedPhoneme("shuo", 0.6, 0.9),
        ]

        states1 = renderer1.generate_states(audio_duration=1.0, phonemes=phonemes, bpm=140.0)
        states2 = renderer2.generate_states(audio_duration=1.0, phonemes=phonemes, bpm=140.0)

        assert len(states1) == 30
        assert len(states2) == 30
        assert [s.to_dict() for s in states1] == [s.to_dict() for s in states2]

    def test_render_metrics_and_json_export(self, tmp_path: Path):
        """Verify renderer calculates accurate metrics and saves JSON manifest."""
        renderer = MockLipSyncRenderer(seed=42)
        phonemes = [
            TimedPhoneme("AA", 0.0, 0.4),
            TimedPhoneme("MBP", 0.4, 0.6),
            TimedPhoneme("EE", 0.6, 1.0),
        ]
        states = renderer.generate_states(audio_duration=1.0, phonemes=phonemes, bpm=135.0)

        out_json = tmp_path / "avatar_manifest.json"
        result = renderer.render(states, audio_path="beat.mp3", output_path=str(out_json))

        assert result["status"] == "success"
        assert result["frame_count"] == 30
        assert "metrics" in result
        assert result["metrics"]["avg_mouth_open"] > 0.0
        assert result["metrics"]["max_frame_delta"] < 0.5  # verifies no sudden jumps
        assert out_json.exists()
        assert out_json.stat().st_size > 500
