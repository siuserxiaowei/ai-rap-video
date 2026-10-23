"""Comprehensive test suite for rap lyrics flow analyzer and bar scheduler.

Tests:
- Syllable counter (English, Chinese, Pinyin, mixed, numbers, edge cases)
- Rhyme scheme detector (end rhymes, internal rhymes, multisyllabic rhymes)
- Flow cadence analyzer (boom_bap, trap_triplet, chopper_fast)
- Bar scheduler (16-bar verse structure, BPM/grid math, word-level syllable-weighted timings)
"""

import math
import pytest
from typing import List

from airap.lyrics import (
    Bar,
    BarScheduler,
    CadenceType,
    FlowAnalysisResult,
    FlowAnalyzer,
    FlowCadence,
    InternalRhyme,
    MultisyllabicRhyme,
    RhymeSchemeResult,
    VerseSchedule,
    WordTiming,
    analyze_flow,
    classify_cadence,
    count_syllables,
    count_syllables_chinese,
    count_syllables_english,
    detect_internal_rhymes,
    detect_multisyllabic_rhymes,
    detect_rhyme_scheme,
    get_rhyme_key,
    schedule_bars,
    split_into_bars,
    tokenize_lyrics,
)


# ============================================================================
# 1. Syllable Counter Tests
# ============================================================================

class TestSyllableCounter:
    """Test English, Chinese, and mixed syllable counting."""

    def test_english_monosyllables(self):
        words = ["rap", "flow", "rhyme", "spit", "beat", "mic", "yo", "yeah", "hip", "hop", "bars"]
        for w in words:
            assert count_syllables(w) == 1, f"Expected 1 syllable for '{w}'"

    def test_english_multisyllables(self):
        cases = {
            "rhythm": 2,
            "chopper": 2,
            "triplet": 2,
            "underground": 3,
            "champion": 3,
            "microphone": 3,
            "cadence": 2,
            "syllables": 3,
            "studio": 3,
            "freestyle": 2,
            "motion": 2,
            "potion": 2,
            "started": 2,
            "bottle": 2,
        }
        for word, expected in cases.items():
            assert count_syllables(word) == expected, f"Expected {expected} for '{word}', got {count_syllables(word)}"

    def test_english_past_tense_and_plurals(self):
        # -ed rules
        assert count_syllables("rapped") == 1
        assert count_syllables("dropped") == 1
        assert count_syllables("started") == 2
        assert count_syllables("faded") == 2

        # -es rules
        assert count_syllables("rhymes") == 1
        assert count_syllables("games") == 1
        assert count_syllables("boxes") == 2
        assert count_syllables("classes") == 2

    def test_numbers_syllables(self):
        assert count_syllables("16") == 2    # six-teen
        assert count_syllables("808") == 3   # eight-o-eight
        assert count_syllables("24") == 3    # twen-ty-four
        assert count_syllables("100") == 2   # one-hun-dred

    def test_chinese_syllables(self):
        assert count_syllables_chinese("刀光剑影") == 4
        assert count_syllables("刀光剑影") == 4
        assert count_syllables("站在这个舞台中央逆风飞翔") == 12
        assert count_syllables("在这个舞台中央逆风飞翔") == 11
        assert count_syllables("嘻哈帝国") == 4

    def test_pinyin_syllables(self):
        # Romanized Pinyin with tone marks
        assert count_syllables("wǒ de rap flow") == 4
        assert count_syllables("nǐ hǎo") == 2
        # Romanized Pinyin words
        assert count_syllables("zhuang") == 1
        assert count_syllables("xiao") == 1
        assert count_syllables("feng") == 1

    def test_mixed_chinese_english(self):
        # Mixed language hip hop lines
        assert count_syllables("Check我的麦克风") == 6   # Check(1) + 我(1) + 的(1) + 麦(1) + 克(1) + 风(1)
        assert count_syllables("16 bars 绝对炸裂") == 7  # 16(2) + bars(1) + 绝(1) + 对(1) + 炸(1) + 裂(1)
        assert count_syllables("Yo 兄弟 check this out") == 6

    def test_empty_and_punctuation(self):
        assert count_syllables("") == 0
        assert count_syllables("   ") == 0
        assert count_syllables("...,,,!?!?") == 0


# ============================================================================
# 2. Rhyme Scheme Detector Tests
# ============================================================================

class TestRhymeSchemeDetector:
    """Test end rhymes, internal rhymes, and multisyllabic rhymes."""

    def test_aabb_end_rhymes(self):
        bars = [
            "Step to the mic when the beat kicks in",
            "Feel the heavy bass underneath my skin",
            "Spitting boom bap venom on the street tonight",
            "Underground rhythm in the neon light",
        ]
        result = detect_rhyme_scheme(bars)
        assert result.pattern == "AABB"
        assert result.rhyme_groups["A"] == [0, 1]
        assert result.rhyme_groups["B"] == [2, 3]
        assert result.rhyme_density == 1.0

    def test_abab_end_rhymes(self):
        bars = [
            "I step inside the fire",
            "Ready for the game",
            "Taking my spirit higher",
            "Burning with the flame",
        ]
        result = detect_rhyme_scheme(bars)
        assert result.pattern == "ABAB"
        assert result.rhyme_groups["A"] == [0, 2]
        assert result.rhyme_groups["B"] == [1, 3]

    def test_monorhyme_aaaa(self):
        bars = [
            "I watch the steady flow",
            "See the rhythm glow",
            "Moving down below",
            "Putting on a show",
        ]
        result = detect_rhyme_scheme(bars)
        assert result.pattern == "AAAA"
        assert result.rhyme_groups["A"] == [0, 1, 2, 3]

    def test_chinese_end_rhymes(self):
        bars = [
            "站在舞台中央逆风飞翔",
            "追逐心中的金色梦想",
            "街头每个角落发出声响",
            "今夜注定在这个地方闪亮",
        ]
        result = detect_rhyme_scheme(bars)
        # All end with 'ang' rhyme family (翔, 想, 响, 亮)
        assert result.pattern == "AAAA"
        assert result.rhyme_density == 1.0

    def test_internal_rhyme_intra_bar(self):
        bars = [
            "I spit the flame to win the game",
            "Walk down the street and feel the heat",
        ]
        internals = detect_internal_rhymes(bars)
        assert len(internals) >= 2
        # Bar 0 should have flame and game
        b0_rhymes = [ir for ir in internals if ir.bar_index == 0]
        assert any(
            ir.word1.lower() == "flame" and ir.word2.lower() == "game" for ir in b0_rhymes
        )
        # Bar 1 should have street and heat
        b1_rhymes = [ir for ir in internals if ir.bar_index == 1]
        assert any(
            ir.word1.lower() == "street" and ir.word2.lower() == "heat" for ir in b1_rhymes
        )

    def test_multisyllabic_rhymes_chinese(self):
        bars = [
            "在这个舞台中间刀光剑影",
            "所有聚光灯下闪烁朝阳倩影",
        ]
        multis = detect_multisyllabic_rhymes(bars, min_syllables=2)
        assert len(multis) >= 1
        m = multis[0]
        assert m.bar1_index == 0
        assert m.bar2_index == 1
        assert m.syllable_count == 4
        assert "刀 光 剑 影" in m.phrase1
        assert "朝 阳 倩 影" in m.phrase2

    def test_multisyllabic_rhymes_english(self):
        # Multi-word compound rhyme
        bars = [
            "Drop that heavy rap track",
            "Bring the dirty trap back",
        ]
        multis = detect_multisyllabic_rhymes(bars, min_syllables=2)
        assert len(multis) >= 1
        assert multis[0].syllable_count >= 2

        # 2-syllable word match
        bars_words = [
            "Moving through the city with the rapid motion",
            "Mixing in the lab like a magic potion",
        ]
        multis_w = detect_multisyllabic_rhymes(bars_words, min_syllables=2)
        assert len(multis_w) >= 1
        assert multis_w[0].phrase1 == "motion"
        assert multis_w[0].phrase2 == "potion"
        assert multis_w[0].syllable_count == 2

    def test_monosyllabic_not_in_multis(self):
        bars = [
            "I got the flow",
            "Watch the light glow",
        ]
        multis = detect_multisyllabic_rhymes(bars, min_syllables=2)
        assert len(multis) == 0


# ============================================================================
# 3. Flow Cadence Analysis Tests
# ============================================================================

class TestFlowCadenceAnalyzer:
    """Test boom_bap, trap_triplet, and chopper_fast classifications."""

    def test_boom_bap_classification(self):
        # 8-11 syllables in 4/4 measure
        cadence = classify_cadence(syllable_count=9, beats=4.0, bpm=130.0)
        assert cadence.cadence_type == CadenceType.BOOM_BAP.value
        assert cadence.syllables_per_beat == 9 / 4.0
        assert cadence.syllables_per_second == pytest.approx(9 / (4.0 * (60 / 130)), rel=1e-3)

    def test_trap_triplet_classification(self):
        # 12-15 syllables in 4/4 measure (classic Migos triplet flow: 3 notes/beat)
        cadence = classify_cadence(syllable_count=12, beats=4.0, bpm=130.0)
        assert cadence.cadence_type == CadenceType.TRAP_TRIPLET.value
        assert cadence.syllables_per_beat == 3.0
        assert cadence.triplet_ratio == 1.0  # Exactly divisible by 3

        cadence_14 = classify_cadence(syllable_count=14, beats=4.0, bpm=130.0)
        assert cadence_14.cadence_type == CadenceType.TRAP_TRIPLET.value

    def test_chopper_fast_classification(self):
        # 16+ syllables in 4/4 measure (rapid-fire chopper style)
        cadence = classify_cadence(syllable_count=18, beats=4.0, bpm=130.0)
        assert cadence.cadence_type == CadenceType.CHOPPER_FAST.value
        assert cadence.syllables_per_beat == 4.5
        assert cadence.syllables_per_second > 9.0

    def test_verse_flow_cadence_analysis(self):
        bars = [
            "Mic check one two on the beat",            # 8 sylls -> boom_bap
            "Underneath the rhythm in the street",        # 9 sylls -> boom_bap
            "Triplets on the rollie dripping ice upon the wrist", # 13 sylls -> trap_triplet
            "Chopper flow spitting critical venom as fast as a bullet delivering rhythm", # 22 sylls -> chopper_fast
        ]
        result = analyze_flow(bars, bpm=130.0)
        assert result.bars_count == 4
        assert result.total_syllables == sum(count_syllables(b) for b in bars)
        assert result.bar_cadences[0].cadence_type == "boom_bap"
        assert result.bar_cadences[1].cadence_type == "boom_bap"
        assert result.bar_cadences[2].cadence_type == "trap_triplet"
        assert result.bar_cadences[3].cadence_type == "chopper_fast"
        assert result.dominant_cadence == "boom_bap"


# ============================================================================
# 4. Bar Scheduler Tests
# ============================================================================

class TestBarScheduler:
    """Test lyrics splitting, beat grid math, and word-level timing estimation."""

    def test_split_into_bars_headers_and_whitespace(self):
        raw_text = """
        [Intro]
        Yeah yeah, check one two

        [Verse 1]
        Line one of the verse
        Line two of the verse
        Line three // Line four

        [Chorus]
        Never surrender
        """
        bars = split_into_bars(raw_text, target_bars=None)
        assert "Line one of the verse" in bars
        assert "Line two of the verse" in bars
        assert "Line three" in bars
        assert "Line four" in bars
        # Section headers should not be in bars
        for b in bars:
            assert "[Verse 1]" not in b
            assert "[Chorus]" not in b
            assert "[Intro]" not in b

    def test_split_into_bars_16_bar_limit(self):
        twenty_lines = [f"Bar number {i + 1} spitting on the mic" for i in range(20)]
        bars = split_into_bars(twenty_lines, target_bars=16)
        assert len(bars) == 16
        assert bars[0] == "Bar number 1 spitting on the mic"
        assert bars[15] == "Bar number 16 spitting on the mic"

    def test_split_into_bars_pad_to_target(self):
        four_lines = [f"Bar {i + 1}" for i in range(4)]
        padded = split_into_bars(four_lines, target_bars=16, pad_to_target=True)
        assert len(padded) == 16
        assert padded[0] == "Bar 1"
        assert padded[4] == "Bar 1"

    def test_exact_bar_math_130_bpm(self):
        bpm = 130.0
        scheduler = BarScheduler(bpm=bpm, time_signature=(4, 4), start_offset=0.0)

        # 60 / 130 = 0.4615384615...
        expected_beat_duration = 60.0 / 130.0
        expected_bar_duration = 4.0 * expected_beat_duration

        assert scheduler.seconds_per_beat == pytest.approx(expected_beat_duration, rel=1e-6)
        assert scheduler.bar_duration == pytest.approx(expected_bar_duration, rel=1e-6)

        sixteen_bars_text = [f"Bar {i + 1} in the building tonight" for i in range(16)]
        bars = scheduler.schedule(sixteen_bars_text)
        assert len(bars) == 16

        # Check first bar
        assert bars[0].index == 1
        assert bars[0].start_time == 0.0
        assert bars[0].end_time == pytest.approx(expected_bar_duration, rel=1e-5)
        assert bars[0].start_beat == 0.0
        assert bars[0].end_beat == 4.0

        # Check 16th bar
        b16 = bars[15]
        assert b16.index == 16
        assert b16.start_time == pytest.approx(15 * expected_bar_duration, rel=1e-5)
        assert b16.end_time == pytest.approx(16 * expected_bar_duration, rel=1e-5)
        assert b16.start_beat == 60.0
        assert b16.end_beat == 64.0
        assert b16.duration == pytest.approx(expected_bar_duration, rel=1e-5)

    def test_start_offset(self):
        offset = 2.5
        scheduler = BarScheduler(bpm=120.0, start_offset=offset)
        # At 120 BPM: beat = 0.5s, bar = 2.0s
        bars = scheduler.schedule(["Bar one", "Bar two"])
        assert bars[0].start_time == pytest.approx(2.5, rel=1e-6)
        assert bars[0].end_time == pytest.approx(4.5, rel=1e-6)
        assert bars[1].start_time == pytest.approx(4.5, rel=1e-6)
        assert bars[1].end_time == pytest.approx(6.5, rel=1e-6)

    def test_word_level_timing_syllable_weights(self):
        scheduler = BarScheduler(bpm=120.0, rest_ratio=0.10)
        # bar_duration = 2.0s
        # rest = 0.2s -> active_duration = 1.8s
        bar_text = "I am the underground champion"
        # Syllables:
        # "I": 1
        # "am": 1
        # "the": 1
        # "underground": 3
        # "champion": 3
        # Total syllables = 1 + 1 + 1 + 3 + 3 = 9
        # Duration per syllable = 1.8s / 9 = 0.2s
        bars = scheduler.schedule([bar_text])
        b = bars[0]
        assert len(b.words) == 5

        w_i, w_am, w_the, w_underground, w_champion = b.words

        # Check weights proportional
        assert w_i.duration == pytest.approx(0.20, rel=1e-4)
        assert w_am.duration == pytest.approx(0.20, rel=1e-4)
        assert w_the.duration == pytest.approx(0.20, rel=1e-4)
        assert w_underground.duration == pytest.approx(0.60, rel=1e-4)
        assert w_champion.duration == pytest.approx(0.60, rel=1e-4)

        # Check continuity (end of word i == start of word i+1)
        for i in range(len(b.words) - 1):
            assert b.words[i].end_time == pytest.approx(b.words[i + 1].start_time, rel=1e-5)

        # Check bounds
        assert b.words[0].start_time == pytest.approx(0.0, rel=1e-5)
        assert b.words[-1].end_time <= b.end_time

    def test_chinese_word_timings(self):
        scheduler = BarScheduler(bpm=120.0, rest_ratio=0.0)
        # 120 BPM -> bar_duration = 2.0s
        bar_text = "刀光剑影"
        bars = scheduler.schedule([bar_text])
        b = bars[0]
        assert len(b.words) == 4
        # Each character gets exactly 2.0 / 4 = 0.5s
        for w in b.words:
            assert w.syllable_count == 1
            assert w.duration == pytest.approx(0.50, rel=1e-4)

    def test_get_word_at_time(self):
        scheduler = BarScheduler(bpm=120.0, rest_ratio=0.0)
        bars = scheduler.schedule(["刀光剑影"])
        b = bars[0]

        # 0.0 - 0.5: 刀
        # 0.5 - 1.0: 光
        # 1.0 - 1.5: 剑
        # 1.5 - 2.0: 影
        w0 = b.get_word_at_time(0.25)
        assert w0 is not None and w0.text == "刀"
        w1 = b.get_word_at_time(0.75)
        assert w1 is not None and w1.text == "光"
        w2 = b.get_word_at_time(1.25)
        assert w2 is not None and w2.text == "剑"
        w3 = b.get_word_at_time(1.75)
        assert w3 is not None and w3.text == "影"

    def test_verse_schedule_container(self):
        scheduler = BarScheduler(bpm=130.0)
        raw_lyrics = [
            "Step to the mic when the beat kicks in",
            "Feel the heavy bass underneath my skin",
            "Spitting boom bap venom on the street tonight",
            "Underground rhythm in the neon light",
        ]
        verse = scheduler.schedule_verse(raw_lyrics)
        assert isinstance(verse, VerseSchedule)
        assert len(verse.bars) == 4
        assert verse.rhyme_scheme == "AABB"
        assert verse.total_beats == 16.0
        assert verse.total_duration == pytest.approx(4 * 4 * (60 / 130), rel=1e-4)

        # Test dictionary & JSON serialization
        v_dict = verse.to_dict()
        assert v_dict["bar_count"] == 4
        assert "bars" in v_dict
        assert len(v_dict["bars"]) == 4

        v_json = verse.to_json()
        assert "AABB" in v_json
        assert "boom_bap" in v_json

    def test_functional_schedule_bars(self):
        bars = schedule_bars(
            lyrics=["One two three four", "Five six seven eight"],
            bpm=120.0,
            start_offset=1.0,
        )
        assert len(bars) == 2
        assert bars[0].start_time == 1.0
        assert bars[0].end_time == 3.0
        assert bars[1].start_time == 3.0
        assert bars[1].end_time == 5.0

    def test_time_signature_3_4(self):
        scheduler = BarScheduler(bpm=120.0, time_signature=(3, 4))
        # At 120 BPM in 3/4: beat = 0.5s, bar = 3 * 0.5 = 1.5s
        assert scheduler.beats_per_bar == 3.0
        assert scheduler.seconds_per_beat == 0.5
        assert scheduler.bar_duration == 1.5
        bars = scheduler.schedule(["Waltz rap bar one", "Waltz rap bar two"])
        assert bars[0].end_time == 1.5
        assert bars[0].end_beat == 3.0
        assert bars[1].start_time == 1.5
        assert bars[1].end_time == 3.0
        assert bars[1].start_beat == 3.0
        assert bars[1].end_beat == 6.0

    def test_empty_schedule_and_flow(self):
        scheduler = BarScheduler(bpm=130.0)
        assert scheduler.schedule([]) == []
        assert scheduler.schedule("") == []

        empty_analysis = analyze_flow([])
        assert empty_analysis.bars_count == 0
        assert empty_analysis.total_syllables == 0
        assert empty_analysis.rhyme_scheme.pattern == ""

    def test_unrhymed_scheme_abcd(self):
        bars = [
            "Apple in the orchard",
            "Elephant walking far away",
            "Midnight shadows on the ocean",
            "Crystal pyramid shining",
        ]
        result = detect_rhyme_scheme(bars)
        assert len(result.pattern) == 4
        # Four unique letters
        assert len(set(result.pattern)) == 4
        assert result.rhyme_density == 0.0

    def test_flow_analyzer_instance_methods(self):
        analyzer = FlowAnalyzer(default_bpm=140.0)
        assert analyzer.count_syllables("supercalifragilistic") >= 6
        assert analyzer.count_syllables_english("freestyle") == 2
        assert analyzer.count_syllables_chinese("说唱") == 2
        assert analyzer.get_rhyme_key("glow") == "OW"

        cadence = analyzer.classify_cadence(syllable_count=13)
        assert cadence.cadence_type == "trap_triplet"
        assert cadence.bpm == 140.0

        scheme = analyzer.detect_rhyme_scheme(["Drop it low", "Watch it blow"])
        assert scheme.pattern == "AA"

        verse_res = analyzer.analyze_verse(["Drop it low", "Watch it blow"])
        assert verse_res.dominant_cadence == "boom_bap"

    def test_verse_get_bar_and_word_at_time(self):
        scheduler = BarScheduler(bpm=120.0, rest_ratio=0.0)
        # Bar 1: 0.0 -> 2.0s ("One two")
        # Bar 2: 2.0 -> 4.0s ("Three four")
        verse = scheduler.schedule_verse(["One two", "Three four"])
        assert verse.get_bar_at_time(1.0).index == 1
        assert verse.get_bar_at_time(3.0).index == 2
        assert verse.get_bar_at_time(5.0) is None

        # Test word lookup through verse
        w = verse.get_word_at_time(0.5)
        assert w is not None
        assert w.text == "One"

    def test_dataclass_to_dict_serializations(self):
        wt = WordTiming(
            text="flow",
            syllable_count=1,
            start_time=0.0,
            end_time=0.5,
            start_beat=0.0,
            end_beat=1.0,
        )
        wt_d = wt.to_dict()
        assert wt_d["text"] == "flow"
        assert wt_d["duration"] == 0.5
        assert wt_d["beat_duration"] == 1.0

        bar = Bar(
            index=1,
            text="test bar",
            syllable_count=2,
            start_time=0.0,
            end_time=2.0,
            start_beat=0.0,
            end_beat=4.0,
            words=[wt],
        )
        bar_d = bar.to_dict()
        assert bar_d["index"] == 1
        assert bar_d["duration"] == 2.0
        assert bar_d["beats"] == 4.0
        assert len(bar_d["words"]) == 1
