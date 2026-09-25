"""Measuring a mix: where each music placement sits against the programme, and
cutting single scenes out of several casts for an A/B.

    runs = music_levels(mixer, n, tl)
    for r in runs: print(r)

    wav, lens, notes = compare_scenes(mixers, n, tl, [1, 6])
"""

import numpy as np


def moving_mean(x, w):
    """np.convolve(x, np.ones(w) / w, "same") by running sums: O(n), not O(n * w).
    Over an episode at a 100 ms window the convolution was most of a levels run."""
    if w > len(x):
        return np.convolve(x, np.ones(w) / w, "same")
    c = np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])
    k = np.arange(len(x)) + (w - 1) // 2          # "same" keeps the centre of "full"
    hi = np.minimum(k, len(x) - 1) + 1
    lo = np.maximum(k - w + 1, 0)
    return (c[hi] - c[lo]) / w


def music_levels(mixer, n, tl, pod=None, sr=None):
    """Each music run in an episode as {at, secs, music, prog, delta_db}.

    The diff of a music-on and a music-off render isolates the music exactly, provided
    the master limiter is out of the way -- otherwise a peak over the ceiling rescales
    the whole mix and the diff picks up a copy of the speech. So master goes to 10.

    The control render keeps every slot at its own length and zeroes it rather than
    removing it: the title theme holds the cut open, so an absent-music render is
    shorter, stops being time-aligned, and the diff reports the whole programme
    sliding against itself as one long run.

    Runs are found on a 100 ms envelope with a 0.5 s gap tolerance, not on zero
    crossings: splitting on the music's own crossings reported 580 runs for 7
    placements.

    Returns (runs, info). info has minutes, music_seconds and peak (music-on, unlimited).
    The mixer is not modified.
    """
    sr = sr or mixer.sr
    saved_cfg, saved_music = mixer.cfg, mixer.music
    try:
        mixer.cfg = dict(saved_cfg, master=10.0)
        on = mixer.build(n, tl, pod, [])[0]
        mixer.music = {k: np.zeros_like(v) for k, v in saved_music.items()}
        off = mixer.build(n, tl, pod, [])[0]
    finally:
        mixer.cfg, mixer.music = saved_cfg, saved_music

    m = min(len(on), len(off))
    mus, prog = on[:m] - off[:m], off[:m]
    w = int(0.1 * sr)
    envl = moving_mean(np.abs(mus), w)
    live = envl > 3e-4
    gap = int(0.5 * sr)
    idx = np.flatnonzero(np.diff(np.concatenate([[0], live.view(np.int8), [0]])))
    runs = []
    for a, b in zip(idx[::2], idx[1::2]):
        if runs and a - runs[-1][1] < gap:
            runs[-1][1] = b
        else:
            runs.append([a, b])

    out = []
    for a, b in runs:
        mr = float(np.sqrt((mus[a:b] ** 2).mean()))
        pr = float(np.sqrt((prog[a:b] ** 2).mean()))
        d = 20 * np.log10(mr / pr) if pr > 1e-9 else float("inf")
        out.append({"at": a / sr, "secs": (b - a) / sr, "music": mr, "prog": pr,
                    "delta_db": d})
    info = {"minutes": m / sr / 60,
            "music_seconds": float((np.abs(mus) > 1e-4).sum() / sr),
            "peak": float(np.max(np.abs(on))) if len(on) else 0.0}
    return out, info


def print_levels(n, runs, info, ceiling=0.89, log=print):
    log("EP%d  %.1f min  music-only energy in %.1fs of it"
        % (n, info["minutes"], info["music_seconds"]))
    log("%d runs\n  %-9s %6s  %8s  %8s  %7s" % (len(runs), "at", "secs", "music", "prog",
                                                "delta"))
    for r in runs:
        d = r["delta_db"]
        log("  %2d:%05.2f %6.1f  %8.4f  %8.4f  %+6.1f dB"
            % (r["at"] // 60, r["at"] % 60, r["secs"], r["music"], r["prog"],
               d if np.isfinite(d) else 99))
    log("\nfull-mix peak with music %.3f (ceiling %.2f)" % (info["peak"], ceiling))


def scenes_of(tl, slug="slug"):
    """Split an episode timeline on its slugs, keeping foley and ad events in place.
    Index 0 is whatever precedes the second slug (usually the recap and cold open)."""
    out, cur = [], []
    for ev in tl:
        if ev["kind"] == slug and any(e["kind"] == slug for e in cur):
            out.append(cur)
            cur = []
        cur.append(ev)
    if cur:
        out.append(cur)
    return out


def compare_scenes(mixers, n, tl, want, gap=1.5, pod=None):
    """One signal with scene `want[i]` rendered by each mixer in turn, 1.5 s apart.

    mixers: [(name, Mixer)] -- typically the same sfx and music with different
    `sources`. It reuses Mixer.build on a slice of the timeline, so every pass gets
    the real foley, beds, music and pacing; a voices-only concatenation would be
    easier and would flatter no cast honestly.

    Returns [(scene index, slug, signal, [(name, secs, borrowed, missing, spoken)])].
    A pass that borrowed every line IS the fallback cast -- the caller should say so.
    Raises IndexError for a scene that does not exist.
    """
    scenes = scenes_of(tl)
    out = []
    for idx in want:
        if not 0 <= idx < len(scenes):
            raise IndexError("EP%d has scenes 0..%d" % (n, len(scenes) - 1))
        sc = scenes[idx]
        slug = next((e["raw"] for e in sc if e["kind"] == "slug"), "(no slug)")
        spoken = sum(1 for e in sc if e.get("wav"))
        parts, rows = [], []
        for name, mx in mixers:
            x, _, missing, _, borrowed, _ = mx.build(n, sc, pod, [])
            silence = np.zeros(int(gap * mx.sr), dtype=np.float32)
            parts += [x, silence]
            rows.append((name, len(x) / mx.sr, borrowed, missing, spoken))
        out.append((idx, slug, np.concatenate(parts), rows))
    return out
