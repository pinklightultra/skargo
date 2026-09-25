"""Scratch cast: timing-true placeholder lines, with no TTS engine at all.

Every job becomes a murmur about as long as the line takes to say, at the part's own
pitch, levelled to the speech RMS the music slots are measured against. The whole
pipeline -- timeline durations, mixer pacing, ad pods, music levels -- runs before a
single real voice is rendered, on any OS, offline. It is also what the tests run on.

A cast is {part: fundamental Hz}. A part missing from it gets a pitch derived from its
name, so an uncast speaker is audible as somebody new rather than as silence.

Each line's random stream is seeded from its speaker and text. Editing one line
changes that one wav; every other file re-renders bit-identical.
"""

import hashlib
import re
from pathlib import Path

import numpy as np

from ..sound.dsp import Synth
from ..sound.wavio import write_int16

WPS = 2.6          # words per second, conversational
RMS = 0.0705       # the score's default speech reference (audiodrama.score.slots)
WORD_GAP = 0.05
COMMA_GAP = 0.12
STOP_GAP = 0.22


def seed_of(*parts):
    h = hashlib.sha1("\0".join(parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "little")


def pitch_for(speaker, lo=90.0, hi=240.0):
    """A stable made-up pitch for a speaker nobody cast."""
    return lo + seed_of(speaker) % 1000 / 1000 * (hi - lo)


def band(S, x, lo, hi):
    """S.band over a whole line, zero-padded to a power of two. Filtering word by
    word was most of the cost, and one FFT at a length with a large prime factor
    was slower still."""
    n = len(x)
    return S.band(np.concatenate([x, np.zeros((1 << (n - 1).bit_length()) - n)]), lo, hi)[:n]


def murmur(text, f0, sr=22050, wps=WPS, rms=RMS, seed=0):
    """A voiced mumble with one burst per word, shaped by syllable, paused at
    punctuation. Speaking time is len(words) / wps; pauses come on top, as they do."""
    S = Synth(sr, seed)
    words = re.findall(r"[\w']+[,.;:!?]*", text) or ["hm."]
    letters = [max(1, len(re.sub(r"[^\w]", "", w))) for w in words]
    speak = len(words) / wps
    voiced, breath = [], []
    for w, n in zip(words, letters):
        d = max(0.12, speak * n / sum(letters) - WORD_GAP)
        tt = S.t(d)
        glide = 1 + 0.05 * np.sin(2 * np.pi * S.rng.uniform(0.6, 1.4) * tt
                                  + S.rng.uniform(0, 2 * np.pi))
        ph = 2 * np.pi * f0 * np.cumsum(glide) / sr
        buzz = sum(np.sin(k * ph) / k for k in range(1, 13))
        syll = max(1, round(n / 3))
        shape = (np.sin(np.pi * tt / d)
                 * (0.55 + 0.45 * np.abs(np.sin(np.pi * syll * tt / d))))
        voiced.append(buzz * shape)
        breath.append(S.noise(d) * shape)
        tail = w[-1]
        gap = np.zeros(int(sr * (WORD_GAP + (STOP_GAP if tail in ".!?"
                                             else COMMA_GAP if tail in ",;:" else 0))))
        voiced.append(gap)
        breath.append(gap)
    x = band(S, np.concatenate(voiced[:-1]), 120, 3400)         + band(S, np.concatenate(breath[:-1]), 2000, 7000) * .04
    r = float(np.sqrt((x ** 2).mean()))
    if r > 0:
        x = x * (rms / r)
    peak = float(np.max(np.abs(x)))
    if peak > 0.95:
        x = x * (0.95 / peak)
    return x.astype(np.float32)


def render(jobs, line_dir, cast=None, sr=22050, force=False, log=print):
    """Generic jobs ({wav, voice_as, text}) -> wavs in line_dir. Returns (made, skipped).

    An existing wav is kept unless `force`, as with the other casts. Its name is its
    timeline position, so after a script edit that moves events, re-render with force.
    """
    cast = cast or {}
    line_dir = Path(line_dir)
    line_dir.mkdir(parents=True, exist_ok=True)
    made = skipped = 0
    for j in jobs:
        dest = line_dir / j["wav"]
        if dest.exists() and not force:
            skipped += 1
            continue
        f0 = cast.get(j["voice_as"]) or pitch_for(j["voice_as"])
        write_int16(dest, murmur(j["text"], f0, sr, seed=seed_of(j["voice_as"], j["text"])), sr)
        made += 1
    if log:
        log("scratch cast: %d lines rendered, %d kept -> %s" % (made, skipped, line_dir.name))
    return made, skipped
