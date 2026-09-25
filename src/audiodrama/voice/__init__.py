"""Voices: speakable text, the audio timeline, and four casts.

    from audiodrama.voice import TimelineParser, assign_wavs
    tl = TimelineParser().parse("episodes/EP1_Pilot.fountain")

Casts: `scratch` (timing-true placeholder murmurs, no engine, runs anywhere), `sapi`
(Windows System.Speech, via one PowerShell batch), `edge` (Edge neural voices; needs
edge-tts and miniaudio), `synthesia` (avatar video, captions aligned back to lines;
key from SYNTHESIA_API_KEY).
"""

from .text import (tidy, title_caps, speakable_slug, speakable_screen,
                   speakable_annotation, xml_escape)
from .timeline import (TimelineParser, LEGACY_TRANSITIONS, episode_files, assign_wavs,
                       durations, stamp_seconds, kind_counts)

__all__ = ["tidy", "title_caps", "speakable_slug", "speakable_screen",
           "speakable_annotation", "xml_escape", "TimelineParser", "LEGACY_TRANSITIONS",
           "episode_files", "assign_wavs", "durations", "stamp_seconds", "kind_counts"]
