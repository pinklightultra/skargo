"""Cut an assembled feature into broadcast episodes and emit the cue sheet.

Episode and act boundaries are authored, not computed: they are [[ep:]] / [[act:]]
markers in the script, sitting on the strongest act-out in reach, never a page
divisor. Ad breaks are generated from the act markers so the source never carries an
ad slate.

A `Show` carries everything show-specific: title, credit, recaps, loglines. Recaps
are authored too -- a machine splicing the three longest previous lines together
makes a montage nobody can follow. (None, text) is a narration card, (SPEAKER, text)
a clip quoted verbatim from the episode being recapped; audiodrama.qa's recap check
proves the quotes, so a recap cannot drift out of sync with the script.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .fountain import load_parts, parse_scenes

ACT_NAMES = ["COLD OPEN", "ACT ONE", "ACT TWO", "ACT THREE",
             "ACT FOUR", "ACT FIVE", "ACT SIX"]

NUMBER_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
                "Eight", "Nine", "Ten", "Eleven", "Twelve"]

# the markers the cutter owns; every other kind round-trips in the scene body
CUT_MARKERS = ("ep", "act", "foley", "day")


@dataclass
class Show:
    title: str
    credit: str = ""
    draft_date: str = ""
    recaps: dict = field(default_factory=dict)       # ep -> [(speaker|None, text)]
    loglines: dict = field(default_factory=dict)     # ep -> str
    act_names: list = field(default_factory=lambda: list(ACT_NAMES))
    words_per_page: int = 150                        # one page is about one minute
    ad_break_seconds: int = 150                      # one commercial pod


def pagecount(scene, wpp=150):
    """Estimated minutes. Whitespace words over the scene body, as the cue sheet does."""
    return sum(len(l.split()) for l in scene["body"]) / wpp


def mmss(minutes):
    total = int(round(minutes * 60))
    return "%d:%02d" % (total // 60, total % 60)


def scenes_from_parts(files):
    return parse_scenes(load_parts(files), markers=CUT_MARKERS)


def group(scenes):
    """scenes -> [{ep, title, acts: [[scene, ...], ...]}]"""
    eps, cur_ep, cur_act = [], None, None
    for sc in scenes:
        if sc["ep"] is not None:
            cur_act = []
            cur_ep = {"ep": sc["ep"], "title": sc["title"], "acts": [cur_act]}
            eps.append(cur_ep)
        elif sc["act"] is not None:
            cur_act = []
            cur_ep["acts"].append(cur_act)
        if cur_ep is None:
            raise ValueError("scene %d precedes the first [[ep:]] marker" % sc["n"])
        cur_act.append(sc)
    return eps


def episode_filename(ep):
    return "EP%d_%s.fountain" % (
        ep["ep"], re.sub(r"[^A-Za-z0-9]+", "_", ep["title"]).strip("_"))


def render_episode(ep, show):
    """One episode as a broadcast-format Fountain file."""
    n, title, names = ep["ep"], ep["title"], show.act_names
    L = ["Title: %s" % show.title]
    if show.credit:
        L.append("Credit: %s" % show.credit)
    L.append("Episode: %d. %s" % (n, title))
    if show.draft_date:
        L.append("Draft date: %s" % show.draft_date)
    L += ["", "====", ""]

    if n in show.recaps:
        L.append("> **PREVIOUSLY ON %s** <" % show.title.upper())
        L.append("")
        for speaker, text in show.recaps[n]:
            if speaker is not None:
                L.append(speaker)
            L.append(text)
            L.append("")
        L.append("SMASH TO:")
        L.append("")

    for i, act in enumerate(ep["acts"]):
        if i > 0:
            L += ["> **END OF %s** <" % names[i - 1], "", "[[ad:%d.%d]]" % (n, i), ""]
        L += ["> **%s** <" % names[i], ""]
        for sc in act:
            L.append(sc["slug"])
            if sc["day"] is not None:
                L.append("[[day:%d]]" % sc["day"])
            L.append("")
            # sound cues go back where they fired: invisible when rendered, but a
            # sound designer reading the file sees each cue against its line
            at = {}
            for cue in sc["foley"]:
                at.setdefault(cue["at"], []).append(cue)
            for j, line in enumerate(sc["body"]):
                for cue in at.get(j, []):
                    L.append("[[foley:%s|%s]]" % (cue["key"], cue["note"]))
                L.append(line)
            for cue in at.get(len(sc["body"]), []):
                L.append("[[foley:%s|%s]]" % (cue["key"], cue["note"]))
            L.append("")
        if i == 0:
            L += ["> **MAIN TITLES** <", ""]     # titles run off the back of the teaser

    L += ["> **END OF %s** <" % names[len(ep["acts"]) - 1], "",
          "> **END OF EPISODE %d** <" % n, ""]
    return "\n".join(re.sub(r"\n{3,}", "\n\n", "\n".join(L)).split("\n")) + "\n"


def cue_sheet(eps, show):
    """(cues, rows). Every cue carries an estimated timecode for the audio build."""
    wpp, pod = show.words_per_page, show.ad_break_seconds / 60
    names = show.act_names
    cues, rows = [], []
    for ep in eps:
        n = ep["ep"]
        story = sum(pagecount(sc, wpp) for act in ep["acts"] for sc in act)
        breaks = len(ep["acts"]) - 1
        elapsed = 0.0
        for i, act in enumerate(ep["acts"]):
            if i > 0:
                cues.append({"episode": n, "act": names[i - 1], "kind": "ad",
                             "at": mmss(elapsed), "key": "ad-%d.%d" % (n, i),
                             "note": "pod out of %s" % names[i - 1].lower()})
                elapsed += pod
            for sc in act:
                pp = pagecount(sc, wpp)
                nlines = max(len(sc["body"]), 1)
                for cue in sc["foley"]:
                    cues.append({"episode": n, "act": names[i], "kind": "foley",
                                 "at": mmss(elapsed + pp * cue["at"] / nlines),
                                 "key": cue["key"], "note": cue["note"],
                                 "scene": sc["n"], "slug": sc["slug"]})
                elapsed += pp
        days = [sc["day"] for act in ep["acts"] for sc in act if sc["day"]]
        rows.append({"ep": n, "title": ep["title"], "acts": len(ep["acts"]),
                     "breaks": breaks, "story": story, "slot": story + breaks * pod,
                     "foley": sum(len(sc["foley"]) for act in ep["acts"] for sc in act),
                     "day0": min(days) if days else None,
                     "day1": max(days) if days else None})
    return cues, rows


def episodes_md(eps, rows, show, tool="episodes.py"):
    wpp, names = show.words_per_page, show.act_names
    story = sum(r["story"] for r in rows)
    slot = sum(r["slot"] for r in rows)
    count = NUMBER_WORDS[len(eps)] if len(eps) < len(NUMBER_WORDS) else str(len(eps))
    B = ["# %s -- episodic cut" % show.title, "",
         "GENERATED by `%s`. Do not edit. Move the `[[ep:]]` and `[[act:]]`" % tool,
         "markers in `parts/*.fountain` and run it again.", "",
         "%s episodes, %d ad breaks, %s of story in %s of slot."
         % (count, sum(r["breaks"] for r in rows), mmss(story), mmss(slot)), "",
         "| ep | title | days | acts | ads | story | slot | foley |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        d0, d1 = r["day0"], r["day1"]
        days = "" if d0 is None else str(d0) if d0 == d1 else "%d-%d" % (d0, d1)
        B.append("| %d | %s | %s | %d | %d | %s | %s | %d |"
                 % (r["ep"], r["title"], days, r["acts"], r["breaks"],
                    mmss(r["story"]), mmss(r["slot"]), r["foley"]))
    B += ["", "## Episodes", ""]
    for ep in eps:
        B += ["### %d. %s" % (ep["ep"], ep["title"]), "",
              show.loglines.get(ep["ep"], ""), ""]
        for i, act in enumerate(ep["acts"]):
            B.append("- **%s** -- %s, out on `%s`"
                     % (names[i], mmss(sum(pagecount(s, wpp) for s in act)), act[-1]["slug"]))
        B.append("")
    return "\n".join(B) + "\n"


def cues_md(eps, cues, show, tool="episodes.py"):
    kinds = Counter(c["kind"] for c in cues)
    keys = Counter(c["key"] for c in cues if c["kind"] == "foley")
    C = ["# %s -- cue sheet" % show.title, "",
         "GENERATED by `%s` from `[[foley:]]` and the act markers." % tool,
         "Machine-readable twin: `cues.json`.", "",
         "%d cues: %d foley, %d ad. %d distinct foley keys."
         % (len(cues), kinds["foley"], kinds["ad"], len(keys)), "",
         "## Foley inventory", "",
         "Build each of these once, then the cue sheet places every instance.", "",
         "| key | uses | first note |", "|---|---|---|"]
    firstnote = {}
    for c in cues:
        if c["kind"] == "foley":
            firstnote.setdefault(c["key"], c["note"])
    for k, v in keys.most_common():
        C.append("| `%s` | %d | %s |" % (k, v, firstnote[k]))
    for ep in eps:
        n = ep["ep"]
        C += ["", "## Episode %d -- %s" % (n, ep["title"]), "",
              "| at | kind | cue | note |", "|---|---|---|---|"]
        for c in cues:
            if c["episode"] == n:
                mark = "**AD**" if c["kind"] == "ad" else "foley"
                C.append("| %s | %s | `%s` | %s |" % (c["at"], mark, c["key"], c["note"]))
    return "\n".join(C) + "\n"


def write_cut(parts, show, outdir, episodes_dir="episodes", tool="episodes.py", log=print):
    """Cut parts into episodes/, cues.json, EPISODES.md and CUES.md under outdir."""
    outdir = Path(outdir)
    epdir = outdir / episodes_dir
    epdir.mkdir(parents=True, exist_ok=True)
    for f in epdir.glob("*.fountain"):
        f.unlink()
    eps = group(scenes_from_parts(parts))
    for ep in eps:
        (epdir / episode_filename(ep)).write_text(render_episode(ep, show), encoding="utf-8")
    cues, rows = cue_sheet(eps, show)
    (outdir / "cues.json").write_text(json.dumps(cues, indent=2), encoding="utf-8")
    (outdir / "EPISODES.md").write_text(episodes_md(eps, rows, show, tool), encoding="utf-8")
    (outdir / "CUES.md").write_text(cues_md(eps, cues, show, tool), encoding="utf-8")
    if log:
        log("wrote %d episodes -> %s/" % (len(eps), episodes_dir))
        for r in rows:
            log("  EP%d %-24s %d acts  %d ads  story %s  slot %s  %3d foley"
                % (r["ep"], r["title"], r["acts"], r["breaks"], mmss(r["story"]),
                   mmss(r["slot"]), r["foley"]))
        log("  %-27s %s story, %s slot, %d cues"
            % ("TOTAL", mmss(sum(r["story"] for r in rows)),
               mmss(sum(r["slot"] for r in rows)), len(cues)))
    return eps, cues, rows
