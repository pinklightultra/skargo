"""LOW TIDE's foley: one recipe per cue key, all drawn from ONE seeded Synth.

Recipes run in table order, rooms first, so a rebuild is sample-identical. Add a
recipe at the end and nothing before it changes; add one in the middle and every
sound after it does.

    from examples.demo import sounds
    sounds.build("out/demo/audio/sfx")
"""

import numpy as np

from audiodrama.sound import Synth, build as _build

SEED = 11
S = Synth(22050, seed=SEED)


def gulls(dur=2.4, calls=3):
    """A falling cry with a wobble, a few times, each from a little further off."""
    def one(i):
        d = 0.38
        tt = S.t(d)
        f = (1900 - 900 * tt / d) * (1 + .03 * np.sin(2 * np.pi * 23 * tt))
        ph = 2 * np.pi * np.cumsum(f) / S.sr
        return (np.sin(ph) + .3 * np.sin(2 * ph)) * S.env(d, .02, .25, 2.5) * (1 - .25 * i)
    return S.norm(S.impulses(dur, [0.05 + i * .7 for i in range(calls)], one), .30)


def creak(dur, lo, hi, rate, peak):
    """Friction with a stutter in it: wood under load, rope on a cleat."""
    x = S.am(S.band(S.noise(dur), lo, hi, -3), rate, .9) * S.env(dur, dur * .15, dur * .8, 1.5)
    return S.norm(x, peak)


def thump(freq=90, dur=.25):
    return S.ks(dur, freq, .7, .5) * S.env(dur, .001, .06, 8)


ROOMS = {
    "room-shore": lambda: S.room(80, 2500, -5, None, (0.12, .7), .16),
    "room-postoffice": lambda: S.room(60, 1800, -8, [(100, .04), (200, .02)], None, .10),
    "room-harbour": lambda: S.room(50, 1400, -7, None, (0.30, .5), .13),
    "room-lamproom": lambda: S.room(40, 900, -9, [(60, .05), (120, .03)], (0.05, .3), .12),
    "room-stairwell": lambda: S.room(70, 1600, -6, None, (0.10, .5), .12),
    "room-rock": lambda: S.room(120, 3200, -3, None, (0.08, .6), .18),
}

EVENTS = {
    "gulls": gulls,
    "steps": lambda: S.steps(6, away=False),
    "cork": lambda: S.norm(S.band(S.noise(.12), 500, 3500, -2) * S.env(.12, .001, .03, 6), .45),
    "paper": lambda: S.paper(),
    "bottle": lambda: S.norm(S.modal(1.2, [(1480, 1, .25), (2210, .5, .18), (3900, .25, .08)])
                             * S.env(1.2, .001, .5, 3), .45),
    "clock": lambda: S.clicks(4.0, 8, [2400, 1900], .30),
    "radio": lambda: S.norm(S.am(S.band(S.noise(3.0), 300, 3000, -2), 3.1, .6), .16),
    "doorbell": lambda: S.norm(S.modal(2.0, [(2093, 1, .9), (2637, .6, .7), (3136, .4, .5)])
                               * S.env(2.0, .001, 1.6, 1.5), .35),
    "door": lambda: S.norm(np.concatenate([creak(1.1, 300, 1400, 9, .5),
                                           thump(70, .5)]), .55),
    "switch": lambda: S.clicks(0.3, 1, [900], .55),
    "drawer": lambda: S.norm(np.concatenate([creak(.6, 200, 2500, 30, .4), thump(140, .2)]), .45),
    "rope": lambda: creak(1.5, 200, 900, 7, .35),
    "surf": lambda: S.norm(S.band(S.noise(3.0), 60, 3000, -4) * S.env(3.0, .6, 2.4, 2), .55),
    "tin": lambda: S.norm(S.modal(.8, [(620, 1, .2), (1370, .6, .12), (2450, .3, .07)], jitter=.01)
                          * S.env(.8, .001, .4, 3), .45),
    "lamp": lambda: S.norm(sum(a * np.sin(2 * np.pi * f * S.t(2.5)) for f, a in
                               ((60, 1), (120, .5), (180, .2)))
                           * np.linspace(0, 1, int(S.sr * 2.5)) ** 2, .25),
    "bolt": lambda: S.norm(S.band(S.noise(.5), 500, 4000, -2) * S.env(.5, .01, .3, 4)
                           + S.modal(.5, [(880, .6, .08)]), .45),
    "franking": lambda: S.norm(S.impulses(2.0, [.1, .7, 1.3], lambda i: thump()), .55),
}

RECIPES = {**ROOMS, **EVENTS}


def build(outdir):
    """Render every recipe to outdir. Reseeds first, so a second build in the same
    process makes the same files as the first."""
    S.rng = np.random.default_rng(SEED)
    return _build(RECIPES, outdir, S.sr)
