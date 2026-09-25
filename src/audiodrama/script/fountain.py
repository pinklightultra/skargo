"""Fountain parsing, with the [[marker]] extensions the pipeline runs on.

The markers are production metadata written into the script as Fountain notes, so a
rendered script never shows them:

    [[ep:N|Title]]        this scene opens episode N (and its cold open)
    [[act:N]]             this scene opens act N; an ad break precedes it
    [[foley:key|note]]    a sound cue, fired at this point in the scene
    [[day:N]]             story day, for the continuity checks
    [[twin:name]]         one of two deliberate re-renders of the same scene
    [[song:name]]         the scene holds the musical number
    [[era:YYYY]]          the scene is outside the present, exempt from the day counter
    [[ad:N.M]]            an ad pod (written by the episode cutter, never by hand)

Two rules everything downstream depends on:

  * Markers never count as words. A foley note reading "a loaf onto a hard counter"
    would otherwise register as a plant of the loaves, and three hundred cues add
    twenty pages to the estimate. Use `prose_body` / `script_words`, never a raw split.
  * BACK TO SCENE is both a transition and the end of an insert. The insert reset has
    to be tested BEFORE transition membership, or the reset is unreachable and every
    line after an insert is misread as screen text. That ordering bug was live in the
    reference show for most of a draft.
"""

import re
from pathlib import Path

WORDS_PER_PAGE = 150            # one page is about one minute of screen time

SLUG_RE = re.compile(r"^(INT\.|EXT\.|INT\./EXT\.|EXT\./INT\.)\s+(.+)$")
CUE_RE = re.compile(r"^([A-Z][A-Z0-9 .'\-]{1,24})(\s*\((?:O\.S\.|V\.O\.|CONT'D|CONTD|PRE-LAP)\))?$")
BLOCK_RE = re.compile(r"^(INSERT|INTERCUT|MONTAGE|END MONTAGE|SERIES OF)\b")
SHOT_RE = re.compile(r"^(TITLE|SUPER|CLOSE|WIDER|WIDE|ANGLE ON|POV|AERIAL|REVERSE)\b")

MARKERS = {
    "ep": re.compile(r"^\[\[ep:(\d+)\|(.+?)\]\]$"),
    "act": re.compile(r"^\[\[act:(\d+)\]\]$"),
    "foley": re.compile(r"^\[\[foley:([\w-]+)\|(.+?)\]\]$"),
    "day": re.compile(r"^\[\[day:(\d+)\]\]$"),
    "twin": re.compile(r"^\[\[twin:([\w-]+)\]\]$"),
    "song": re.compile(r"^\[\[song:([\w-]+)\]\]$"),
    "era": re.compile(r"^\[\[era:(\d{4})\]\]$"),
    "ad": re.compile(r"^\[\[ad:([\d.]+)\]\]$"),
}

# The full set. A show whose timeline was rendered against a narrower set should pass
# that set explicitly rather than accept this one: a line that stops being spoken
# renumbers every wav after it (see audiodrama.voice.timeline).
TRANSITIONS = frozenset({
    "CUT TO:", "SMASH CUT TO:", "SMASH TO:", "DISSOLVE TO:", "MATCH CUT TO:",
    "FADE IN:", "FADE OUT.", "FADE TO BLACK.", "BACK TO SCENE", "WIDER", "HOLD.",
    "END OF ACT ONE", "END OF ACT TWO", "END OF ACT THREE", "END OF ACT TWO-A",
    "END OF ACT TWO-B", "END OF ACT TWO-C", "THE END", "TAG", "MAIN TITLES",
})


def _strip_title(raw):
    return re.sub(r"^Title:.*?\n====\n", "", raw, flags=re.S)


def assemble(files):
    """Concatenate part files verbatim into one script, the way a build step does."""
    return "\n\n".join(Path(p).read_text(encoding="utf-8").strip() for p in files) + "\n"


def load_parts(files):
    """Concatenate parts in the given order, dropping each title block and boneyard."""
    chunks = []
    for f in files:
        raw = Path(f).read_text(encoding="utf-8")
        raw = raw.split("/*")[0]
        chunks.append(_strip_title(raw).strip("\n"))
    return "\n\n".join(chunks)


def load_script(text):
    """One assembled script -> its body: boneyard and title block removed."""
    return _strip_title(text.split("/*")[0])


def parse_scenes(body, markers=("ep", "act", "foley", "day", "twin", "song", "era")):
    """Split a body into scenes and pull the named markers out of each.

    A marker kind not in `markers` stays in the scene body as an ordinary line, which
    is what a consumer that round-trips the script (the episode cutter) wants for the
    kinds it does not own.

    Each scene: slug, n (1-based), line (1-based line in body), the marker fields,
    foley [{key, note, at}] where `at` is the body index the cue fired before, body
    (lines right-stripped, blanks kept) and lines (the same, fully stripped).
    """
    want = {k: MARKERS[k] for k in markers}
    scenes, cur = [], None
    for i, raw in enumerate(body.split("\n")):
        s = raw.rstrip()
        t = s.strip()
        if SLUG_RE.match(t):
            cur = {"slug": t, "n": len(scenes) + 1, "line": i + 1, "day": None,
                   "twin": None, "song": None, "era": None, "ep": None, "title": None,
                   "ep_title": None, "act": None, "foley": [], "body": []}
            scenes.append(cur)
            continue
        if cur is None:
            continue
        hit = False
        for kind, rx in want.items():
            m = rx.match(t)
            if not m:
                continue
            hit = True
            if kind == "ep":
                cur["ep"] = int(m.group(1))
                cur["title"] = cur["ep_title"] = m.group(2)
                cur["act"] = 0
            elif kind == "foley":
                cur["foley"].append({"key": m.group(1), "note": m.group(2),
                                     "at": len(cur["body"])})
            elif kind in ("act", "day", "era"):
                cur[kind] = int(m.group(1))
            else:
                cur[kind] = m.group(1)
            break
        if not hit:
            cur["body"].append(s)
    for sc in scenes:
        sc["lines"] = [l.strip() for l in sc["body"]]
    return scenes


def next_nonblank(lines, i):
    for k in range(i + 1, len(lines)):
        if lines[k].strip():
            return lines[k].strip()
    return ""


def is_cue(s, nxt):
    """A speaker cue is short caps followed by speech. Caps followed by caps is a sign."""
    m = CUE_RE.match(s)
    if not m or s.endswith((".", "?", "!", ",")) or len(s.split()) > 4:
        return None
    if nxt and not CUE_RE.match(nxt) and not nxt.isupper():
        return m.group(1).strip()
    return ""


def classify(lines, transitions=TRANSITIONS, annotator="SYSTEM"):
    """Tag each line: blank, slug, other, action, cue, paren, dialogue.

    `other` is anything that makes no page content: transitions, [[markers]], and an
    annotator's bracketed tags (`[ SYSTEM / ... ]`). Screen text inside an INSERT /
    MONTAGE block is action until BACK TO SCENE or END INSERT closes it. A single shot
    heading (CLOSE - X) is one line of action and does NOT open a block: treating it as
    one swallowed every line after it.
    """
    tag = "[ %s" % annotator if annotator else None
    kinds = [None] * len(lines)
    prev_cue = in_insert = False
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            kinds[i] = "blank"; prev_cue = False; continue
        if SLUG_RE.match(s):
            kinds[i] = "slug"; prev_cue = in_insert = False; continue
        # before the transitions test, or the in_insert reset is unreachable
        if s == "BACK TO SCENE" or s.startswith("END INSERT"):
            kinds[i] = "other"; in_insert = prev_cue = False; continue
        if s in transitions or (tag and s.startswith(tag)) or s.startswith("[["):
            kinds[i] = "other"; prev_cue = False; continue
        if BLOCK_RE.match(s):
            in_insert = not s.startswith(("END", "BACK"))
            kinds[i] = "action"; prev_cue = False; continue
        if SHOT_RE.match(s):
            kinds[i] = "action"; prev_cue = False; continue
        if in_insert:
            kinds[i] = "action"; prev_cue = False; continue
        cue = is_cue(s, next_nonblank(lines, i))
        if cue is not None:
            if cue:
                kinds[i] = "cue"; prev_cue = True
            else:
                kinds[i] = "action"; prev_cue = False
            continue
        if s.startswith("(") and s.endswith(")"):
            kinds[i] = "paren"; continue
        kinds[i] = "dialogue" if prev_cue else "action"
    return kinds


def split_scene(sc, transitions=TRANSITIONS, annotator="SYSTEM"):
    """Fill sc['cues'], sc['action'], sc['dialogue'] from sc['lines']. Returns sc."""
    kinds = classify(sc["lines"], transitions, annotator)
    sc["cues"], sc["action"], sc["dialogue"] = [], [], []
    for s, k in zip(sc["lines"], kinds):
        if k == "cue":
            sc["cues"].append(CUE_RE.match(s).group(1).strip())
        elif k in ("action", "dialogue"):
            sc[k].append(s)
    return sc


def prose_body(body):
    """The body with [[...]] marker lines removed. Every regex test reads this."""
    return "\n".join(l for l in body.split("\n") if not l.strip().startswith("[["))


def script_words(text):
    """Words that end up on a page: runs of letters, markers excluded.

    Splitting on whitespace instead counts the times and years in slug lines, and one
    script does not get to have two lengths depending on which tool measured it.
    """
    return len(re.findall(r"[A-Za-z']+", prose_body(text)))


def norm(line):
    """A line reduced for repetition tests: lowercase letters, apostrophes, spaces."""
    return re.sub(r"[^a-z' ]", "", line.lower()).strip()
