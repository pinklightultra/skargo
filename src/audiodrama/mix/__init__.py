"""Mixing: lines + foley + music slots -> an episode, and the measurements on it.

    from audiodrama.mix import Mixer, load_dir, load_config, write
    cfg, _ = load_config("audio/mixconfig.json")
    mx = Mixer(load_dir("audio/sfx"), load_dir("audio/music"),
               sources=["audio/lines_edge", "audio/lines"], cfg=cfg)
    x, sfx, missing, muted, borrowed, music = mx.build(1, timeline["1"])
    write("EP1.wav", x)
"""

from .mixer import (DEFAULT_CFG, GENRES, ORDINALS, Buf, Mixer, ScoreRules, load_config,
                    load_dir, window, write)
from .measure import music_levels, print_levels, scenes_of, compare_scenes
from .export import encode, encode_all

__all__ = ["DEFAULT_CFG", "GENRES", "ORDINALS", "Buf", "Mixer", "ScoreRules",
           "load_config", "load_dir", "window", "write", "music_levels", "print_levels",
           "scenes_of", "compare_scenes", "encode", "encode_all"]
