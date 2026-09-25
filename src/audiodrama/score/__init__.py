"""Music scoring: slots cut from a song backlog, and the measurements picks are made on.

    from audiodrama.score import Backlog, fold_config, build_slots
    bl = Backlog(["~/music/export", "~/music/loose"])
    cfg = fold_config(MY_SLOTS, "audio/music.json")
    build_slots(cfg, bl, "audio/music", order=list(MY_SLOTS), speech_rms=0.0705)

Roles the mixer understands: titles, actin_<ordinal>, actout_<ordinal|cold|end>,
recap_ep<N>, scene_<genre>.
"""

from .slots import Backlog, cut, slot, fold_config, build_slots, profile, speech_rms
from . import analyze

__all__ = ["Backlog", "cut", "slot", "fold_config", "build_slots", "profile",
           "speech_rms", "analyze"]
