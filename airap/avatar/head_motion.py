"""Head motion generator and 3D rotational transforms for rap performance.

Includes:
- Rap HeadBobber: Beat-synced head nod generator where downbeats trigger downward
  head dips and upbeats raise the head.
- Poisson distribution eye-blink generator for natural blinking dynamics.
- Pitch, Yaw, Roll 3D rotational transforms, Euler angle conversions, and quaternions.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class EulerAngles:
    """3D Euler angles (Pitch, Yaw, Roll) in degrees.

    Convention:
    - Pitch: Rotation around X-axis (nodding: positive = downward nod, negative = head raised up).
    - Yaw: Rotation around Y-axis (turning: positive = turned right, negative = turned left).
    - Roll: Rotation around Z-axis (tilting: positive = tilted right ear down, negative = left).
    """
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0

    def to_radians(self) -> Tuple[float, float, float]:
        """Convert angles from degrees to radians (pitch, yaw, roll)."""
        return (
            math.radians(self.pitch),
            math.radians(self.yaw),
            math.radians(self.roll),
        )

    def to_rotation_matrix(
        self,
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
        """Calculate 3x3 rotation matrix using Z-Y-X (Roll-Yaw-Pitch) convention.

        R = R_z(roll) * R_y(yaw) * R_x(pitch)
        """
        p, y, r = self.to_radians()
        cp, sp = math.cos(p), math.sin(p)
        cy, sy = math.cos(y), math.sin(y)
        cr, sr = math.cos(r), math.sin(r)

        r00 = cr * cy
        r01 = cr * sy * sp - sr * cp
        r02 = cr * sy * cp + sr * sp

        r10 = sr * cy
        r11 = sr * sy * sp + cr * cp
        r12 = sr * sy * cp - cr * sp

        r20 = -sy
        r21 = cy * sp
        r22 = cy * cp

        return (
            (round(r00, 8), round(r01, 8), round(r02, 8)),
            (round(r10, 8), round(r11, 8), round(r12, 8)),
            (round(r20, 8), round(r21, 8), round(r22, 8)),
        )

    def to_quaternion(self) -> Tuple[float, float, float, float]:
        """Convert Euler angles to normalized quaternion (w, x, y, z)."""
        p, y, r = self.to_radians()
        hp, hy, hr = p * 0.5, y * 0.5, r * 0.5

        chp, shp = math.cos(hp), math.sin(hp)
        chy, shy = math.cos(hy), math.sin(hy)
        chr, shr = math.cos(hr), math.sin(hr)

        w = chr * chy * chp + shr * shy * shp
        x = chr * chy * shp - shr * shy * chp
        y = chr * shy * chp + shr * chy * shp
        z = shr * chy * chp - chr * shy * shp

        norm = math.sqrt(w * w + x * x + y * y + z * z)
        if norm > 1e-9:
            w, x, y, z = w / norm, x / norm, y / norm, z / norm
        return (round(w, 8), round(x, 8), round(y, 8), round(z, 8))

    def rotate_vector(self, v: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Rotate a 3D vector by this rotation matrix."""
        m = self.to_rotation_matrix()
        vx, vy, vz = v
        rx = m[0][0] * vx + m[0][1] * vy + m[0][2] * vz
        ry = m[1][0] * vx + m[1][1] * vy + m[1][2] * vz
        rz = m[2][0] * vx + m[2][1] * vy + m[2][2] * vz
        return (round(rx, 8), round(ry, 8), round(rz, 8))

    def lerp(self, other: EulerAngles, alpha: float) -> EulerAngles:
        """Linear interpolation between two Euler angle poses."""
        alpha = max(0.0, min(1.0, alpha))
        return EulerAngles(
            pitch=self.pitch + alpha * (other.pitch - self.pitch),
            yaw=self.yaw + alpha * (other.yaw - self.yaw),
            roll=self.roll + alpha * (other.roll - self.roll),
        )


@dataclass
class HeadMotionState:
    """Avatar head orientation and position state at a specific timestamp."""
    timestamp: float
    angles: EulerAngles

    @property
    def pitch(self) -> float:
        return self.angles.pitch

    @property
    def yaw(self) -> float:
        return self.angles.yaw

    @property
    def roll(self) -> float:
        return self.angles.roll


class HeadBobber:
    """Rap head nod generator tightly synced to musical tempo (BPM).

    Rap Performance Mechanics:
    - Downbeats (beats 1 & 3 in 4/4) trigger pronounced downward head dips (nodding).
    - Upbeats (the '&' half-way between beats) rebound upward, raising the head.
    - Bars follow 4/4 cadence with distinct accentuation on the 1st downbeat.
    - Side-to-side yaw sway and swagger roll tilt groove across bars.
    """

    def __init__(
        self,
        bpm: float = 130.0,
        intensity: float = 1.0,
        base_pitch: float = 2.0,
        pitch_amplitude: float = 8.5,
        yaw_amplitude: float = 4.0,
        roll_amplitude: float = 3.0,
    ):
        """Initialize HeadBobber.

        Args:
            bpm: Musical tempo in beats per minute (e.g. 130-150 BPM for rap).
            intensity: Overall motion multiplier [0.0, 2.0].
            base_pitch: Resting forward posture angle in degrees.
            pitch_amplitude: Peak nod dip amplitude in degrees.
            yaw_amplitude: Lateral head turn amplitude in degrees.
            roll_amplitude: Sideways swagger head tilt in degrees.
        """
        self.bpm = max(20.0, bpm)
        self.intensity = intensity
        self.base_pitch = base_pitch
        self.pitch_amplitude = pitch_amplitude
        self.yaw_amplitude = yaw_amplitude
        self.roll_amplitude = roll_amplitude

    @property
    def beat_period(self) -> float:
        """Duration of a quarter-note beat in seconds."""
        return 60.0 / self.bpm

    def get_motion_at(self, timestamp: float) -> HeadMotionState:
        """Compute head Euler angles at an arbitrary timestamp.

        - Downbeats (t % beat_period == 0) reach maximum downward nod (highest positive pitch).
        - Upbeats (t % beat_period == beat_period / 2) raise the head (lowest pitch).
        """
        t = max(0.0, timestamp)
        bp = self.beat_period

        # Fractional phase within the beat: 0.0 is on the beat, 0.5 is the upbeat
        beat_phase = (t % bp) / bp

        # Asymmetric rap bounce curve:
        # Sharp dip into the beat at phase 0, smooth rebound up at phase 0.5
        # Range of bounce is [-0.5, 1.0]
        bounce = 0.75 * math.cos(2 * math.pi * beat_phase) + 0.25 * math.cos(4 * math.pi * beat_phase)

        # 4/4 Bar position and beat accentuation
        beat_idx = int(t / bp) % 4
        # Beat 0 (downbeat 1): 1.25x accent
        # Beat 1 (offbeat): 0.85x
        # Beat 2 (downbeat 3 / backbeat): 1.15x
        # Beat 3 (offbeat): 0.90x
        accent_weights = [1.25, 0.85, 1.15, 0.90]
        accent = accent_weights[beat_idx]

        # Calculate Pitch (degrees)
        # Positive pitch = downward dip; negative/lower = head raised
        pitch = self.base_pitch + (self.pitch_amplitude * self.intensity * accent * bounce)

        # Calculate Yaw (degrees) - rhythmic sway across 2 bars (8 beats)
        yaw_phase = (t % (8 * bp)) / (8 * bp)
        yaw = self.yaw_amplitude * self.intensity * math.sin(2 * math.pi * yaw_phase)

        # Calculate Roll (degrees) - subtle syncopated swagger across 4 beats
        roll_phase = (t % (4 * bp)) / (4 * bp)
        roll = self.roll_amplitude * self.intensity * math.sin(2 * math.pi * roll_phase + math.pi / 4)

        return HeadMotionState(
            timestamp=t,
            angles=EulerAngles(
                pitch=round(pitch, 4),
                yaw=round(yaw, 4),
                roll=round(roll, 4),
            ),
        )

    def generate_timeline(
        self,
        duration: float,
        fps: int = 30,
    ) -> List[HeadMotionState]:
        """Generate full animation timeline for a video sequence."""
        frame_count = max(1, int(round(duration * fps)))
        dt = 1.0 / fps
        return [self.get_motion_at(i * dt) for i in range(frame_count)]


class BlinkGenerator:
    """Natural Poisson-process eye-blink generator for digital avatars.

    Blink Characteristics:
    - Inter-blink intervals follow an exponential distribution (Poisson point process).
    - Mean blink rate: ~18 blinks/minute (lambda ~ 0.30 blinks/sec).
    - Blink duration: ~180 ms (50ms close, 30ms hold, 100ms smooth reopening).
    - Output values: 0.0 (wide open) to 1.0 (fully closed).
    - Fully deterministic when initialized with a random seed.
    """

    def __init__(
        self,
        mean_rate_hz: float = 0.30,
        blink_duration: float = 0.18,
        seed: Optional[int] = 42,
        horizon: float = 600.0,
    ):
        """Initialize BlinkGenerator.

        Args:
            mean_rate_hz: Poisson rate lambda (average blinks per second).
            blink_duration: Duration of single eye-blink in seconds.
            seed: Deterministic random seed for reproducibility.
            horizon: Pre-computation time horizon in seconds.
        """
        self.mean_rate_hz = max(0.05, mean_rate_hz)
        self.blink_duration = blink_duration
        self.seed = seed
        self.horizon = horizon
        self._blink_timestamps: List[float] = []
        self._generate_events()

    def _generate_events(self) -> None:
        """Pre-compute blink trigger timestamps using Poisson point process."""
        rng = random.Random(self.seed)
        current_time = rng.uniform(0.5, 2.0)  # Initial pause before first blink

        self._blink_timestamps.clear()
        while current_time < self.horizon:
            self._blink_timestamps.append(current_time)
            # Sample exponential inter-arrival interval: dt = -ln(U) / lambda
            u = max(1e-7, rng.random())
            interval = -math.log(u) / self.mean_rate_hz
            # Minimum refractory period of 0.8s between blinks
            current_time += max(0.8, interval)

    def get_blink_at(self, timestamp: float) -> float:
        """Calculate eye-blink closure at a specific timestamp [0.0 to 1.0]."""
        if timestamp < 0:
            return 0.0

        d = self.blink_duration
        # Find if timestamp falls within any blink window
        for bt in self._blink_timestamps:
            if bt <= timestamp <= bt + d:
                elapsed = timestamp - bt
                # Phase 1: Rapid close (0% to ~28% of duration: ~50ms)
                close_time = d * 0.28
                hold_time = d * 0.44  # peak hold up to ~80ms
                if elapsed < close_time:
                    p = elapsed / close_time
                    # Smooth hermite / cosine ease in
                    return 0.5 * (1.0 - math.cos(math.pi * p))
                elif elapsed <= hold_time:
                    return 1.0
                else:
                    # Phase 3: Smooth reopen
                    reopen_p = (elapsed - hold_time) / (d - hold_time)
                    return 0.5 * (1.0 + math.cos(math.pi * reopen_p))

            if bt > timestamp + d:
                # Timestamps are ordered; can stop early
                break

        return 0.0

    def generate_timeline(
        self,
        duration: float,
        fps: int = 30,
    ) -> List[float]:
        """Generate eye-blink values for each frame of a sequence."""
        frame_count = max(1, int(round(duration * fps)))
        dt = 1.0 / fps
        return [round(self.get_blink_at(i * dt), 4) for i in range(frame_count)]
