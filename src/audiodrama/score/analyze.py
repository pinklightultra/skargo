"""The measurements a slot pick is made on. Each returns ranked candidates, not a verdict.

Everything takes a mono signal and its rate. The four tests, one per role:

    calmest_window   a scene bed: the window of a length whose 1 s loudness travels
                     least (10th-90th percentile spread, dB). A bed has a minute that
                     must not pull the ear off a line.
    sting_onset      an act-out: the frame whose loudness most exceeds the frame
                     0.4 s before it. That is what "hits" means. Start a little
                     early -- a clipped attack is worse than a hair of pre-roll.
    figure_windows   an act-in: a short window whose loudest 0.1 s frame falls in its
                     first quarter (a cue announces itself, a fade does not), with a
                     crest factor near 6 (a swell measures 2.5, a hit 12). Darker wins.
    steady_windows   a recap bed: dark (low centroid) and even (low CV of loudness).

These are the scripts the reference show's picks were made with, lifted as they ran.
It measured stings, act-ins and recap beds at the track's OWN rate (44.1 kHz,
downmixed, not resampled) and scene beds at the drama rate. A centroid depends on the
rate, so measure at the rate a recorded number was taken at to reproduce it.
"""

import numpy as np


def frames(x, sr, hop=0.05, win=0.10):
    """(times s, rms) of overlapping `win` frames every `hop`."""
    h, n = int(hop * sr), int(win * sr)
    idx = np.arange(0, max(1, len(x) - n), h)
    return idx / sr, np.array([np.sqrt((x[i:i + n] ** 2).mean()) for i in idx])


def centroid(x, sr):
    """Spectral centroid (Hz) of the whole signal, one Hann-windowed FFT."""
    X = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return float((f * X).sum() / max(X.sum(), 1e-12))


def second_rms(x, sr):
    """RMS of each whole second."""
    k = len(x) // sr
    fr = x[:k * sr].reshape(k, sr)
    return np.sqrt((fr ** 2).mean(1)) + 1e-9


def calmest_window(x, sr, seconds):
    """[(spread dB, start s)] for every whole-second window of `seconds`, calmest first.

    A window longer than the track is shortened to two seconds under its length.
    """
    rms = second_rms(x, sr)
    k = len(rms)
    want = min(int(seconds), k - 2)
    out = []
    for s in range(0, k - want + 1):
        w = rms[s:s + want]
        out.append((float(20 * np.log10(np.percentile(w, 90) / np.percentile(w, 10))),
                    float(s)))
    return sorted(out)


def sting_onset(x, sr, before=0.4, tail=3.0, preroll=0.06, top=5, hop=0.05, win=0.10):
    """[(rise, onset s, suggested start s)], biggest rise first.

    The rise is a frame's RMS minus the RMS `before` seconds earlier, linear.
    Frames within `tail` seconds of the end are skipped so a sting fits.
    """
    t, e = frames(x, sr, hop, win)
    back = int(before / hop)
    rise = np.zeros_like(e)
    if len(e) > back + 1:
        prev = np.concatenate([np.full(back, e[0]), e[:-back]])
        rise = e - prev
    ok = np.flatnonzero(t < max(0.0, len(x) / sr - tail))
    order = ok[np.argsort(-rise[ok], kind="stable")][:top]
    return [(float(rise[i]), round(float(t[i]), 3), round(max(float(t[i]) - preroll, 0.0), 3))
            for i in order]


def figure_windows(x, sr, seconds=3.0, step=1.0, frame=0.1, floor=5e-3, head=0.25,
                   crest_target=6.0, late_weight=6.0, brightness=4000.0):
    """[(score, start s, loudest-frame position 0..1, crest, centroid Hz)], best first.

    score = late_weight * how far past `head` the loudest frame falls
          + |log2(crest / crest_target)|
          + centroid / brightness
    Windows whose mean frame RMS is under `floor` are too quiet to be a cue at all.
    """
    out = []
    h = int(frame * sr)
    for start in np.arange(0, len(x) / sr - seconds, step):
        seg = x[int(start * sr):int((start + seconds) * sr)]
        e = np.array([np.sqrt((seg[i:i + h] ** 2).mean()) for i in range(0, len(seg) - h, h)])
        if e.mean() < floor:
            continue
        loud = int(np.argmax(e)) / len(e)
        crest = float(np.abs(seg).max() / max(np.sqrt((seg ** 2).mean()), 1e-9))
        pen = max(0.0, loud - head) * late_weight + abs(np.log2(max(crest, 1e-6) / crest_target))
        c = centroid(seg, sr)
        out.append((float(pen + c / brightness), float(start), loud, crest, c))
    return sorted(out)


def steady_windows(x, sr, seconds=28.0, step=4.0, brightness=1000.0, cv_weight=2.0):
    """[(score, start s, centroid Hz, evenness, mean rms)], best first.

    Evenness is the coefficient of variation of 0.1 s frame RMS inside the window
    (lower is steadier); score = centroid / brightness + cv_weight * evenness.
    """
    out = []
    for start in np.arange(0, max(0.0, len(x) / sr - seconds), step):
        seg = x[int(start * sr):int((start + seconds) * sr)]
        if len(seg) < sr * 5:
            continue
        _, se = frames(seg, sr)
        cv = float(se.std() / max(se.mean(), 1e-9))
        c = centroid(seg, sr)
        out.append((c / brightness + cv * cv_weight, float(start), c, cv, float(se.mean())))
    return sorted(out)
