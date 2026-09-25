"""Foley synthesis primitives. No samples, no downloads, no scipy.

Modal synthesis for anything that rings (bells, tile, tins, cutlery), Karplus-Strong
for anything struck that has a body (a bin, a door), and spectrally shaped noise
with an envelope for friction and air (paper, cloth, crowds, wind, rooms). Filtering
is an rFFT mask rather than a biquad because that is fully vectorised.

A `Synth` owns its sample rate and its random generator. Every draw comes from that
one generator, so a recipe table evaluated in a fixed order rebuilds bit-identical;
reorder the table, or add a recipe in the middle, and everything after it changes.

    S = Synth(22050, seed=7)
    bell = S.norm(S.modal(2.6, [(1046, 1, 1.5), (1052, .9, 1.6)]) * S.env(2.6, .001, 2.2, 1.1), .6)
"""

import numpy as np


class Synth:
    def __init__(self, sr=22050, seed=7):
        self.sr = sr
        self.rng = np.random.default_rng(seed)

    # ---- time and noise
    def t(self, dur):
        return np.arange(int(self.sr * dur)) / self.sr

    def noise(self, dur):
        return self.rng.standard_normal(int(self.sr * dur))

    # ---- shaping
    def band(self, x, lo, hi, tilt=0.0):
        """Keep lo..hi Hz with soft edges, plus an optional tilt in dB/octave."""
        SR = self.sr
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(len(x), 1 / SR)
        g = np.ones_like(f)
        g[f < lo] = 0.0
        g[f > hi] = 0.0
        edge = (f >= lo) & (f < lo * 2)
        g[edge] *= np.linspace(0, 1, edge.sum())
        edge = (f > hi / 2) & (f <= hi)
        g[edge] *= np.linspace(1, 0, edge.sum())
        if tilt:
            with np.errstate(divide="ignore"):
                oct_ = np.log2(np.maximum(f, 1e-9) / max(lo, 1e-9))
            g *= 10 ** (tilt * oct_ / 20)
        return np.fft.irfft(X * g, len(x))

    def env(self, dur, a=0.005, d=None, curve=3.0):
        """Linear attack, then exponential decay."""
        SR = self.sr
        n = int(SR * dur)
        e = np.ones(n)
        na = max(int(SR * a), 1)
        e[:na] = np.linspace(0, 1, na)
        d = dur if d is None else d
        e *= np.exp(-curve * np.arange(n) / (SR * d))
        return e

    def am(self, x, rate, depth=0.5):
        return x * (1 - depth + depth * (0.5 + 0.5 * np.sin(
            2 * np.pi * rate * self.t(len(x) / self.sr))))

    @staticmethod
    def norm(x, peak=0.7):
        m = np.max(np.abs(x))
        return x * (peak / m) if m > 0 else x

    def loopable(self, x, xfade=0.25):
        """Crossfade the tail over the head so a bed repeats without a seam."""
        n = int(self.sr * xfade)
        if n * 2 >= len(x):
            return x
        head, tail = x[:n].copy(), x[-n:].copy()
        r = np.linspace(0, 1, n)
        x = x[:-n].copy()
        x[:n] = head * r + tail * (1 - r)
        return x

    @staticmethod
    def drift(x, cycles=2, db=2.5):
        """A slow breath over the whole buffer, a whole number of cycles so it wraps.

        A non-integer count puts a step at the loop seam: a click every loop.
        """
        g = 10 ** (db / 20)
        return x * (1 + (g - 1) * 0.5 * (1 - np.cos(2 * np.pi * cycles
                                                    * np.arange(len(x)) / len(x))))

    # ---- sources
    def modal(self, dur, partials, jitter=0.0):
        """Sum of decaying sinusoids, (freq, amp, decay seconds) each.

        Inharmonic partials with a decay rate each is why metal sounds like metal.
        """
        x = np.zeros(int(self.sr * dur))
        tt = self.t(dur)
        for f, a, dec in partials:
            f = f * (1 + jitter * self.rng.standard_normal())
            x += a * np.sin(2 * np.pi * f * tt) * np.exp(-tt / dec)
        return x

    def ks(self, dur, freq, damp=0.5, bright=1.0):
        """Karplus-Strong: a noise burst round a delay line with a lowpass in it."""
        SR = self.sr
        n = int(SR * dur)
        L = max(int(SR / freq), 2)
        buf = self.band(self.noise(L / SR), 80, 8000 * bright)[:L]
        out = np.zeros(n)
        for i in range(n):
            out[i] = buf[i % L]
            j = i % L
            buf[j] = (1 - damp) * buf[j] + damp * 0.5 * (buf[j] + buf[(j + 1) % L])
        return out

    def impulses(self, dur, times, gen):
        """Place short events inside a buffer. gen(i) returns the i-th sound."""
        x = np.zeros(int(self.sr * dur))
        for i, when in enumerate(times):
            s = gen(i)
            a = int(self.sr * when)
            b = min(a + len(s), len(x))
            if a < len(x):
                x[a:b] += s[:b - a]
        return x

    # ---- composites
    def room(self, lo, hi, tilt, hum=None, wobble=None, peak=0.16, dur=24.0):
        """A loopable room tone: shaped noise, optional mains hum, a slow wobble.

        Rooms want to be long. A 2.8 s noise loop repeated a thousand times a season
        stops sounding like a room and starts sounding like a loop, and no level fixes
        periodicity. The wobble is quantised to whole cycles per loop so it closes.
        """
        x = self.band(self.noise(dur), lo, hi, tilt)
        if hum:
            for f, a in hum:
                x += a * np.sin(2 * np.pi * f * self.t(dur))
        if wobble:
            rate, depth = wobble
            x = self.am(x, max(1, round(rate * dur)) / dur, depth)
        return self.norm(self.drift(self.loopable(x)), peak)

    def paper(self, dur=0.5, lo=1800, hi=9000, n=2, peak=0.55):
        """Crisp, dry, high. Paper is crackle, not a swoosh."""
        def one(i):
            d = 0.09
            return self.band(self.noise(d), lo, hi, -1) * self.env(d, .002, .035, 5) * (1 - .2 * i)
        return self.norm(self.impulses(dur, [0.02 + i * (dur * .45) for i in range(n)], one), peak)

    def clicks(self, dur, count, freqs, peak=0.5, accel=False, spread=0.0):
        """Small hard ticks: claws, a pencil, a spiral binding."""
        SR = self.sr

        def one(i):
            f = freqs[i % len(freqs)] * (1 + spread * self.rng.standard_normal())
            d = 0.06
            return self.modal(d, [(f, 1, .012), (f * 2.7, .5, .008)]) * self.env(d, .0008, .02, 6)
        if accel:
            pos = np.cumsum(np.linspace(1.4, 0.6, count))
            pos = pos / pos[-1] * dur * .9
            times = list(pos)
            gains = np.linspace(0.35, 1.0, count)
        else:
            times = [dur * (i + .3) / count for i in range(count)]
            gains = np.ones(count)
        x = np.zeros(int(SR * dur))
        for i, when in enumerate(times):
            s = one(i) * gains[i]
            a = int(SR * when)
            b = min(a + len(s), len(x))
            if a < len(x):
                x[a:b] += s[:b - a]
        return self.norm(x, peak)

    def steps(self, count=6, away=True, peak=0.30):
        """Somebody crossing a room, arriving or leaving.

        A step is a heel (a low thump with a body) and a sole rolling down (dry,
        high) a few ms later. One foot lands harder than the other -- without that
        six identical steps read as a machine.
        """
        SR = self.sr
        gap = 0.42
        dur = gap * count + 0.4
        gains = np.linspace(1.0, 0.22, count) if away else np.linspace(0.22, 1.0, count)

        def one(i):
            lean = 1.0 if i % 2 == 0 else 0.78
            heel = self.ks(.20, 108, .74, .5) * self.env(.20, .001, .035, 9) * .9
            sole = self.band(self.noise(.16), 900, 6500, -3) * self.env(.16, .004, .028, 8) * .45
            s = np.zeros(int(SR * .22))
            s[:len(heel)] += heel
            off = int(SR * .022)
            s[off:off + len(sole)] += sole[:len(s) - off]
            return s * gains[i] * lean

        times = [0.05 + i * gap * (1 + .05 * self.rng.standard_normal()) for i in range(count)]
        return self.norm(self.impulses(dur, times, one), peak)

    def hum(self, notes, scale, oct_=0, cents=0, breath=.28, crack=0.0, peak=0.22):
        """A tune sung close-mouthed: sine plus weak harmonics, vibrato, breath.

        notes: [(degree or None for a rest, seconds)]; scale: {degree: Hz}.
        `crack` is a child's voice -- pitch that will not sit still and a body that
        thins out as the note goes on. Zero is an adult humming to herself.
        """
        SR = self.sr
        dur = sum(d for _, d in notes)
        x = np.zeros(int(SR * dur) + SR // 4)
        at = 0.0
        for name, d in notes:
            if name is not None:
                f = scale[name] * 2 ** (oct_ + cents / 1200)
                tt = self.t(d)
                vib = 1 + .006 * np.sin(2 * np.pi * 4.6 * tt)
                if crack:
                    vib = vib + crack * .02 * np.sin(2 * np.pi * 1.3 * tt + self.rng.random() * 6)
                ph = 2 * np.pi * f * np.cumsum(vib) / SR
                body = np.sin(ph) + .22 * np.sin(2 * ph) + .06 * np.sin(3 * ph)
                e = self.env(d, .045, d * .9, .8) * np.minimum(1, np.linspace(1.2, 0, len(tt)) * 4)
                if crack:
                    e *= 1 - crack * .35 * np.linspace(0, 1, len(tt))
                note = self.band(body * e, 140, 2600 + 900 * crack, -2)
                note += self.band(self.noise(d), 700, 5200, -1) * e * breath * .25
                a = int(SR * at)
                x[a:a + len(note)] += note
            at += d
        return self.norm(x, peak)


def scale_of(tonic_hz, steps=(0, 2, 4, 5, 7, 9, 11, 12), names="1 2 3 4 5 6 7 8"):
    """{degree name: Hz} for a scale on tonic_hz. The default is major, degrees 1-8."""
    return {n: tonic_hz * 2 ** (s / 12) for n, s in zip(names.split(), steps)}
