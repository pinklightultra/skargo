"""A two-track song backlog for LOW TIDE, synthesised so the demo ships no audio.

The formats are the awkward ones on purpose. The theme is what a DAW writes by
default -- 32-bit float, stereo, 44.1 kHz, which the `wave` module refuses -- and the
bed is 16-bit mono at the drama rate. The scorer has to read both.

    low_tide_theme.wav   90 s: a D minor pad, a tune over the first 12 s, and two
                         stings, at 30 s and 60 s, for the act cues to be cut from
    harbour_bed.wav      60 s: a dark drone, for the recap
"""

from pathlib import Path

import numpy as np

from audiodrama.sound.wavio import write_int16

THEME_SR = 44100
STINGS = (30.0, 60.0)
CHORDS = [(146.83, 174.61, 220.00), (116.54, 146.83, 174.61),     # Dm, Bb
          (174.61, 220.00, 261.63), (130.81, 164.81, 196.00)]     # F, C
TUNE = [(293.66, .8), (349.23, .4), (440.0, 1.2), (392.0, .8), (349.23, .8),
        (329.63, 1.6), (293.66, .8), (261.63, .8), (293.66, 2.4)]


def write_float32(path, left, right, sr):
    """A stereo WAVE_FORMAT_IEEE_FLOAT file, with the fact chunk a float WAV carries."""
    data = np.stack([left, right], 1).astype("<f4").tobytes()
    fmt = ((3).to_bytes(2, "little") + (2).to_bytes(2, "little") + sr.to_bytes(4, "little")
           + (sr * 8).to_bytes(4, "little") + (8).to_bytes(2, "little")
           + (32).to_bytes(2, "little") + (0).to_bytes(2, "little"))
    fact = (len(left)).to_bytes(4, "little")
    body = (b"WAVE" + b"fmt " + len(fmt).to_bytes(4, "little") + fmt
            + b"fact" + (4).to_bytes(4, "little") + fact
            + b"data" + len(data).to_bytes(4, "little") + data)
    Path(path).write_bytes(b"RIFF" + len(body).to_bytes(4, "little") + body)


def theme(seconds=90.0, sr=THEME_SR, seed=3):
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    L, R = np.zeros(n), np.zeros(n)
    span = 4.0
    for k in range(int(np.ceil(seconds / span))):
        a, b = int(k * span * sr), min(int((k + 1) * span * sr), n)
        tt = t[a:b] - k * span
        shape = np.minimum(1, tt / 1.2) * np.minimum(1, (span - tt) / 1.2)
        for f in CHORDS[k % len(CHORDS)]:
            L[a:b] += .10 * np.sin(2 * np.pi * f * .998 * t[a:b]) * shape
            R[a:b] += .10 * np.sin(2 * np.pi * f * 1.002 * t[a:b]) * shape
    at = 1.0
    for f, d in TUNE:
        a, m = int(at * sr), int(d * sr)
        tt = np.arange(m) / sr
        note = (np.sin(2 * np.pi * f * tt) + .3 * np.sin(4 * np.pi * f * tt)) * np.exp(-2.2 * tt)
        L[a:a + m] += .16 * note
        R[a:a + m] += .12 * note
        at += d
    for s in STINGS:
        a = int(s * sr)
        m = min(int(4 * sr), n - a)
        tt = np.arange(m) / sr
        hit = sum(np.sin(2 * np.pi * f * tt) for f in (73.42, 146.83, 220.0, 293.66))
        hit = hit * np.exp(-1.1 * tt) * np.minimum(1, tt / .004)
        boom = rng.standard_normal(m) * np.exp(-9 * tt) * .5
        L[a:a + m] += .22 * hit + .2 * boom
        R[a:a + m] += .22 * hit + .2 * boom
    return L.astype(np.float32), R.astype(np.float32)


def bed(seconds=60.0, sr=22050):
    t = np.arange(int(seconds * sr)) / sr
    x = (np.sin(2 * np.pi * 73.42 * t) + .6 * np.sin(2 * np.pi * 110.0 * t)
         + .25 * np.sin(2 * np.pi * 146.83 * t))
    x *= 0.75 + 0.25 * np.sin(2 * np.pi * t / 15)
    return (0.2 * x / np.max(np.abs(x))).astype(np.float32)


def write(outdir):
    """Write both tracks. Returns their paths."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    th, bd = outdir / "low_tide_theme.wav", outdir / "harbour_bed.wav"
    write_float32(th, *theme(), THEME_SR)
    write_int16(bd, bed())
    return [th, bd]
