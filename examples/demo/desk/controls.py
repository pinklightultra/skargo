"""Every control on the desk.

The page, the programmatic clicker, and the outcome matrix all read this list.
A control that is not in here is not on the page, and a control that is in here
has to return an outcome when it is clicked.
"""

from ..show import MARKS
from ..sounds import RECIPES

# id, label, what the click does
STAGES = (
    ("init", "Init", "Copy the parts into this folder."),
    ("script", "Script", "Stamp markers, cues, and the episode cut."),
    ("check", "Check", "Score the draft. A failure stops the show."),
    ("timeline", "Timeline", "Turn the episodes into the audio clock."),
    ("voices", "Voices", "Render the take selected in the margin."),
    ("sfx", "Foley", "Synthesise every cue in the sheet."),
    ("backlog", "Backlog", "Write the two demo songs."),
    ("music", "Music", "Cut the slots from the backlog."),
    ("mix", "Mix", "Assemble the episodes."),
    ("levels", "Levels", "Measure where each music placement lands."),
    ("mp3", "mp3", "Encode the episodes, when the extra is installed."),
    ("all", "Run the show", "Every stage, in order. Stop on the first failure."),
)

CASTS = ("scratch", "sapi", "edge")
VOICES = ("scratch", "sapi", "edge")

# mixer bus id, caption
BUSES = (
    ("dial", "Dialogue"),
    ("narr", "Narration"),
    ("sys", "System"),
    ("music", "Music"),
    ("sfx", "Foley hits"),
    ("bed", "Rooms"),
)

# key, caption, minimum, maximum, step
FADERS = (
    ("gap", "Gap", 0.0, 2.0, 0.01),
    ("gapSpeech", "Speech gap", 0.0, 2.0, 0.01),
    ("gapSlug", "Slug gap", 0.0, 2.0, 0.01),
    ("preScene", "Before a scene", 0.0, 3.0, 0.05),
    ("actout", "After an act", 0.0, 5.0, 0.05),
    ("pod", "Player pod", 0.0, 30.0, 0.5),
    ("bed", "Room level", 0.0, 1.0, 0.01),
    ("sfx", "Foley level", 0.0, 1.5, 0.01),
    ("music", "Music level", 0.0, 1.5, 0.01),
    ("speech", "Speech level", 0.0, 1.5, 0.01),
    ("master", "Ceiling", 0.05, 1.2, 0.01),
)

EPISODES = tuple(sorted({num for kind, num, *_rest in MARKS.values() if kind == "ep"}))
FOLEY_KEYS = tuple(RECIPES)

STAGE_LABEL = {sid: label for sid, label, _blurb in STAGES}
FADER_RANGE = {key: (lo, hi) for key, _label, lo, hi, _step in FADERS}
FADER_LABEL = {key: label for key, label, *_rest in FADERS}
BUS_LABEL = {bid: label for bid, label in BUSES}


def control_ids():
    """Stable ids, in the order the page paints them."""
    ids = [f"stage:{sid}" for sid, *_ in STAGES]
    ids += [f"cast:{name}" for name in CASTS]
    ids += [f"voices:{name}" for name in VOICES]
    ids.append("force")
    ids += [f"episode:{n}" for n in EPISODES]
    ids.append("defaults")
    ids.append("pod-override")
    ids.append("kbps")
    ids.append("backlog")
    ids.append("reset-slots")
    ids += [f"bus:{bid}" for bid, _label in BUSES]
    ids += [f"fader:{key}" for key, *_ in FADERS]
    ids.append("reset-player")
    ids += [f"mute:{key}" for key in FOLEY_KEYS]
    return tuple(ids)
