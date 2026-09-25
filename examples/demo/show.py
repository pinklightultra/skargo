"""LOW TIDE as an audiodrama configuration: every table that is about this show and
not about audio drama in general, turned into library objects.

A new show copies this folder and replaces the contents. The library under src/ never
imports from here.
"""

import re
from pathlib import Path

from audiodrama.mix import ScoreRules
from audiodrama.qa import DraftCheck, Prop
from audiodrama.script import FoleyRules, Show
from audiodrama.voice import TimelineParser
from audiodrama.voice.sapi import DAVID, ZIRA

HERE = Path(__file__).resolve().parent
PARTS = HERE / "parts"
TITLE = "LOW TIDE"

# ---- the episode cut: {global scene number: ("ep"|"act", number, note)}
MARKS = {
    1: ("ep", 1, "The Causeway"),
    2: ("act", 1, "the post office"),
    4: ("act", 2, "the rock"),
    5: ("ep", 2, "High Water"),
    6: ("act", 1, "the lamp room"),
    7: ("act", 2, "the morning post"),
}

# Recaps are authored. A quoted clip must be a line its speaker really said in the
# previous episode; the draft check proves it.
RECAPS = {
    2: [(None, "A bottle came in on the tide, with a letter inside."),
        ("TOBY", "Who writes a joke and puts it in the sea?"),
        ("MAEVE", "There's only one light. And it has been dark for twenty years."),
        ("IRIS", "You took your time. Did you bring the stamps?")],
}

LOGLINES = {
    1: "A letter washes up at the island post office, sent from a lighthouse that "
       "has been dark for twenty years.",
    2: "The keeper of the light has been writing the whole time, and every letter is "
       "addressed to the same house.",
}

SHOW = Show(title=TITLE, credit="a two-part radio mystery", draft_date="2026",
            recaps=RECAPS, loglines=LOGLINES)

# ---- foley: rooms by slug (first match wins, so narrow before broad), events by
# action line. Keys starting room- are beds; the rest are placed where they fire.
ROOMS = [
    (r"CAUSEWAY", "room-shore", "the sea coming back over sand"),
    (r"INT\. POST OFFICE", "room-postoffice", "a small shop at night"),
    (r"HARBOUR", "room-harbour", "water against a jetty"),
    (r"LAMP ROOM", "room-lamproom", "glass in the wind, the lamp turning"),
    (r"INT\. LIGHTHOUSE", "room-stairwell", "wind in a stone tower"),
    (r"EXT\. LIGHTHOUSE", "room-rock", "wind and surf on three sides"),
]
EVENTS = [
    (r"\bgulls?\b", "gulls", "gulls overhead"),
    (r"\bruns\b|\bclimbs?\b|\bsprints\b", "steps", "footsteps"),
    (r"\bcork\b", "cork", "a cork eased out"),
    (r"\bpaper\b|\benvelopes?\b|\btears\b", "paper", "paper handled"),
    (r"\bbottle\b", "bottle", "glass knocking on stone"),
    (r"\bclock\b", "clock", "a clock ticking"),
    (r"\bradio\b", "radio", "a radio murmuring"),
    (r"\bshop bell\b", "doorbell", "a bell over the door"),
    (r"\bdoor\b", "door", "a heavy door"),
    (r"\bswitch(?:es)?\b|\bclick\b", "switch", "a switch thrown"),
    (r"\bdrawer\b", "drawer", "a wooden drawer"),
    (r"\bropes?\b", "rope", "rope creaking on a cleat"),
    (r"\bsurf\b|\bwaves\b", "surf", "a wave breaking"),
    (r"\btins?\b", "tin", "a biscuit tin"),
    (r"\bhum\b|\blamp\b", "lamp", "the lamp warming up"),
    (r"\bunbolts\b", "bolt", "a bolt drawn"),
    (r"\bfranking\b", "franking", "a franking machine, three times"),
]
FOLEY = FoleyRules(rooms=ROOMS, events=EVENTS)

# ---- voices. A new show takes the library's full transition set, so the narrator
# reads none of CUT TO: / FADE TO BLACK. / THE END aloud.
PARSER = TimelineParser()
FALLBACK_SPEAKER = "MAN"
SCRATCH_CAST = {"NARRATOR": 110, "CARD": 150, "MAEVE": 190, "TOBY": 255,
                "OWEN": 92, "IRIS": 205, "RADIO": 128, "MAN": 115}
SAPI_CAST = {"NARRATOR": (DAVID, 0, 0), "CARD": (ZIRA, 0, 0), "MAEVE": (ZIRA, -8, -1),
             "TOBY": (ZIRA, 35, 1), "OWEN": (DAVID, -18, -2), "IRIS": (ZIRA, -16, -2),
             "RADIO": (DAVID, 6, 1), "MAN": (DAVID, 0, 0)}
EDGE_CAST = {"NARRATOR": ("en-GB-RyanNeural", 0, 0), "CARD": ("en-GB-LibbyNeural", 0, 0),
             "MAEVE": ("en-IE-EmilyNeural", 0, -4), "TOBY": ("en-US-AnaNeural", 0, 4),
             "OWEN": ("en-GB-ThomasNeural", -6, -8), "IRIS": ("en-GB-SoniaNeural", -8, -10),
             "RADIO": ("en-GB-RyanNeural", 4, 6), "MAN": ("en-GB-RyanNeural", 0, 0)}
CASTS = {"scratch": SCRATCH_CAST, "sapi": SAPI_CAST, "edge": EDGE_CAST}
# line folders per cast, in priority order: a half-rendered cast falls back to scratch
SOURCES = {"scratch": ["lines_scratch"], "sapi": ["lines_sapi", "lines_scratch"],
           "edge": ["lines_edge", "lines_scratch"]}

# ---- music. rms_db is relative to speech RMS, not a peak level.
MUSIC_SLOTS = {
    "titles": {"track": "low_tide_theme.wav", "start": 0.0, "seconds": 10.0,
               "rms_db": -3.0, "fade_in": 0.3, "fade_out": 2.5},
    "actin": {"track": "low_tide_theme.wav", "start": 29.95, "seconds": 3.0,
              "rms_db": -4.0, "fade_in": 0.0, "fade_out": 1.5},
    "actout": {"track": "low_tide_theme.wav", "start": 59.95, "seconds": 4.5,
               "rms_db": -2.0, "fade_in": 0.0, "fade_out": 2.5},
    "recap": {"track": "harbour_bed.wav", "start": 5.0, "seconds": 30.0,
              "rms_db": -14.0, "fade_in": 1.0, "fade_out": 2.0},
}
SPEECH_RMS = 0.0705           # what the scratch cast is levelled to
SCORE = ScoreRules()

# ---- the draft check
DECLARED = {"MAEVE", "TOBY", "OWEN", "IRIS", "RADIO"}
PROPS = {"the stamps": Prop(r"\bstamps?\b", 0.35, 0.80),
         "the biscuit tins": Prop(r"\btins?\b", 0.50, 0.80)}


def canon(prose, scenes, check):
    """The show's own rules. check(name, good, detail)."""
    low = prose.lower()
    door = low.find("unbolts")
    iris = low.find("iris")
    check("the keeper is unnamed until the door opens", 0 <= door < iris,
          "first 'iris' at %.0f%%, door at %.0f%%" % (100 * iris / len(low), 100 * door / len(low)))
    sister = [m.start() for m in re.finditer(r"\bsister\b", low)]
    check("the sister is revealed once, late", len(sister) == 1 and sister[0] / len(low) > 0.6,
          "%d mentions%s" % (len(sister), ", at %.0f%%" % (100 * sister[0] / len(low))
                             if sister else ""))


def checker(root, source_lines=None):
    root = Path(root)
    return DraftCheck(
        title=TITLE, declared=set(DECLARED), props=dict(PROPS), canon=canon,
        episodes=2, acts=(3, 3), min_speakers=4, recaps=RECAPS,
        foley_keys=FOLEY.keys(), min_distinct_sounds=15, max_room_only=2,
        episodes_dir=root / "episodes", cues_path=root / "cues.json",
        source_lines=source_lines)
