"""AIRap Avatar & LipSync Module.

High-cadence rap lip-sync, beat-synced head motion, and adapter engine.
"""

from airap.avatar.head_motion import (
    BlinkGenerator,
    EulerAngles,
    HeadBobber,
    HeadMotionState,
)
from airap.avatar.lipsync_engine import (
    FrameAvatarState,
    HedraAdapter,
    LipSyncEngine,
    LivePortraitAdapter,
    MockLipSyncRenderer,
    Wav2LipAdapter,
)
from airap.avatar.phoneme_viseme import (
    DEFAULT_VISEME_SHAPES,
    CoArticulationFilter,
    PhonemeVisemeMapper,
    TimedPhoneme,
    TimedViseme,
    Viseme,
)

__all__ = [
    # Viseme & Phonemes
    "Viseme",
    "DEFAULT_VISEME_SHAPES",
    "TimedPhoneme",
    "TimedViseme",
    "PhonemeVisemeMapper",
    "CoArticulationFilter",
    # Head Motion & Blink
    "EulerAngles",
    "HeadMotionState",
    "HeadBobber",
    "BlinkGenerator",
    # LipSync Engine & Adapters
    "FrameAvatarState",
    "LipSyncEngine",
    "LivePortraitAdapter",
    "HedraAdapter",
    "Wav2LipAdapter",
    "MockLipSyncRenderer",
]
