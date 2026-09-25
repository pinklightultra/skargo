"""Synthesia cast: one video per scene, lines recovered from the captions.

Voice is bound to the avatar in this API, so a cast is {part: avatar id}. One video
per scene, not per line (15 renders for an episode instead of 513). Per-line bounds
come back out of captions.srt, which is per SENTENCE, so a slide is recovered by
concatenating caption blocks until the text equals the scriptText sent. That is
exact and needs no gap heuristic.

Synthesia returns mp4 only (H.264 + AAC). Slicing the per-line WAVs out of it needs
an AAC decoder; the reference show used headless Chromium for that. This module
stops at the manifest of (wav, start, end).

The API key is read from the SYNTHESIA_API_KEY environment variable and nowhere else.

Avatar discovery: /v2/avatars 404s, so a pool has to be probed. Validation reports
only the FIRST bad avatar in a payload, which is a clean oracle -- candidate first,
a known-bad sentinel second; if the error names the sentinel the candidate is real.
Validation fails either way, so nothing is created and no quota is spent.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.synthesia.io/v2/videos"
SETTINGS = {"style": "rectangular", "horizontalAlign": "right", "scale": 0.25}


def avatar(name):
    return "%s_costume1_cameraA" % name


def scenes_of(timeline):
    """An episode timeline -> spoken events grouped by scene.

    Anything before the first slug (the "Cold Open." card) rides at the head of scene
    1: a render of its own would cost a whole video for two words.
    """
    out, cur = [], []
    for ev in timeline:
        if ev["kind"] == "slug" and cur and any(e["kind"] == "slug" for e in cur):
            out.append(cur)
            cur = []
        if ev.get("text") and ev["kind"] != "actout":
            cur.append(ev)
    if cur:
        out.append(cur)
    return out


def parse_srt(txt):
    def secs(t):
        h, m, rest = t.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    caps = []
    for block in txt.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        a, z = lines[1].split(" --> ")
        caps.append((secs(a), secs(z), " ".join(lines[2:]).strip()))
    return caps


def align(events, caps, log=print):
    """Walk the captions, closing a slide the moment its text is complete.

    The text is recorded next to the wav name because a wav name is a POSITION in the
    episode timeline; `verify` and `remap` depend on it.
    """
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    out, i = [], 0
    for ev in events:
        want, got = norm(ev["text"]), ""
        start = end = caps[i][0] if i < len(caps) else None
        while i < len(caps) and norm(got) != want:
            got = (got + " " + caps[i][2]).strip()
            end = caps[i][1]
            i += 1
        if norm(got) != want:
            raise ValueError("caption alignment failed on %r\n  got %r" % (want, got))
        out.append({"wav": ev["wav"], "speaker": ev["speaker"], "text": ev["text"],
                    "start": round(start, 3), "end": round(end, 3),
                    "seconds": round(end - start, 3)})
    if i != len(caps) and log:
        log("  note: %d caption blocks left over" % (len(caps) - i))
    return out


class SynthesiaCast:
    def __init__(self, cast, fallback, out_dir, title="AUDIO DRAMA", settings=SETTINGS,
                 background="off_white", log=print):
        self.cast = cast
        self.fallback = fallback
        self.dir = Path(out_dir)
        self.manifest = self.dir / "manifest.json"
        self.title = title
        self.settings = settings
        self.background = background
        self.log = log or (lambda *a: None)

    # ---- transport
    @staticmethod
    def key():
        k = os.environ.get("SYNTHESIA_API_KEY")
        if not k:
            raise RuntimeError("set SYNTHESIA_API_KEY")
        return k

    def call(self, method, url, body=None, tries=6):
        """Retried through a network drop, never through a 4xx."""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": self.key(),
                                              "Content-Type": "application/json"})
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    self.log("HTTP %d: %s" % (e.code, e.read().decode()[:600]))
                    raise
                last = "HTTP %d" % e.code
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = str(e)
            if attempt == tries - 1:
                self.log("giving up after %d tries: %s" % (tries, last))
                raise
            wait = min(60, 5 * 2 ** attempt)
            self.log("    network: %s -- retrying in %ds" % (last, wait))
            time.sleep(wait)

    # ---- manifest
    def load(self):
        if self.manifest.exists():
            return json.loads(self.manifest.read_text(encoding="utf-8"))
        return {}

    def save(self, m):
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest.write_text(json.dumps(m, indent=1), encoding="utf-8")

    # ---- payload
    def slides(self, events):
        for spk in sorted({e["speaker"] for e in events if e["speaker"] not in self.cast}):
            self.log("  WARNING uncast %r -> %s" % (spk, self.fallback))
        return [{"scriptText": e["text"], "avatar": self.cast.get(e["speaker"], self.fallback),
                 "avatarSettings": self.settings, "background": self.background}
                for e in events]

    def body(self, key, events, test=False):
        return {"test": test, "title": "%s %s" % (self.title, key),
                "description": "audio-drama voices", "visibility": "private",
                "input": self.slides(events)}

    # ---- render
    def render_scene(self, ep, idx, events, force=False, test=False, dry=False):
        key = "ep%d_sc%02d" % (ep, idx)
        prior = self.load().get(key, {})
        if prior.get("status") == "complete" and not force:
            self.log("%s already done (%s), skipping" % (key, prior["duration"]))
            return 0
        # a submitted render outlives its process; resubmitting pays twice
        if prior.get("id") and not force:
            self.log("%s was already submitted (%s), resuming" % (key, prior["id"]))
            return self.finish(key, prior["id"], events)
        body = self.body(key, events, test)
        if dry:
            self.log(json.dumps(body["input"][:2], indent=1))
            self.log("-- dry run, nothing sent")
            return 0
        vid = self.call("POST", API, body)
        man = self.load()
        man[key] = {"id": vid["id"], "status": vid.get("status"), "test": test}
        self.save(man)
        self.log("  submitted %s" % vid["id"])
        return self.finish(key, vid["id"], events)

    def finish(self, key, vid_id, events, polls=400, every=15):
        for i in range(polls):
            v = self.call("GET", "%s/%s" % (API, vid_id))
            st = v.get("status")
            if st == "complete":
                self.dir.mkdir(parents=True, exist_ok=True)
                mp4 = self.dir / ("%s.mp4" % key)
                urllib.request.urlretrieve(v["download"], mp4)
                srt = urllib.request.urlopen(v["captions"]["srt"]).read().decode("utf-8-sig")
                lines = align(events, parse_srt(srt), self.log)
                man = self.load()
                man[key] = {"id": vid_id, "status": "complete", "duration": v.get("duration"),
                            "mp4": mp4.name, "test": man.get(key, {}).get("test", False),
                            "lines": lines}
                self.save(man)
                self.log("  %s  %s  %d lines aligned" % (v.get("duration"), mp4.name, len(lines)))
                return 0
            if st in ("failed", "rejected"):
                self.log("  render %s: %s" % (st, json.dumps(v)[:400]))
                return 1
            time.sleep(every)
        self.log("  still rendering; run again to pick it up")
        return 1

    # ---- integrity
    def verify(self, ep, timeline):
        """Number of manifest lines whose wav name no longer carries their text."""
        now = {e["wav"]: e["text"] for e in timeline if e.get("wav")}
        drift, unstamped, total = [], 0, 0
        for key, sc in sorted(self.load().items()):
            if not key.startswith("ep%d_" % ep) or not sc.get("lines"):
                continue
            for l in sc["lines"]:
                total += 1
                if "text" not in l:
                    unstamped += 1
                elif now.get(l["wav"]) != l["text"]:
                    drift.append((key, l["wav"], l["text"], now.get(l["wav"])))
        self.log("verify EP%d: %d lines, %d drifted, %d unstamped"
                 % (ep, total, len(drift), unstamped))
        return len(drift)

    def remap(self, ep, timeline):
        """Move wav names onto the current timeline by matching text.

        A renumbering is recoverable and a rewrite is not: this refuses if the text
        sequence of any scene changed, and otherwise renames without re-rendering.
        """
        man, moved = self.load(), 0
        for i, evs in enumerate(scenes_of(timeline)):
            key = "ep%d_sc%02d" % (ep, i)
            sc = man.get(key)
            if not sc or not sc.get("lines"):
                continue
            lines = sc["lines"]
            if len(lines) != len(evs) or any(l.get("text") != e["text"]
                                             for l, e in zip(lines, evs)):
                self.log("%s: the script changed, not just the numbering. Re-render." % key)
                return 1
            for l, ev in zip(lines, evs):
                moved += l["wav"] != ev["wav"]
                l["wav"] = ev["wav"]
        self.save(man)
        self.log("remapped %d line names onto the current timeline" % moved)
        return 0
