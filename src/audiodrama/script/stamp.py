"""Write [[ep:]] / [[act:]] and [[foley:]] markers into part files.

Both stampers are idempotent: they strip their own marker kind first, so re-running
after an edit re-places everything from the current text.

Scene numbers run across all the parts in the order given, so an episode table keyed
by scene number is auditable in one screen:

    MARKS = {1: ("ep", 1, "Pilot"), 4: ("act", 1, "the kitchen"), ...}

Foley goes on ACTION lines only -- a character saying "whistle" is not a whistle --
plus one room tone per scene, keyed off the slug and placed after the slug and any
marker lines, in front of the first line with content. Nothing before the first slug
is stamped: a title block reading "a radio mystery" is not a radio.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .fountain import SLUG_RE, classify

_EPACT_RE = re.compile(r"^\[\[(?:ep|act):")
_FOLEY_RE = re.compile(r"^\[\[foley:")


def strip_markers(text, kinds):
    """Drop every [[kind:...]] line for the given kinds."""
    rx = re.compile(r"^\[\[(?:%s):" % "|".join(map(re.escape, kinds)))
    return "\n".join(l for l in text.split("\n") if not rx.match(l.strip()))


def stamp_scene_markers(texts, marks):
    """texts: part texts in order. marks: scene number -> ("ep", n, title) | ("act", n, note).

    Returns (new_texts, scene_count, missing) where missing lists scene numbers in
    `marks` that the script does not reach. A caller should refuse to write if any are.
    """
    n, out_texts = 0, []
    for text in texts:
        out = []
        for line in text.split("\n"):
            if _EPACT_RE.match(line.strip()):
                continue
            out.append(line)
            if SLUG_RE.match(line.strip()):
                n += 1
                if n in marks:
                    kind, num, note = marks[n]
                    out.append("[[ep:%d|%s]]" % (num, note) if kind == "ep"
                               else "[[act:%d]]" % num)
        out_texts.append("\n".join(out))
    missing = sorted(set(marks) - set(range(1, n + 1)))
    return out_texts, n, missing


@dataclass
class FoleyRules:
    """rooms: [(slug regex, key, note)], first match wins, so narrow before broad.
    events: [(line regex, key, note)], matched in order, case-insensitive.

    Room patterns are case-sensitive on purpose: slugs are caps, and `INT\\.` vs
    `EXT\\.` in a pattern is how one location gets an inside and an outside tone.
    """
    rooms: list
    events: list
    max_per_line: int = 2
    transitions: frozenset = None      # None -> audiodrama.script.fountain.TRANSITIONS
    annotator: str = "SYSTEM"
    _rooms: list = field(default=None, init=False, repr=False)
    _events: list = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._rooms = [(re.compile(p), k, n) for p, k, n in self.rooms]
        self._events = [(re.compile(p, re.I), k, n) for p, k, n in self.events]

    def room_for(self, slug):
        for rx, key, note in self._rooms:
            if rx.search(slug):
                return key, note
        return None

    def cues_for(self, line):
        out = []
        for rx, key, note in self._events:
            if rx.search(line):
                out.append((key, note))
                if len(out) == self.max_per_line:
                    break
        return out

    def keys(self):
        return {k for _, k, _ in self.rooms} | {k for _, k, _ in self.events}

    def stamp(self, text):
        """One part text -> (new text, cues written, rooms matched, unroomed slugs)."""
        kw = {"annotator": self.annotator}
        if self.transitions is not None:
            kw["transitions"] = self.transitions
        src = [l for l in text.split("\n") if not _FOLEY_RE.match(l.strip())]
        kinds = classify(src, **kw)
        out, seen, pending = [], set(), None
        in_scene = False                  # a title block is not a scene: no cues in it
        total = rooms = 0
        unroomed = []
        for i, line in enumerate(src):
            if kinds[i] == "slug":
                out.append(line)
                seen, in_scene = set(), True
                pending = self.room_for(line.strip())
                if pending:
                    rooms += 1
                else:
                    unroomed.append(line.strip())
                continue
            if pending and kinds[i] not in ("other", "blank"):
                out.append("[[foley:%s|%s]]" % pending)
                total += 1
                pending = None
            if kinds[i] == "action" and in_scene:
                for key, note in self.cues_for(line):
                    if key in seen:
                        continue                  # one instance per sound per scene
                    seen.add(key)
                    out.append("[[foley:%s|%s]]" % (key, note))
                    total += 1
            out.append(line)
        return "\n".join(out), total, rooms, unroomed

    def stamp_files(self, files, log=print):
        total = rooms = 0
        unroomed = []
        for f in files:
            f = Path(f)
            new, t, r, u = self.stamp(f.read_text(encoding="utf-8"))
            f.write_text(new, encoding="utf-8")
            total, rooms = total + t, rooms + r
            unroomed += u
        if log:
            log("stamped %d foley cues (%d room tones) across %d parts"
                % (total, rooms, len(files)))
            if unroomed:
                log("NO ROOM TONE for %d slugs:" % len(unroomed))
                for s in unroomed:
                    log("    " + s)
        return total, rooms, unroomed
