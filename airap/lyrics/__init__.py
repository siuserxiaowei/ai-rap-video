"""AIRap Lyrics & Flow Engine.

Provides syllable counting, rhyme scheme analysis, cadence classification,
and musical bar scheduling for rap lyrics.
"""

from airap.lyrics.flow_analyzer import (
    CadenceType,
    FlowAnalysisResult,
    FlowAnalyzer,
    FlowCadence,
    InternalRhyme,
    MultisyllabicRhyme,
    RhymeSchemeResult,
    analyze_flow,
    classify_cadence,
    count_syllables,
    count_syllables_chinese,
    count_syllables_english,
    detect_internal_rhymes,
    detect_multisyllabic_rhymes,
    detect_rhyme_scheme,
    get_rhyme_key,
    tokenize_lyrics,
)
from airap.lyrics.bar_scheduler import (
    Bar,
    BarScheduler,
    VerseSchedule,
    WordTiming,
    schedule_bars,
    split_into_bars,
)

__all__ = [
    # Cadence & Flow
    "CadenceType",
    "FlowCadence",
    "InternalRhyme",
    "MultisyllabicRhyme",
    "RhymeSchemeResult",
    "FlowAnalysisResult",
    "FlowAnalyzer",
    "count_syllables",
    "count_syllables_english",
    "count_syllables_chinese",
    "classify_cadence",
    "detect_rhyme_scheme",
    "detect_internal_rhymes",
    "detect_multisyllabic_rhymes",
    "analyze_flow",
    "get_rhyme_key",
    "tokenize_lyrics",
    # Bar Scheduling
    "Bar",
    "WordTiming",
    "VerseSchedule",
    "BarScheduler",
    "split_into_bars",
    "schedule_bars",
]
