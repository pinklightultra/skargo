"""Build a show's foley library from a recipe table, and check it covers the cues.

A recipe table is {key: zero-argument callable -> float signal}. Room tones are keys
starting `room-`; the mixer tiles those as beds and places everything else as an
event. Recipes are evaluated in table order, which is what makes a seeded build
reproducible.
"""

import json
from pathlib import Path

from .wavio import write_int16


def build(recipes, outdir, sr=22050):
    """Render every recipe to outdir/<key>.wav. Returns {key: seconds}."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    made = {}
    for key, fn in recipes.items():
        x = fn()
        write_int16(outdir / ("%s.wav" % key), x, sr)
        made[key] = len(x) / sr
    return made


def cue_keys(cues):
    """The foley keys a cue sheet (cues.json content, or its path) asks for."""
    if isinstance(cues, (str, Path)):
        cues = json.loads(Path(cues).read_text(encoding="utf-8"))
    return {c["key"] for c in cues if c["kind"] == "foley"}


def coverage(needed, made):
    """(missing, extra): cue keys with no sound, and sounds no cue uses."""
    return sorted(set(needed) - set(made)), sorted(set(made) - set(needed))
