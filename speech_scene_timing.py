"""Audio-aware scene cuts for offline, rights-cleared narrated product Shorts.

Uses only FFmpeg's silence detector. This is not speech recognition,
forced alignment, or lip synchronization; cuts fall near audible pauses when
an eligible pause exists, otherwise at a bounded evenly spaced fallback.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
import subprocess

_PAUSE_START = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_PAUSE_END = re.compile(r"silence_end:\s*(\d+(?:\.\d+)?)")


def audio_pauses(wav: Path, seconds: float) -> list[float]:
    """Find interior silence midpoints using a local FFmpeg filter only."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(wav),
         "-af", "silencedetect=noise=-35dB:d=0.16", "-f", "null", "-"],
        capture_output=True, text=True, timeout=35,
    )
    if result.returncode:
        # Rendering remains possible without editorial pause information.
        return []
    starts: list[float] = []
    points: list[float] = []
    for line in result.stderr.splitlines():
        start = _PAUSE_START.search(line)
        if start:
            starts.append(max(0.0, float(start.group(1))))
        end = _PAUSE_END.search(line)
        if end and starts:
            a, b = starts.pop(0), float(end.group(1))
            middle = (a + b) / 2
            if b - a >= .16 and .3 < middle < seconds - .3:
                points.append(middle)
    return sorted(set(points))


def plan_scenes(wav: Path, seconds: float, count: int, transition: float) -> dict:
    """Return fade-safe scene durations, transition offsets and honest QA info."""
    if not math.isfinite(seconds) or seconds <= 0 or not 1 <= count <= 6:
        raise ValueError("Invalid narration length or scene count")
    if not 0 <= transition <= .5 or (count > 1 and seconds / count < .7):
        raise ValueError("Narration too short for the requested scenes")
    pauses = audio_pauses(wav, seconds) if count > 1 else []
    cuts: list[float] = []
    aligned = 0
    avg = seconds / count
    min_gap = min(.98, max(.7, avg * .60))
    # Keep cuts near the expected scene length; prevent rapid scene flashing.
    max_shift = min(2.5, avg * .40)
    for index in range(1, count):
        ideal = seconds * index / count
        lower = (cuts[-1] if cuts else 0.) + min_gap
        upper = seconds - (count - index) * min_gap
        candidates = [p for p in pauses if lower <= p <= upper and abs(p - ideal) <= max_shift]
        if candidates:
            cut = min(candidates, key=lambda p: (abs(p - ideal), p))
            aligned += 1
        else:
            cut = max(lower, min(upper, ideal))
        cuts.append(cut)
    # Transitions center on each cut. Final MP4 duration stays unchanged.
    durations = []
    for index in range(count):
        left = 0.0 if index == 0 else cuts[index-1] - transition / 2
        right = seconds if index == count-1 else cuts[index] + transition / 2
        durations.append(right-left)
    offsets = [cut - transition / 2 for cut in cuts]
    return {"cut_times": cuts, "scene_durations": durations,
            "transition_offsets": offsets, "pause_matches": aligned,
            "available_pauses": len(pauses),
            "method": "ffmpeg_silence_pauses_with_even_fallback_v20"}
