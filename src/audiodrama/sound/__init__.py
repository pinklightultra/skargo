"""Sound: WAV I/O and procedural foley.

    from audiodrama.sound import Synth, build
    S = Synth(22050, seed=7)
    build({"room-kitchen": lambda: S.room(60, 2400, -7, [(118, .05)], (0.22, .25))}, "sfx/")
"""

from .wavio import read_int16, write_int16, read_any, to_rate, WavError
from .dsp import Synth, scale_of
from .foley import build, cue_keys, coverage

__all__ = ["read_int16", "write_int16", "read_any", "to_rate", "WavError",
           "Synth", "scale_of", "build", "cue_keys", "coverage"]
