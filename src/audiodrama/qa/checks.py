"""Draft integrity checks: the pathologies that wreck a machine-assisted draft.

Template stamping, verbatim reuse across scenes, uniform scene length, fake slug
lines, a clock that runs backwards, a recap that paraphrases, an episode cut that is
really a page divisor. Plus a hook for the show's own canon.

    from audiodrama.qa import DraftCheck, load_draft
    body = load_draft("MYSHOW.fountain")
    chk = DraftCheck(title="MYSHOW", declared={"ANNA", "BEN", ...}, episodes=4)
    sys.exit(chk.run(body))

Every threshold is a field. The defaults are the reference show's, which is a
six-episode, four-to-six-act family horror-comedy; change what does not fit yours.
"""

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..script.fountain import CUE_RE, SLUG_RE, TRANSITIONS, prose_body
from .report import Report

GENERIC = re.compile(r"^(\W*|.{0,4})$")
TOD = {"DAY", "NIGHT", "DAWN", "DUSK", "MORNING", "AFTERNOON", "EVENING",
       "LATE AFTERNOON", "PRE-DAWN", "MIDNIGHT", "CONTINUOUS", "LATER",
       "MOMENTS LATER", "SAME"}
ANON = {"WOMAN", "A WOMAN", "MAN", "OLD MAN", "TEENAGER", "CROWD",
        "TOWNSPEOPLE", "KIDS", "A KID", "ALL", "RADIO", "P.A."}
# screen-direction lines that any script repeats freely
DIRECTION_BUDGET = {
    "beat": 999, "cut to:": 999, "smash cut to:": 999, "dissolve to:": 999,
    "match cut to:": 999, "back to scene": 999, "continuous": 999, "beat.": 999,
    "silence.": 999, "hold.": 999, "wider": 999, "later": 999, "fade in:": 2,
    "fade out.": 2, "====": 999,
}


def load_draft(path):
    """The script body with the boneyard (everything after the first /*) and the
    title page dropped."""
    raw = Path(path).read_text(encoding="utf-8")
    body = raw.split("/*")[0]
    return re.sub(r"^Title:.*?\n====\n", "", body, flags=re.S)


def norm(l):
    return re.sub(r"[^a-z' ]", "", l.lower()).strip()


def parse(body, transitions=TRANSITIONS, annotator="SYSTEM", lookahead="position"):
    """Scenes with slug, n, line, day, twin, song, era, ep, ep_title, act, foley,
    lines, cues, action, dialogue.

    lookahead="first" reproduces a quirk of the reference checker: the line after a
    possible cue is found from the FIRST occurrence of that text in the scene, so a
    repeated caps line is judged by what follows its first appearance. "position"
    uses the line's own position.
    """
    tag = "[ %s" % annotator
    lines = [l.rstrip() for l in body.split("\n")]
    scenes, cur = [], None
    for i, l in enumerate(lines):
        s = l.strip()
        if SLUG_RE.match(s):
            cur = {"slug": s, "n": len(scenes) + 1, "line": i + 1, "day": None,
                   "twin": None, "song": None, "era": None,
                   "ep": None, "ep_title": None, "act": None, "foley": [],
                   "lines": [], "cues": [], "action": [], "dialogue": []}
            scenes.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^\[\[day:(\d+)\]\]$", s)
        if m:
            cur["day"] = int(m.group(1)); continue
        m = re.match(r"^\[\[twin:([\w-]+)\]\]$", s)
        if m:
            cur["twin"] = m.group(1); continue
        m = re.match(r"^\[\[song:([\w-]+)\]\]$", s)
        if m:
            cur["song"] = m.group(1); continue
        m = re.match(r"^\[\[era:(\d{4})\]\]$", s)
        if m:
            cur["era"] = int(m.group(1)); continue
        m = re.match(r"^\[\[ep:(\d+)\|(.+?)\]\]$", s)
        if m:
            cur["ep"], cur["ep_title"] = int(m.group(1)), m.group(2)
            cur["act"] = 0
            continue
        m = re.match(r"^\[\[act:(\d+)\]\]$", s)
        if m:
            cur["act"] = int(m.group(1)); continue
        m = re.match(r"^\[\[foley:([\w-]+)\|(.+?)\]\]$", s)
        if m:
            cur["foley"].append((m.group(1), m.group(2))); continue
        cur["lines"].append(s if s else "")
    for sc in scenes:
        prev_cue = False
        in_insert = False
        L = sc["lines"]
        for pos, s in enumerate(L):
            if not s:
                prev_cue = False; continue
            # before the TRANSITIONS skip: BACK TO SCENE is also a transition, and
            # testing membership first left in_insert stuck on for the scene
            if s == "BACK TO SCENE" or s.startswith("END INSERT"):
                in_insert = False; prev_cue = False; continue
            if s in transitions or s.startswith(tag) or s.startswith("[["):
                prev_cue = False; continue
            # a block heading opens screen text until BACK TO SCENE; a single shot
            # heading (CLOSE - X) does not
            if re.match(r"^(INSERT|INTERCUT|MONTAGE|END MONTAGE|SERIES OF)\b", s):
                in_insert = not s.startswith(("END", "BACK"))
                prev_cue = False; sc["action"].append(s); continue
            if re.match(r"^(TITLE|SUPER|CLOSE|WIDER|WIDE|ANGLE ON|POV|AERIAL"
                        r"|REVERSE)\b", s):
                prev_cue = False; sc["action"].append(s); continue
            if in_insert:
                sc["action"].append(s); prev_cue = False; continue
            m = CUE_RE.match(s)
            if m and not s.endswith((".", "?", "!", ",")) and len(s.split()) <= 4:
                # a real cue is followed by dialogue; signage by more caps
                start = L.index(s) if lookahead == "first" else pos
                nxt = ""
                for k in range(start + 1, len(L)):
                    if L[k].strip():
                        nxt = L[k].strip(); break
                if nxt and not CUE_RE.match(nxt) and not nxt.isupper():
                    sc["cues"].append(m.group(1).strip()); prev_cue = True; continue
                sc["action"].append(s); prev_cue = False; continue
            if s.startswith("(") and s.endswith(")"):
                continue
            (sc["dialogue"] if prev_cue else sc["action"]).append(s)
    return scenes


def episode_map(scenes):
    """[{ep, title, acts: [[scene, ...], ...]}] from the markers; [] if scene 1 has none."""
    eps, cur_ep, cur_act = [], None, None
    for sc in scenes:
        if sc["ep"] is not None:
            cur_act = []
            cur_ep = {"ep": sc["ep"], "title": sc["ep_title"], "acts": [cur_act]}
            eps.append(cur_ep)
        elif sc["act"] is not None:
            cur_act = []
            cur_ep["acts"].append(cur_act)
        if cur_ep is None:
            return []
        cur_act.append(sc)
    return eps


@dataclass
class Prop:
    """A load-bearing object: planted by `plant_by`, still in use after `pay_after`
    (fractions of the script)."""
    pattern: str
    plant_by: float
    pay_after: float


@dataclass
class DraftCheck:
    title: str = "DRAFT"
    declared: set = field(default_factory=set)       # every legal cue name
    anon: set = field(default_factory=lambda: set(ANON))
    motif_budget: dict = field(default_factory=lambda: dict(DIRECTION_BUDGET))
    default_cap: int = 2               # scenes a non-motif line may appear in
    originality: float = 0.985         # unique share of 5+ word lines
    ngram: int = 7
    ngram_max: int = 2                 # a 7-gram may appear this often
    shape_cv: float = 0.25
    min_speakers: int = 5
    props: dict = field(default_factory=dict)        # name -> Prop
    canon: Optional[Callable] = None   # canon(prose, scenes, check(name, good, detail))
    episodes: int = 6
    acts: tuple = (4, 6)
    slot_spread: float = 1.4
    recaps: Optional[dict] = None      # {ep: [(speaker or None, text)]}
    foley_keys: Optional[set] = None
    room_prefix: str = "room-"
    min_distinct_sounds: int = 30
    max_room_only: int = 8
    episodes_dir: Optional[Path] = None
    cues_path: Optional[Path] = None
    words_per_page: int = 150
    transitions: frozenset = TRANSITIONS
    annotator: str = "SYSTEM"
    annotator_min: int = 20
    lookahead: str = "position"
    source_lines: Optional[int] = None  # total lines of the source file, for SONG

    # --- the scene corpora the repetition tests see

    def twin_shadow(self, scenes):
        seen, shadow = {}, set()
        for sc in scenes:
            if not sc["twin"]:
                continue
            if sc["twin"] in seen:
                shadow.add(sc["n"])
            else:
                seen[sc["twin"]] = sc["n"]
        return shadow

    def song_shadow(self, scenes):
        """A chorus repeats; exempt the song scene once t_song has proved the device."""
        return {sc["n"] for sc in scenes if sc["song"]}

    # --- tests

    def t_twins(self, scenes, R):
        """A declared twin is one scene played twice: take one's dialogue must be a
        prefix of take two's, and the two must LOOK different."""
        groups = defaultdict(list)
        for sc in scenes:
            if sc["twin"]:
                groups[sc["twin"]].append(sc)
        for name, g in groups.items():
            if len(g) != 2:
                R.fail("TWIN", f"{name}: {len(g)} scenes, expected exactly 2"); continue
            a, b = g
            da, db = a["dialogue"], b["dialogue"]
            if db[:len(da)] != da:
                bad = next((i for i in range(min(len(da), len(db))) if da[i] != db[i]),
                           len(da))
                R.fail("TWIN", f"{name}: dialogue drifted at line {bad+1} -- "
                               f"take one \"{da[bad][:44] if bad < len(da) else ''}\" vs "
                               f"take two \"{db[bad][:44] if bad < len(db) else ''}\"")
            else:
                coda = len(db) - len(da)
                R.ok("TWIN", f"{name}: {len(da)} dialogue lines identical, "
                             f"take two adds a {coda}-line coda")
            sa, sb = set(map(norm, a["action"])), set(map(norm, b["action"]))
            overlap = len(sa & sb) / max(len(sa | sb), 1)
            if overlap > 0.25:
                R.fail("TWIN", f"{name}: action lines {overlap:.0%} identical -- "
                               f"the takes must LOOK different")
            else:
                R.ok("TWIN", f"{name}: action overlap {overlap:.0%}, "
                             f"the two takes read differently")

    def t_song(self, scenes, R):
        """A song built on a hole: the chorus recurs, breaks off at the gap (a line
        ending --), and exactly one rendition fills it."""
        songs = [sc for sc in scenes if sc["song"]]
        if not songs:
            return
        if len(songs) > 1:
            R.fail("SONG", f"{len(songs)} song scenes; the film gets exactly one")
            return
        sc = songs[0]
        d = [norm(l) for l in sc["dialogue"]]
        hook = Counter(x for x in d if len(x.split()) >= 5).most_common(1)
        if not hook or hook[0][1] < 2:
            R.fail("SONG", f"{sc['song']}: no chorus line recurs; that is not a song")
            return
        line, n = hook[0]
        tails = [sc["dialogue"][i + 1] for i, x in enumerate(d)
                 if x == line and i + 1 < len(sc["dialogue"])]
        gaps = [t for t in tails if t.rstrip().endswith("--")]
        filled = [t for t in tails if not t.rstrip().endswith("--")]
        if not gaps:
            R.fail("SONG", f"{sc['song']}: chorus recurs {n}x but never breaks off at the gap")
        elif len(filled) != 1:
            R.fail("SONG", f"{sc['song']}: {len(filled)} renditions resolve the gap, "
                           f"expected exactly 1")
        else:
            R.ok("SONG", f"{sc['song']}: chorus x{n}, {len(gaps)} break off at the hole, "
                         f"1 fills it -- \"{filled[0][-24:].strip()}\"")
        if self.source_lines:
            frac = sc["line"] / max(self.source_lines, 1)
            R.ok("SONG", f"{sc['song']}: lands at {frac:.0%} of the script")

    def t_repetition(self, scenes, R):
        """Cross-scene spread is the pathology; a line repeated inside one scene is rhythm."""
        shadow = self.twin_shadow(scenes) | self.song_shadow(scenes)
        spread = defaultdict(set)
        for sc in scenes:
            if sc["n"] in shadow:
                continue
            for l in sc["action"] + sc["dialogue"]:
                spread[norm(l)].add(sc["n"])
        offenders = []
        for k, sn in spread.items():
            if GENERIC.match(k) or len(k.split()) < 2:
                continue
            cap = self.motif_budget.get(k, self.default_cap)
            if len(sn) > cap:
                offenders.append((len(sn), cap, k))
        subs = [norm(l) for sc in scenes if sc["n"] not in shadow
                for l in sc["action"] + sc["dialogue"] if len(l.split()) >= 5]
        ratio = len(set(subs)) / max(len(subs), 1)
        for v, cap, k in sorted(offenders, reverse=True)[:15]:
            R.fail("REPETITION", f"in {v} different scenes (cap {cap}) -- {k[:88]}")
        if ratio < self.originality:
            R.fail("REPETITION", f"substantive-line originality {ratio:.4f} below "
                                 f"{self.originality}")
        else:
            R.ok("REPETITION", f"{len(set(subs))}/{len(subs)} substantive lines unique "
                               f"({ratio:.4f}); {len(offenders)} motifs over budget")

    def t_ngrams(self, scenes, R):
        """Near-duplicate construction the exact-line test misses."""
        shadow = self.twin_shadow(scenes) | self.song_shadow(scenes)
        text = " ".join(l for sc in scenes if sc["n"] not in shadow
                        for l in sc["action"] + sc["dialogue"]).lower()
        toks = re.findall(r"[a-z']+", text)
        k = self.ngram
        g = Counter(tuple(toks[i:i + k]) for i in range(len(toks) - k + 1))
        hot = [(v, " ".join(key)) for key, v in g.items() if v > self.ngram_max]
        if hot:
            for v, s in sorted(hot, reverse=True)[:12]:
                R.fail("NGRAM", f"{k}-gram x{v} -- \"{s}\"")
        else:
            R.ok("NGRAM", f"no {k}-gram repeats {self.ngram_max + 1}+ times across "
                          f"{len(toks)} tokens")

    def t_scene_shape(self, scenes, R):
        wc = [len(re.findall(r"[A-Za-z']+", " ".join(s["action"] + s["dialogue"])))
              for s in scenes]
        if len(wc) < 3:
            return
        m, sd = statistics.mean(wc), statistics.pstdev(wc)
        cv = sd / m if m else 0
        lc = [len(s["action"]) + len(s["dialogue"]) for s in scenes]
        ident = Counter(lc).most_common(1)[0]
        if cv < self.shape_cv:
            R.fail("SHAPE", f"scene length CV {cv:.2f} too uniform -- template smell")
        elif ident[1] > max(3, 0.25 * len(scenes)):
            R.fail("SHAPE", f"{ident[1]} scenes share exactly {ident[0]} lines")
        else:
            R.ok("SHAPE", f"scene words {min(wc)}-{max(wc)}, mean {m:.0f}, CV {cv:.2f}")

    def t_positional(self, scenes, R):
        """Slot N identical across scenes: the template-stamping signature."""
        if len(scenes) < 6:
            return
        bad = 0
        depth = min(len(s["lines"]) for s in scenes)
        for slot in range(min(depth, 40)):
            vals = [s["lines"][slot] for s in scenes if len(s["lines"]) > slot]
            vals = [v for v in vals if v and not GENERIC.match(v)]
            if not vals:
                continue
            top, n = Counter(vals).most_common(1)[0]
            if n >= 4 and n > 0.3 * len(vals):
                R.fail("POSITIONAL", f"slot {slot}: {n}/{len(vals)} identical -- {top[:70]}")
                bad += 1
        if not bad:
            R.ok("POSITIONAL", "no slot shared by 30%+ of scenes")

    def t_slugs(self, scenes, R):
        bad, times = [], Counter()
        for s in scenes:
            m = SLUG_RE.match(s["slug"])
            if not m:
                bad.append(s["slug"]); continue
            parts = [p.strip() for p in m.group(2).split(" - ")]
            if len(parts) < 2:
                bad.append(s["slug"] + "  (no time)"); continue
            if len(parts) > 3:
                bad.append(s["slug"] + "  (too many segments)")
            times[parts[-1]] += 1
            tods = [p for p in parts[1:]
                    if p in TOD or re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)$", p)]
            if len(tods) > 1:
                bad.append(s["slug"] + "  (doubled time-of-day)")
        if bad:
            for b in bad[:12]:
                R.fail("SLUG", b)
        else:
            R.ok("SLUG", f"{len(scenes)} slugs valid, {len(times)} distinct time tokens")

    def t_days(self, scenes, R):
        era = [s for s in scenes if s["era"]]
        if era:
            R.ok("DAY", f"{len(era)} scenes marked outside the present "
                        f"({sorted({s['era'] for s in era})}); exempt from the day counter")
        scenes = [s for s in scenes if not s["era"]]
        days = [(s["n"], s["day"]) for s in scenes]
        missing = [n for n, d in days if d is None]
        seq = [d for _, d in days if d is not None]
        if missing:
            R.fail("DAY", f"{len(missing)} scenes missing [[day:N]] -- first at scene "
                          f"{missing[0]}")
        if seq != sorted(seq):
            drops = [(i, seq[i - 1], seq[i]) for i in range(1, len(seq)) if seq[i] < seq[i - 1]]
            R.fail("DAY", f"day counter goes backwards: {drops[:5]}")
        if not missing and seq == sorted(seq) and seq:
            R.ok("DAY", f"days {min(seq)}..{max(seq)} monotonic across {len(seq)} scenes")

    def t_clock(self, scenes, R):
        """Clock times inside one day must run forward."""
        def minutes(slug):
            m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)$", slug)
            if not m:
                return None
            h, mm, ap = int(m.group(1)), int(m.group(2)), m.group(3)
            if ap == "AM" and h == 12:
                h = 0
            if ap == "PM" and h != 12:
                h += 12
            return h * 60 + mm
        bad, checked = [], 0
        by_day = defaultdict(list)
        for s in scenes:
            if s["era"] or s["day"] is None or s["twin"]:
                continue
            t = minutes(s["slug"])
            if t is not None:
                by_day[s["day"]].append((s["n"], t, s["slug"]))
        for day, seq in sorted(by_day.items()):
            checked += len(seq)
            for i in range(1, len(seq)):
                if seq[i][1] < seq[i - 1][1]:
                    bad.append(f"day {day}: scene {seq[i][0]} \"{seq[i][2]}\" "
                               f"runs backwards from \"{seq[i-1][2]}\"")
        if bad:
            for b in bad[:8]:
                R.fail("CLOCK", b)
        else:
            R.ok("CLOCK", f"{checked} timestamped scenes run forward within all "
                          f"{len(by_day)} days")

    def t_cast(self, scenes, R):
        seen, first = Counter(), {}
        for s in scenes:
            for c in s["cues"]:
                seen[c] += 1
                first.setdefault(c, s["n"])
        if self.declared:
            unknown = [c for c in seen if c not in self.declared]
            if unknown:
                R.fail("CAST", f"undeclared cues: {sorted(unknown)[:10]}")
        solo = [c for c, v in seen.items()
                if v == 1 and c in self.declared and c not in self.anon]
        if len(seen) < self.min_speakers:
            R.fail("CAST", f"only {len(seen)} speaking characters")
        else:
            R.ok("CAST", f"{len(seen)} speakers, {sum(seen.values())} cues; "
                         f"top {seen.most_common(4)}")
        if solo:
            R.warn("CAST", f"single-line speakers: {solo}")

    def t_canon(self, prose, scenes, R):
        """The show's own rules, supplied as canon(prose, scenes, check)."""
        if self.canon is None:
            return
        self.canon(prose, scenes, lambda name, good, detail:
                   R.check("CANON", good, f"{name} -- {detail}"))

    def t_plants(self, prose, R):
        """Every load-bearing object planted before it is used and used after it is
        planted. A prop that appears once is set dressing, not a plot."""
        low = prose.lower()
        L = len(low)
        for name, p in self.props.items():
            hits = [m.start() / L for m in re.finditer(p.pattern, low)]
            if len(hits) < 2:
                R.fail("PLANT", f"{name}: {len(hits)} mentions -- that is set dressing, "
                                f"not a plant")
            elif hits[0] > p.plant_by:
                R.fail("PLANT", f"{name}: first planted at {hits[0]:.0%}, needed by "
                                f"{p.plant_by:.0%}")
            elif hits[-1] < p.pay_after:
                R.fail("PLANT", f"{name}: last used at {hits[-1]:.0%}, needed after "
                                f"{p.pay_after:.0%}")
            else:
                R.ok("PLANT", f"{name}: {len(hits)} mentions, {hits[0]:.0%} -> {hits[-1]:.0%}")

    def t_style(self, prose, R):
        em = prose.count("—")
        if em:
            R.fail("STYLE", f"{em} em dashes; use -- instead")
        else:
            R.ok("STYLE", "no em dashes")
        smart = prose.count("’") + prose.count("“")
        if smart:
            R.warn("STYLE", f"{smart} smart quotes present")

    def scene_pages(self, sc):
        return len(" ".join(sc["action"] + sc["dialogue"]).split()) / self.words_per_page

    def t_episodes(self, scenes, R):
        """The episodic cut is a cut, not a page divisor: every scene in one act of one
        episode, acts numbered 0..n, and episodes inside one broadcast slot."""
        if not scenes or scenes[0]["ep"] is None:
            R.fail("EPISODES", "scene 1 carries no [[ep:]] marker; nothing is assigned")
            return
        eps = episode_map(scenes)
        if len(eps) != self.episodes:
            R.fail("EPISODES", f"{len(eps)} episodes; the cut is designed for "
                               f"{self.episodes}")
            return
        nums = [e["ep"] for e in eps]
        if nums != list(range(1, len(eps) + 1)):
            R.fail("EPISODES", f"episode numbers out of order or gapped: {nums}"); return
        assigned = sum(len(a) for e in eps for a in e["acts"])
        if assigned != len(scenes):
            R.fail("EPISODES", f"{assigned} scenes assigned of {len(scenes)}"); return
        lo, hi = self.acts
        for e in eps:
            if not lo <= len(e["acts"]) <= hi:
                R.fail("EPISODES", f"EP{e['ep']} has {len(e['acts'])} acts; want {lo} to {hi}")
            for act in e["acts"]:
                if not act:
                    R.fail("EPISODES", f"EP{e['ep']} has an empty act")
            declared = [act[0]["act"] for act in e["acts"]]
            if declared != list(range(len(e["acts"]))):
                R.fail("EPISODES", f"EP{e['ep']} act numbers are {declared}")
        mins = [sum(self.scene_pages(s) for a in e["acts"] for s in a) for e in eps]
        spread = max(mins) / min(mins)
        R.ok("EPISODES", "%d episodes, %d acts, %d ad breaks, %d-%d min"
             % (len(eps), sum(len(e["acts"]) for e in eps),
                sum(len(e["acts"]) - 1 for e in eps), round(min(mins)), round(max(mins))))
        for label, cond in (("no episode is orphaned mid-day",
                             all(any(s["day"] for a in e["acts"] for s in a) for e in eps)),
                            ("episodes fit one slot (longest < %gx shortest)"
                             % self.slot_spread, spread < self.slot_spread)):
            R.check("EPISODES", cond, f"{label} -- spread {spread:.2f}x")
        # half of a deliberate repetition reads as a continuity error
        where = {}
        for e in eps:
            for a in e["acts"]:
                for s in a:
                    if s["twin"]:
                        where.setdefault(s["twin"], set()).add(e["ep"])
        for tag, seen in where.items():
            R.check("EPISODES", len(seen) == 1,
                    f"twin '{tag}' stays inside one episode -- {sorted(seen)}")

    def t_recaps(self, scenes, R):
        """Every line quoted in a 'previously on' is a line somebody said, in the
        previous episode, by the speaker it is attributed to."""
        if self.recaps is None:
            R.warn("RECAPS", "no recaps supplied")
            return
        eps = episode_map(scenes)
        if not eps:
            return
        ranges = {e["ep"]: [s for a in e["acts"] for s in a] for e in eps}
        quoted = bad = 0
        for ep_n, items in sorted(self.recaps.items()):
            prev = ranges.get(ep_n - 1)
            if prev is None:
                R.fail("RECAPS", f"EP{ep_n} recaps EP{ep_n - 1}, which does not exist")
                continue
            said = {norm(l) for s in prev for l in s["dialogue"]}
            cues = {c for s in prev for c in s["cues"]}
            for speaker, text in items:
                if speaker is None:
                    continue
                quoted += 1
                if norm(text) not in said:
                    bad += 1
                    R.fail("RECAPS", f"EP{ep_n} quotes a line not in EP{ep_n - 1}: "
                                     f"{speaker}: {text[:52]}")
                elif speaker not in cues:
                    bad += 1
                    R.fail("RECAPS", f"EP{ep_n} attributes to {speaker}, who does not "
                                     f"speak in EP{ep_n - 1}")
        if not bad:
            R.ok("RECAPS", f"{quoted} quoted clips across {len(self.recaps)} recaps, "
                           f"all verbatim and correctly attributed")

    def t_foley(self, scenes, R):
        """One room tone per scene and it comes first, every key declared, no sound
        repeated inside a scene."""
        if self.foley_keys is None:
            R.warn("FOLEY", "no foley keys supplied")
            return
        total = sum(len(sc["foley"]) for sc in scenes)
        if not total:
            R.fail("FOLEY", "no cues stamped"); return
        noroom, lateroom, dupes, unknown = [], [], [], set()
        for sc in scenes:
            keys = [k for k, _ in sc["foley"]]
            rooms = [k for k in keys if k.startswith(self.room_prefix)]
            if not rooms:
                noroom.append(sc["n"])
            elif keys[0] != rooms[0]:
                lateroom.append(sc["n"])
            if len(rooms) > 1:
                dupes.append(f"scene {sc['n']} has {len(rooms)} room tones")
            if len(set(keys)) != len(keys):
                dupes.append(f"scene {sc['n']} repeats a sound")
            unknown |= {k for k in keys if k not in self.foley_keys}
        for label, bad in (("every scene has a room tone", noroom),
                           ("the room tone is the first cue", lateroom)):
            R.check("FOLEY", not bad, f"{label} -- {len(bad)} exceptions"
                                      f"{' at ' + str(bad[:6]) if bad else ''}")
        for d in dupes:
            R.fail("FOLEY", d)
        if unknown:
            R.fail("FOLEY", f"cues with no entry in the foley rules: {sorted(unknown)}")
        distinct = len(Counter(k for sc in scenes for k, _ in sc["foley"]))
        R.check("FOLEY", distinct >= self.min_distinct_sounds,
                f"{total} cues, {distinct} distinct sounds to build")
        thin = [sc["n"] for sc in scenes if len(sc["foley"]) < 2]
        (R.ok if len(thin) <= self.max_room_only else R.warn)(
            "FOLEY", f"{len(thin)} scenes carry room tone only")

    def t_episode_files(self, R):
        """Check the artifact, not just the source: ad breaks land between acts."""
        if self.episodes_dir is None:
            return
        d = Path(self.episodes_dir)
        files = sorted(d.glob("*.fountain")) if d.is_dir() else []
        if not files:
            R.warn("CUT", "no episode files; write the cut first"); return
        ads = badplace = 0
        for f in files:
            lines = [l.strip() for l in f.read_text(encoding="utf-8").split("\n")]
            for i, l in enumerate(lines):
                if not l.startswith("[[ad:"):
                    continue
                ads += 1
                back = [x for x in lines[:i] if x][-1:]
                if not back or not back[0].startswith("> **END OF"):
                    badplace += 1
        R.check("CUT", not badplace,
                f"{len(files)} episode files, {ads} ad breaks, "
                f"{badplace} landing anywhere but an act break")
        if self.cues_path is not None:
            R.check("CUT", Path(self.cues_path).exists(),
                    "cues.json written for the audio pass")

    def t_pages(self, scenes, prose, R):
        w = len(re.findall(r"[A-Za-z']+", prose))
        pages = w / self.words_per_page
        R.ok("LENGTH", f"{w} words, {len(scenes)} scenes, est. {pages:.0f} pages")
        return pages

    def run(self, body, log=print):
        """Every test, in order. Returns an exit code (1 on any failure)."""
        R = Report(log)
        scenes = parse(body, self.transitions, self.annotator, self.lookahead)
        prose = prose_body(body)
        if not scenes:
            if log:
                log("no scenes parsed")
            return 1
        if log:
            log(f"=== {self.title} check :: {len(scenes)} scenes ===\n")
        self.t_twins(scenes, R)
        self.t_song(scenes, R)
        self.t_repetition(scenes, R)
        self.t_ngrams(scenes, R)
        self.t_scene_shape(scenes, R)
        self.t_positional(scenes, R)
        self.t_slugs(scenes, R)
        self.t_days(scenes, R)
        self.t_clock(scenes, R)
        self.t_cast(scenes, R)
        self.t_canon(prose, scenes, R)
        self.t_plants(prose, R)
        self.t_style(prose, R)
        self.t_episodes(scenes, R)
        self.t_recaps(scenes, R)
        self.t_foley(scenes, R)
        self.t_episode_files(R)
        self.t_pages(scenes, prose, R)
        self.report = R
        return R.finish()
