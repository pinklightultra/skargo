"""Assemble rendered lines, foley and music slots into a finished episode.

Everything is mixed as float32 in numpy. No ffmpeg.

How time works. The clock only advances for things that are heard in sequence:
each line's own length plus a gap, a pre-scene beat before each slug, a hold after
each act-out, the ad pod. Foley and music never advance it, with ONE exception --
the main titles theme, which gets its own time because the Main Titles card is the
last event of the cold open and an overlaid theme would run through the act-out
sting and into the pod. A muted sound still costs no time, so muting never moves
the cut.

Room tones are beds: a `room-*` foley cue opens one that tiles under everything
until the next room cue, slug, ad pod or the main titles. Event sounds land at the
moment their cue fired.

Music rides events that already exist in the timeline (cards, act-outs, annotator
genre tags), so scoring never adds a marker -- a marker is an event, and a new event
renumbers every wav after it.

    seam music    titles, actin_<n>, actout_<n>, recap_ep<N>: placed at a moment
    scene music   scene_<genre>: opened by an annotator tag naming a genre, closed by
                  the next genre tag, a slug, an act-out, an ad, or an empty tag
                  (the annotator failing to name the scene kills its score)

A long scene bed is taken as a window at an offset derived from the firing event's
index, so a genre that fires twenty times a season does not play the same seventy
seconds twenty times, and the player and this file cannot disagree about which.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..sound.wavio import read_int16, write_int16

# The player's vocabulary, so a saved mixconfig.json needs no translation.
DEFAULT_CFG = {
    "gap": 0.26,          # between consecutive utterances
    "gapSlug": 0.45,      # a beat to let a location land
    "gapSpeech": 0.34,    # dialogue needs a little more air than narration
    "preScene": 0.7,      # silence before a new slug
    "actout": 1.6,        # air after the last line of an act
    "pod": 6.0,           # a real pod is 150 s; nobody auditions that
    # Ambience belongs 20-30 dB down: the thing you notice when it stops. 0.13 put
    # the reference show's beds near -26 dB under dialogue.
    "bed": 0.13,
    "sfx": 0.55,
    "music": 1.0,         # slots are already levelled against speech
    "speech": 1.0,
    "master": 0.89,       # peak ceiling
    "muted_keys": [],     # foley keys to silence
    "off": {},            # bus -> False: bed, sfx, music, dial, sys, narr
}


def load_config(path, base=None):
    """(cfg, kept): base (default DEFAULT_CFG) with a JSON file folded over it,
    ignoring keys this mixer does not own. kept is None when there is no file."""
    cfg = dict(DEFAULT_CFG if base is None else base)
    path = Path(path)
    if not path.exists():
        return cfg, None
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = {k: v for k, v in data.items() if k in cfg}
    cfg.update(kept)
    return cfg, kept


ORDINALS = ("one", "two", "three", "four", "five")
GENRES = ("comedy", "family", "horror", "drama", "farce",
          "procedural", "whimsy", "spectacle")


@dataclass
class ScoreRules:
    """What in the timeline fires which music. Defaults match the reference show."""
    genre_prefix: str = "System. Genre:"
    genres: tuple = GENRES
    ordinals: tuple = ORDINALS
    scene_cap: float = 75.0       # longest a scene bed plays before it gets out of the way
    scene_floor: float = 12.0     # under this a bed is a stab; quick re-labels get nothing
    window_fade: float = 1.2
    recap_tail: float = 1.8
    titles_card: str = "Main Titles"
    act_card: str = "Act "
    recap_open: str = "Previously On"
    recap_close: str = "Cold Open"
    room_prefix: str = "room-"
    bus_of: dict = field(default_factory=lambda: {"speech": "dial", "system": "sys"})
    default_bus: str = "narr"

    def variant_of(self, text):
        """`three` from "END OF ACT THREE" or "Act Three.", `cold` / `end` for the ends."""
        t = text.upper().rstrip(".")
        if "COLD OPEN" in t:
            return "cold"
        if t.startswith("END OF EPISODE"):
            return "end"
        last = t.split()[-1].lower()
        return last if last in self.ordinals else None

    def genre_of(self, text):
        """The base genre an annotator tag names, or None when it said anything else.

        None is a real answer: a scene the annotator declines to name gets no music.
        A modifier ("Comedy, Load-Bearing") is ignored -- the joke is in the modifier
        and the music is not in on the joke.
        """
        if not text.startswith(self.genre_prefix):
            return None
        said = text.split(":", 1)[1].strip().rstrip(".").lower()
        for g in self.genres:
            if said.startswith(g):
                return g
        return None


class Buf:
    """A growable mono mix buffer addressed in seconds."""

    def __init__(self, sr=22050):
        self.sr = sr
        self.x = np.zeros(sr * 60, dtype=np.float32)
        self.end = 0

    def _fit(self, n):
        while n > len(self.x):
            self.x = np.concatenate([self.x, np.zeros(len(self.x), dtype=np.float32)])

    def add(self, at, sig, gain=1.0):
        a = int(at * self.sr)
        b = a + len(sig)
        self._fit(b)
        self.x[a:b] += sig * gain
        self.end = max(self.end, b)

    def tile(self, start, stop, sig, gain=1.0, fade=0.25):
        """Lay a loopable bed across a span, faded so a scene change is not a click."""
        a, b = int(start * self.sr), int(stop * self.sr)
        if b <= a or len(sig) == 0:
            return
        self._fit(b)
        reps = int(np.ceil((b - a) / len(sig)))
        bed = np.tile(sig, reps)[:b - a]
        f = min(int(fade * self.sr), len(bed) // 4)
        if f > 0:
            bed[:f] *= np.linspace(0, 1, f)
            bed[-f:] *= np.linspace(1, 0, f)
        self.x[a:b] += bed * gain
        self.end = max(self.end, b)

    def done(self):
        return self.x[:self.end].copy()


def window(sig, seconds, seed, sr=22050, fade=1.2):
    """`seconds` out of a long bed at an offset derived from the firing event's index."""
    n = min(int(seconds * sr), len(sig))
    room = len(sig) - n
    out = sig[(seed * 7919) % room:][:n].copy() if room > 0 else sig[:n].copy()
    f = min(int(fade * sr), len(out) // 3)
    if f > 0:
        out[:f] *= np.linspace(0, 1, f)
        out[-f:] *= np.linspace(1, 0, f)
    return out


def load_dir(d):
    """{stem: signal} for every wav in a folder (sfx or music). Empty if absent."""
    d = Path(d)
    if not d.exists():
        return {}
    return {p.stem: read_int16(p) for p in d.glob("*.wav")}


class Mixer:
    """sfx, music: {key: signal}. sources: line folders in priority order; a line
    missing from the first is taken from a later one and counted as fell_back, so a
    half-rendered cast still assembles end to end."""

    def __init__(self, sfx, music=None, sources=(), cfg=None, rules=None, sr=22050):
        self.sfx = sfx
        self.music = music or {}
        self.sources = [Path(s) for s in sources]
        self.cfg = dict(DEFAULT_CFG if cfg is None else cfg)
        self.rules = rules or ScoreRules()
        self.sr = sr

    def find_line(self, wav):
        for d in self.sources:
            p = d / wav
            if p.exists():
                return p, d is not self.sources[0]
        return None, False

    def gap_for(self, ev):
        if ev["kind"] == "slug":
            return self.cfg["gapSlug"]
        if ev["kind"] == "speech":
            return self.cfg["gapSpeech"]
        return self.cfg["gap"]

    def build(self, n, tl, pod=None, report=None):
        """One episode. Returns (signal, sfx placed, missing, muted, fell back, music placed).

        report, if a list, receives (time, "AD id") for every pod.
        """
        CFG, R, SR, sfx, music = self.cfg, self.rules, self.sr, self.sfx, self.music
        pod = CFG["pod"] if pod is None else pod
        report = [] if report is None else report
        buf = Buf(SR)
        t = 0.0
        bed_key, bed_start = None, 0.0
        placed_sfx = missing = muted = fell_back = placed_music = 0
        off = CFG["off"]
        dead = set(CFG["muted_keys"])

        def close_bed(at):
            nonlocal bed_key
            if bed_key and bed_key in sfx:
                buf.tile(bed_start, at, sfx[bed_key], CFG["bed"])
            bed_key = None

        # a scene bed plays its own length up to scene_cap and the rest of the scene
        # is dry: a loop point inside a bar is audible where one inside a room is not
        score_key, score_start, score_i = None, 0.0, 0

        def close_score(at):
            nonlocal score_key, placed_music
            if score_key:
                span = at - score_start
                sig = music.get("scene_%s" % score_key)
                if span >= R.scene_floor and sig is not None and off.get("music") is not False:
                    buf.add(score_start, window(sig, min(span, R.scene_cap), score_i,
                                                SR, R.window_fade), CFG["music"])
                    placed_music += 1
            score_key = None

        # the recap is bounded by its own two cards; recap NARRATION is not the same
        # thing (a recap of five quoted clips has none)
        recap_from = recap_to = None
        titles_until = 0.0

        def fit(sig, seconds, tail=R.recap_tail):
            n_ = int((seconds + tail) * SR)
            if n_ >= len(sig):
                return sig
            out = sig[:n_].copy()
            f = min(int(tail * SR), len(out))
            out[-f:] *= np.linspace(1, 0, f)
            return out

        def cue_music(role, at, span=None, variant=None):
            """Overlay a seam slot without advancing the clock; role_variant wins."""
            nonlocal placed_music
            sig = music.get("%s_%s" % (role, variant)) if variant else None
            if sig is None:
                sig = music.get(role)
            if sig is None or off.get("music") is False:
                return 0.0
            if span:
                sig = fit(sig, span)
            buf.add(at, sig, CFG["music"])
            placed_music += 1
            return len(sig) / SR

        for i, ev in enumerate(tl):
            k = ev["kind"]

            if k == "slug":
                close_bed(t)
                close_score(t)
                t += CFG["preScene"]

            if k == "foley":
                key = ev["key"]
                if key not in sfx:
                    missing += 1
                    continue
                room = key.startswith(R.room_prefix)
                if key in dead or off.get("bed" if room else "sfx") is False:
                    muted += 1
                    continue
                if room:
                    close_bed(t)
                    bed_key, bed_start = key, t
                else:
                    buf.add(t, sfx[key], CFG["sfx"])
                    placed_sfx += 1
                continue

            if k == "ad":
                close_bed(t)
                close_score(t)
                t += 0.5
                report.append((t, "AD %s" % ev["id"]))
                t += pod
                continue

            if k == "actout":
                # END OF ACT n then END OF EPISODE is one moment written twice: sting
                # only the second
                nxt = tl[i + 1]["kind"] if i + 1 < len(tl) else None
                close_score(t)
                if nxt != "actout":
                    cue_music("actout", t, variant=R.variant_of(ev.get("text", "")))
                t += CFG["actout"]
                continue

            if k == "sysfail":
                close_score(t)
                t += ev.get("hold", 1.4)
                continue

            if k == "system":
                g = R.genre_of(ev.get("text", ""))
                if g:
                    close_score(t)
                    score_key, score_start, score_i = g, t, i

            if k == "card":
                if ev["text"].startswith(R.titles_card):
                    # the one slot that advances the clock; a title sequence is not in
                    # a kitchen, so the room tone goes with it
                    close_bed(t)
                    close_score(t)
                    titles_until = t + cue_music("titles", t) + CFG["preScene"]
                elif ev["text"].startswith(R.act_card):
                    cue_music("actin", t, variant=R.variant_of(ev["text"]))
                elif ev["text"].startswith(R.recap_open):
                    recap_from = t
                elif ev["text"].startswith(R.recap_close) and recap_from is not None \
                        and recap_to is None:
                    recap_to = t

            wav = ev.get("wav")
            if not wav:
                continue
            p, borrowed = self.find_line(wav)
            if p is None:
                missing += 1
                continue
            fell_back += borrowed
            sig = read_int16(p)
            # a muted voice keeps its slot: you are auditioning the mix, not recutting
            if off.get(R.bus_of.get(k, R.default_bus)) is False:
                muted += 1
            else:
                buf.add(t, sig, CFG["speech"])
            t += len(sig) / SR + self.gap_for(ev) + ev.get("hold", 0.0)
            t = max(t, titles_until)

        close_bed(t)
        close_score(t)
        # laid last: its length is only known once the block has been walked
        if recap_from is not None:
            cue_music("recap", recap_from, (recap_to or t) - recap_from, "ep%d" % n)
        x = buf.done()

        peak = np.max(np.abs(x)) if len(x) else 0.0
        if peak > CFG["master"]:
            x = x * (CFG["master"] / peak)
        return x, placed_sfx, missing, muted, fell_back, placed_music


def write(p, x, sr=22050):
    write_int16(p, x, sr)
