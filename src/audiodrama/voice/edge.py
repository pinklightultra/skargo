"""Edge neural voices: one request per line, so the wav IS the line.

No key, no quota, no video, and a child voice exists (en-US-AnaNeural). Pacing is a
per-part parameter, so the episode slot is a dial rather than a property of a vendor.

The cost: this is the endpoint Edge's own read-aloud uses, not a contracted API. It
can change without notice. Fine for a draft; not something to build a business on.

The endpoint returns mp3, which `wave` cannot read, so `miniaudio` decodes it to mono
PCM in-process -- no ffmpeg. `edge-tts` and `miniaudio` are imported lazily, so the
rest of audiodrama works without them.

A cast is {part: (voice, pitch Hz, rate %)}. Hz because that is what the endpoint
takes; a percentage would be a conversion invented here.

A manifest beside the wavs records the text each one was rendered from. `verify`
proves a derived wav name still carries that text: a wav name is an event index, and
a rewrite above line N moves every name after it.
"""

import asyncio
import json
import wave
from pathlib import Path

CONCURRENCY = 6
RETRIES = 4


def pct(v):
    return "%+d%%" % v


def hz(v):
    return "%+dHz" % v


class EdgeCast:
    def __init__(self, cast, line_dir, sr=22050, fallback="MAN",
                 concurrency=CONCURRENCY, retries=RETRIES, log=print):
        self.cast = cast
        self.dir = Path(line_dir)
        self.manifest = self.dir / "manifest.json"
        self.sr = sr
        self.fallback = fallback
        self.concurrency = concurrency
        self.retries = retries
        self.log = log or (lambda *a: None)

    def voice_for(self, speaker):
        return self.cast.get(speaker, self.cast[self.fallback])

    @staticmethod
    def from_timelines(timelines):
        """(wav, speaker, text, ep) for every utterance, in timeline order."""
        out = []
        for n, tl in timelines.items():
            for ev in tl:
                if "wav" in ev and ev.get("text"):
                    out.append({"wav": ev["wav"], "speaker": ev["voice_as"],
                                "text": ev["text"], "ep": n})
        return out

    def write_wav(self, dest, mp3):
        import miniaudio
        d = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16,
                             nchannels=1, sample_rate=self.sr)
        with wave.open(str(dest), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(self.sr)
            f.writeframes(d.samples.tobytes())

    async def one(self, job, sem, force):
        """Synthesize one line. Retries the network, never a rejection."""
        import edge_tts
        dest = self.dir / job["wav"]
        if dest.exists() and not force:
            return "skip"
        voice, pitch, rate = self.voice_for(job["speaker"])
        async with sem:
            for attempt in range(self.retries):
                try:
                    c = edge_tts.Communicate(job["text"], voice, rate=pct(rate), pitch=hz(pitch))
                    data = b""
                    async for ch in c.stream():
                        if ch["type"] == "audio":
                            data += ch["data"]
                    if not data:
                        raise RuntimeError("empty audio for %s" % job["wav"])
                    self.write_wav(dest, data)
                    return "ok"
                except Exception as e:
                    # a malformed request fails the same way every time
                    if attempt == self.retries - 1 or "unexpected" in str(e).lower():
                        self.log("FAIL %s (%s): %s" % (job["wav"], voice, e))
                        return "fail"
                    await asyncio.sleep(1.5 * (attempt + 1))

    def read_manifest(self):
        if self.manifest.exists():
            return json.loads(self.manifest.read_text(encoding="utf-8"))
        return {}

    def verify(self, jobs):
        man = self.read_manifest()
        have = {p.name for p in self.dir.glob("ep*.wav")}
        drift, missing = [], []
        for j in jobs:
            if j["wav"] not in have:
                missing.append(j["wav"])
            elif man.get(j["wav"], {}).get("text") != j["text"]:
                drift.append(j["wav"])
        self.log("verify: %d in script, %d on disk, %d unrendered, %d DRIFTED"
                 % (len(jobs), len(have), len(missing), len(drift)))
        for w in drift[:10]:
            self.log("  drift %s\n    disk   %r\n    script %r"
                     % (w, man.get(w, {}).get("text"),
                        next(j["text"] for j in jobs if j["wav"] == w)))
        return not drift

    async def _run(self, jobs, force):
        self.dir.mkdir(parents=True, exist_ok=True)
        sem = asyncio.Semaphore(self.concurrency)
        results = await asyncio.gather(*(self.one(j, sem, force) for j in jobs))
        man = self.read_manifest()
        for j, r in zip(jobs, results):
            if r in ("ok", "skip"):
                man[j["wav"]] = {"speaker": j["speaker"], "text": j["text"],
                                 "voice": self.voice_for(j["speaker"])[0]}
        self.manifest.write_text(json.dumps(man, indent=1), encoding="utf-8")
        return results

    def render(self, jobs, force=False):
        return asyncio.run(self._run(jobs, force))

    def durations(self, jobs):
        """Total speech, and refresh lines.json (the whole directory, not this run)."""
        sec = {}
        for p in sorted(self.dir.glob("ep*.wav")):
            with wave.open(str(p)) as w:
                sec[p.name] = round(w.getnframes() / w.getframerate(), 3)
        (self.dir / "lines.json").write_text(json.dumps(sec, indent=0), encoding="utf-8")
        return sum(sec[j["wav"]] for j in jobs if j["wav"] in sec)
