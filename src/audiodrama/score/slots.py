"""Music slots: cuts from a song backlog, levelled against the show's own speech.

A slot is a named cut, `role` or `role_variant`:

    {"track": "theme.wav", "start": 0.0, "seconds": 26.0,
     "rms_db": -2.0, "fade_in": 0.8, "fade_out": 3.5}

`rms_db` is relative to the show's measured speech RMS, NOT a peak level. Peak gain
lies: a dense mixdown at peak 0.30 measured +10 dB over the narration it was meant to
sit under, because a music bed's crest factor is nothing like a spoken line's.
Measure speech with `speech_rms` over a few hundred rendered lines and pass it in.

The mixer resolves `role_variant` first and falls back to `role`, so a config with
one slot in it still plays that slot everywhere -- which is how you audition an idea.
"""

import hashlib
import json
import random
from pathlib import Path

import numpy as np

from ..sound.wavio import read_any, to_rate, write_int16, read_int16, WavError


class Backlog:
    """One or more folders of source tracks. A slot names a FILE, not a root: which
    folder a song sits in is not a fact about the song. Earlier roots win."""

    def __init__(self, roots):
        self.roots = [Path(r) for r in roots]

    def find(self, name):
        for root in self.roots:
            p = root / name
            if p.exists():
                return p
        raise FileNotFoundError("%s is in none of the backlog roots" % name)

    def tracks(self):
        """[(path, signal, rate, error)] for every distinct .wav, deduped on the whole PCM.

        Not on a head hash (tracks that fade in from silence collide) and not on the
        filename (exports double every file as `name (1).wav`).
        """
        seen, out = {}, []
        for root in self.roots:
            if not root.exists():
                continue
            for p in sorted(root.iterdir()):
                if not p.is_file() or p.suffix.lower() != ".wav":
                    continue
                try:
                    x, rate = read_any(p)
                except WavError as e:
                    out.append((p, None, None, str(e)))
                    continue
                h = hashlib.sha1(x.tobytes()).hexdigest()
                if h in seen:
                    continue
                seen[h] = p.name
                out.append((p, x, rate, ""))
        return out


def cut(spec, x, rate, sr=22050, speech_rms=0.0705, peak_cap=0.85, log=print):
    """Cut, resample, fade and level one slot from an already-read track."""
    a = int(spec["start"] * rate)
    b = a + int(spec["seconds"] * rate)
    if a >= len(x):
        raise ValueError("%s: start %.1fs is past the end (%.1fs)"
                         % (spec["track"], spec["start"], len(x) / rate))
    out = to_rate(x[a:min(b, len(x))], rate, sr)
    for key, sign in (("fade_in", 1), ("fade_out", -1)):
        n = min(int(spec[key] * sr), len(out) // 2)
        if n > 0:
            ramp = np.linspace(0, 1, n)
            if sign > 0:
                out[:n] *= ramp
            else:
                out[-n:] *= ramp[::-1]
    rms = np.sqrt((out ** 2).mean())
    if rms <= 0:
        return out
    out = out * (speech_rms * 10 ** (spec["rms_db"] / 20) / rms)
    # an RMS target can still clip a transient, so cap the peak and say so
    peak = np.max(np.abs(out))
    if peak > peak_cap:
        if log:
            log("    (peak %.2f, scaled to %.2f -- this track has a hot transient)"
                % (peak, peak_cap))
        out *= peak_cap / peak
    return out


def slot(spec, backlog, **kw):
    x, rate = read_any(backlog.find(spec["track"]))
    return cut(spec, x, rate, **kw)


def fold_config(defaults, path, log=print):
    """Defaults with a JSON config folded over them per ROLE, not per file.

    A whole-dict merge means editing one field of one slot silently drops every
    field you did not retype. If the file is missing it is written from defaults.
    """
    cfg = {k: dict(v) for k, v in defaults.items()}
    path = Path(path)
    if path.exists():
        for role, spec in json.loads(path.read_text(encoding="utf-8")).items():
            cfg.setdefault(role, {}).update(spec)
        if log:
            log("using %s" % path.name)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(defaults, indent=1), encoding="utf-8")
        if log:
            log("wrote %s with the default picks; edit and re-run" % path.name)
    return cfg


def build_slots(cfg, backlog, outdir, order=(), sr=22050, speech_rms=0.0705, log=print):
    """Write every configured slot to outdir/<name>.wav; remove any slot no longer
    configured (the mixer's role fallback would otherwise keep playing it)."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    order = list(order)
    built = {}
    for name in sorted(cfg, key=lambda k: (order.index(k) if k in order else len(order), k)):
        spec = cfg[name]
        sig = slot(spec, backlog, sr=sr, speech_rms=speech_rms, log=log)
        write_int16(outdir / ("%s.wav" % name), sig, sr)
        built[name] = sig
        if log:
            log("  %-13s %-24s %5.1fs  %+.0f dB vs speech  rms %.4f  peak %.2f"
                % (name, spec["track"], len(sig) / sr, spec["rms_db"],
                   np.sqrt((sig ** 2).mean()), np.max(np.abs(sig))))
    for p in sorted(outdir.glob("*.wav")):
        if p.stem not in cfg:
            p.unlink()
            if log:
                log("  removed %s (no longer configured)" % p.name)
    if log:
        roles = sorted({n.split("_")[0] for n in cfg})
        log("%d slots in %s, from %d of the backlog's tracks"
            % (len(cfg), "/".join(roles), len({s["track"] for s in cfg.values()})))
    return built


def profile(backlog, sr=22050):
    """What is in a backlog, choosing nothing: one row per distinct track.

    centroid (Hz), voice (share of energy in 300-3400 Hz, where speech lives),
    range (10th-90th percentile spread of 1 s loudness, dB), rms (median 1 s RMS).
    A bed wants long, dark, steady and out of the voice band; a sting needs none of
    that and only two seconds.
    """
    rows = []
    for p, x, rate, err in backlog.tracks():
        if err:
            rows.append({"track": p.name, "error": err})
            continue
        try:
            d = to_rate(x, rate, sr)
        except WavError as e:        # 48 kHz: one export setting must not sink the survey
            rows.append({"track": p.name, "error": str(e)})
            continue
        k = len(d) // sr
        if k < 1:
            rows.append({"track": p.name, "seconds": len(d) / sr, "error": "under a second"})
            continue
        fr = d[:k * sr].reshape(k, sr)
        rms = np.sqrt((fr ** 2).mean(1)) + 1e-9
        F = np.abs(np.fft.rfft(fr * np.hanning(sr), axis=1))
        f = np.fft.rfftfreq(sr, 1.0 / sr)
        rows.append({
            "track": p.name, "seconds": len(d) / sr,
            "centroid": float((F * f).sum() / (F.sum() + 1e-9)),
            "voice": float(F[:, (f > 300) & (f < 3400)].sum() / (F.sum() + 1e-9)),
            "range": float(20 * np.log10(np.percentile(rms, 90) / np.percentile(rms, 10))),
            "rms": float(np.median(rms)),
        })
    return rows


def speech_rms(line_dir, n=300, seed=0):
    """(mean, median) RMS over n random rendered lines: the reference every slot's
    rms_db is relative to."""
    files = sorted(Path(line_dir).glob("*.wav"))
    if not files:
        raise FileNotFoundError("no wavs in %s" % line_dir)
    pick = random.Random(seed).sample(files, min(n, len(files)))
    vals = []
    for p in pick:
        x = read_int16(p)
        if len(x):
            vals.append(float(np.sqrt((x.astype(np.float64) ** 2).mean())))
    return float(np.mean(vals)), float(np.median(vals))
