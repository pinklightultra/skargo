"""An episode file -> the flat, ordered timeline of things that make sound.

Event kinds:

    card     an act card or PREVIOUSLY ON, spoken by the card voice
    actout   END OF ACT n. Silent: the music sting and the ad pod announce it
    ad       an ad pod ([[ad:n.m]])
    foley    a sound cue ([[foley:key|note]])
    slug     a scene heading, spoken by the narrator as English
    system   an annotator tag spoken aloud, with an optional trailing hold
    sysfail  an empty annotator tag: silence, held
    action   an action line, spoken by the narrator
    recap    narration inside the PREVIOUSLY ON block
    screen   signs, documents and banners, spoken by the narrator
    speech   dialogue

Speaker names are never announced. This is a drama, not an audiobook.

Every utterance gets a wav named for its INDEX in the episode timeline
(`ep1_0042.wav`). That makes renders stable across runs, and it also means any
change to what counts as an utterance renumbers every wav after it -- so the
transition set a show rendered against is part of its config, not a default to be
improved silently.
"""

import re
import wave
from pathlib import Path

from ..script.fountain import SLUG_RE, CUE_RE, MARKERS
from .text import title_caps, speakable_slug, speakable_screen, speakable_annotation

CARD_RE = re.compile(r"^>\s*\*\*(.+?)\*\*\s*<$")
BLOCK_RE = re.compile(r"^(INSERT|INTERCUT|MONTAGE|SERIES OF)\b")
SHOT_RE = re.compile(r"^(TITLE|SUPER|CLOSE|WIDER|WIDE|ANGLE ON|POV|AERIAL|REVERSE)\b")

# The narrow set the reference show rendered against. New shows should take the
# default (audiodrama.script.TRANSITIONS), which also silences SMASH CUT TO:,
# FADE TO BLACK., THE END and bare END OF ACT lines -- all of which this set lets the
# narrator read aloud.
LEGACY_TRANSITIONS = frozenset({"CUT TO:", "DISSOLVE TO:", "SMASH TO:", "FADE OUT.",
                                "FADE IN:", "MATCH CUT TO:", "HOLD.", "BACK TO SCENE"})


class TimelineParser:
    def __init__(self, transitions=None, narrator="NARRATOR", card_speaker="CARD",
                 annotator="SYSTEM", recap_label="PREVIOUSLY", actout_label="END OF"):
        if transitions is None:
            from ..script.fountain import TRANSITIONS as transitions
        self.transitions = frozenset(transitions)
        self.narrator = narrator
        self.card_speaker = card_speaker
        self.annotator = annotator
        self.recap_label = recap_label
        self.actout_label = actout_label
        self.sys_re = (re.compile(r"^\[\s*%s\s*(?:/\s*(.*?))?\s*\]$" % re.escape(annotator))
                       if annotator else None)
        self.prefix = annotator.title() if annotator else ""

    def parse(self, path):
        return self.parse_text(Path(path).read_text(encoding="utf-8"))

    def parse_text(self, text):
        lines = text.split("\n")
        try:
            lines = lines[lines.index("====") + 1:]      # skip the title block
        except ValueError:
            pass
        return self.parse_lines(lines)

    def parse_lines(self, lines):
        N = self.narrator
        tl = []
        prev_cue = None
        in_recap = in_insert = False
        for idx, raw in enumerate(lines):
            s = raw.strip()
            if not s:
                prev_cue = None
                continue
            # a run of '=' is a page break; read aloud it is dead air a TTS will fill
            if set(s) == {"="}:
                prev_cue = None
                continue
            m = CARD_RE.match(s)
            if m:
                label = m.group(1)
                in_recap = label.startswith(self.recap_label)
                if label.startswith(self.actout_label):
                    tl.append({"kind": "actout", "text": label})
                else:
                    tl.append({"kind": "card", "speaker": self.card_speaker,
                               "text": title_caps(label).rstrip(".") + "."})
                prev_cue = None
                continue
            m = MARKERS["ad"].match(s)
            if m:
                tl.append({"kind": "ad", "id": m.group(1)})
                continue
            m = MARKERS["foley"].match(s)
            if m:
                tl.append({"kind": "foley", "key": m.group(1), "note": m.group(2)})
                continue
            if MARKERS["day"].match(s):
                continue
            if SLUG_RE.match(s):
                in_recap = False
                tl.append({"kind": "slug", "speaker": N, "text": speakable_slug(s), "raw": s})
                prev_cue = None
                continue
            m = self.sys_re.match(s) if self.sys_re else None
            if m:
                text, pause = speakable_annotation(m.group(1) or "", self.prefix)
                if text is None:
                    tl.append({"kind": "sysfail", "hold": pause, "raw": s})
                else:
                    tl.append({"kind": "system", "speaker": self.annotator,
                               "text": text, "hold": pause})
                prev_cue = None
                continue
            # before the transitions test: BACK TO SCENE is also a transition
            if s == "BACK TO SCENE" or s.startswith(("END INSERT", "END MONTAGE")):
                in_insert = False
                prev_cue = None
                continue
            if s in self.transitions:
                prev_cue = None
                continue
            if BLOCK_RE.match(s):
                in_insert = True
                tl.append({"kind": "action", "speaker": N, "text": speakable_screen(s)})
                prev_cue = None
                continue
            if SHOT_RE.match(s):
                prev_cue = None
                continue                          # a camera angle makes no sound
            if s.startswith("(") and s.endswith(")"):
                continue                          # parentheticals are direction
            if in_insert and s.isupper():
                tl.append({"kind": "screen", "speaker": N, "text": speakable_screen(s)})
                prev_cue = None
                continue
            m = CUE_RE.match(s)
            if m and not s.endswith((".", "?", "!", ",")) and len(s.split()) <= 4:
                nxt = next((lines[k].strip() for k in range(idx + 1, len(lines))
                            if lines[k].strip()), "")
                # a cue is followed by speech; caps followed by caps is a sign
                if nxt and not CUE_RE.match(nxt) and not nxt.isupper():
                    prev_cue = m.group(1).strip()
                    continue
                tl.append({"kind": "screen", "speaker": N, "text": speakable_screen(s)})
                prev_cue = None
                continue
            if prev_cue:
                tl.append({"kind": "speech", "speaker": prev_cue, "text": s})
                continue
            tl.append({"kind": "recap" if in_recap else "action", "speaker": N, "text": s})
        return tl


def episode_files(epdir, want=None):
    """{n: path} for EP*.fountain in epdir, optionally only the numbers in want."""
    out = {}
    for f in sorted(Path(epdir).glob("EP*.fountain")):
        n = int(re.match(r"EP(\d+)", f.name).group(1))
        if not want or n in want:
            out[n] = f
    return out


def assign_wavs(eps, known, fallback="MAN", pattern="ep%d_%04d.wav"):
    """Stamp voice_as and wav on every utterance. Mutates the events.

    eps: {n: timeline}. known: the speakers the cast can voice; anybody else is voiced
    as `fallback` and reported. Returns (timelines, jobs, unknown), each job
    {wav, voice_as, text}; a cast module turns jobs into renders.
    """
    timelines, jobs, unknown = {}, [], set()
    for n, tl in eps.items():
        for i, ev in enumerate(tl):
            if "text" not in ev or "speaker" not in ev:
                continue
            spk = ev["speaker"]
            if spk not in known:
                unknown.add(spk)
                spk = fallback
            ev["voice_as"] = spk
            ev["wav"] = pattern % (n, i)
            jobs.append({"wav": ev["wav"], "voice_as": spk, "text": ev["text"]})
        timelines[n] = tl
    return timelines, jobs, sorted(unknown)


def durations(line_dir):
    d = {}
    for p in Path(line_dir).glob("*.wav"):
        try:
            with wave.open(str(p)) as w:
                d[p.name] = w.getnframes() / w.getframerate()
        except Exception:
            d[p.name] = 0.0
    return d


def stamp_seconds(timelines, dur):
    for tl in timelines.values():
        for ev in tl:
            if "wav" in ev:
                ev["seconds"] = dur.get(ev["wav"], 0.0)
    return timelines


def kind_counts(timelines):
    kinds = {}
    for tl in timelines.values():
        for ev in tl:
            kinds[ev["kind"]] = kinds.get(ev["kind"], 0) + 1
    return kinds
