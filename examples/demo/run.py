"""The LOW TIDE pipeline on the audiodrama libraries, in a working folder of its own.

    python -m examples.demo.run all                # every stage, scratch voices, offline

    python -m examples.demo.run init               # copy parts/ into --root
    python -m examples.demo.run script             # episode markers, foley cues, the cut
    python -m examples.demo.run check              # draft quality report, exit 1 on failures
    python -m examples.demo.run timeline           # episodes -> audio/timeline.json
    python -m examples.demo.run voices [--cast scratch|sapi|edge]
    python -m examples.demo.run sfx                # synthesise foley, report uncovered cues
    python -m examples.demo.run backlog            # synthesise the song backlog
    python -m examples.demo.run music              # cut music slots from the backlog
    python -m examples.demo.run mix [--voices scratch|sapi|edge] [EP ...]
    python -m examples.demo.run levels [EP]        # where each music placement lands
    python -m examples.demo.run mp3                # needs the mp3 extra

Everything is written under --root (default out/demo). The parts in examples/demo/parts
are only ever read.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from audiodrama import mix as M
from audiodrama import score
from audiodrama.qa import load_draft
from audiodrama.script import assemble, stamp_scene_markers, write_cut
from audiodrama.sound import coverage, cue_keys
from audiodrama.voice import timeline as TL

from . import backlog
from . import show as SH
from . import sounds

REPO = Path(__file__).resolve().parents[2]
DRAFT = "LOW_TIDE.fountain"


def parts_of(root):
    return sorted((root / "parts").glob("*.fountain"))


def cmd_init(a):
    root = Path(a.root)
    (root / "parts").mkdir(parents=True, exist_ok=True)
    for p in sorted(SH.PARTS.glob("*.fountain")):
        shutil.copy2(p, root / "parts" / p.name)
    print("copied %d parts" % len(parts_of(root)))


def cmd_script(a):
    root = Path(a.root)
    files = parts_of(root)
    new, n, missing = stamp_scene_markers([f.read_text(encoding="utf-8") for f in files],
                                          SH.MARKS)
    if missing:
        raise SystemExit("scene numbers not found: %s" % missing)
    for f, t in zip(files, new):
        f.write_text(t, encoding="utf-8")
    print("stamped %d markers across %d scenes" % (len(SH.MARKS), n))
    SH.FOLEY.stamp_files(files)
    (root / DRAFT).write_text(assemble(files), encoding="utf-8")
    write_cut(files, SH.SHOW, root, tool="examples/demo/run.py")


def cmd_check(a):
    src = Path(a.root) / DRAFT
    n_lines = len(src.read_text(encoding="utf-8").split("\n"))
    return SH.checker(a.root, n_lines).run(load_draft(src))


def cmd_timeline(a):
    root = Path(a.root)
    eps = {n: SH.PARSER.parse(f) for n, f in TL.episode_files(root / "episodes").items()}
    timelines, jobs, unknown = TL.assign_wavs(eps, SH.SCRATCH_CAST, SH.FALLBACK_SPEAKER)
    for spk in unknown:
        print("WARNING uncast speaker %r -> %s" % (spk, SH.FALLBACK_SPEAKER))
    print("timeline: " + ", ".join("%s %d" % kv
                                   for kv in sorted(TL.kind_counts(timelines).items())))
    aud = root / "audio"
    aud.mkdir(parents=True, exist_ok=True)
    lines = aud / SH.SOURCES[a.voices][0]
    if lines.is_dir():
        TL.stamp_seconds(timelines, TL.durations(lines))
    (aud / "timeline.json").write_text(
        json.dumps({str(k): v for k, v in timelines.items()}, indent=1), encoding="utf-8")
    (aud / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    print("wrote audio/timeline.json, %d utterances" % len(jobs))


def cmd_voices(a):
    aud = Path(a.root) / "audio"
    jobs = json.loads((aud / "jobs.json").read_text(encoding="utf-8"))
    out = aud / SH.SOURCES[a.cast][0]
    if a.cast == "scratch":
        from audiodrama.voice import scratch
        scratch.render(jobs, out, SH.SCRATCH_CAST, force=a.force)
        return 0
    if a.cast == "sapi":
        from audiodrama.voice import sapi
        return 0 if sapi.render(sapi.render_jobs(jobs, SH.SAPI_CAST), out, aud) else 1
    from audiodrama.voice.edge import EdgeCast
    timelines = {int(k): v for k, v in
                 json.loads((aud / "timeline.json").read_text(encoding="utf-8")).items()}
    ec = EdgeCast(SH.EDGE_CAST, out, fallback=SH.FALLBACK_SPEAKER)
    ejobs = EdgeCast.from_timelines(timelines)
    ec.render(ejobs, force=a.force)
    ec.durations(ejobs)
    return 0 if ec.verify(ejobs) else 1


def cmd_sfx(a):
    root = Path(a.root)
    made = sounds.build(root / "audio" / "sfx")
    missing, extra = coverage(cue_keys(root / "cues.json"), made)
    print("synthesised %d sounds -> audio/sfx/ (%d room tones, %d events)"
          % (len(made), len(sounds.ROOMS), len(sounds.EVENTS)))
    if missing:
        print("MISSING %d cue keys have no recipe: %s" % (len(missing), ", ".join(missing)))
    if extra:
        print("unused recipes: %s" % ", ".join(extra))
    return 1 if missing else 0


def cmd_backlog(a):
    paths = backlog.write(Path(a.root) / "backlog")
    print("wrote %d backlog tracks -> backlog/" % len(paths))


def cmd_music(a):
    root = Path(a.root)
    bl = score.Backlog([a.backlog or root / "backlog"])
    cfg = score.fold_config(SH.MUSIC_SLOTS, root / "audio" / "music.json")
    score.build_slots(cfg, bl, root / "audio" / "music", order=list(SH.MUSIC_SLOTS),
                      speech_rms=SH.SPEECH_RMS)


def mixer_for(root, voices, defaults=False):
    aud = Path(root) / "audio"
    cfg = dict(M.DEFAULT_CFG)
    if not defaults:
        cfg, kept = M.load_config(aud / "mixconfig.json")
        if kept is not None:
            print("mixconfig.json: %d settings from the player" % len(kept))
    return M.Mixer(M.load_dir(aud / "sfx"), M.load_dir(aud / "music"),
                   [aud / d for d in SH.SOURCES[voices]], cfg, SH.SCORE)


def cmd_mix(a):
    aud = Path(a.root) / "audio"
    mx = mixer_for(a.root, a.voices, a.defaults)
    timelines = json.loads((aud / "timeline.json").read_text(encoding="utf-8"))
    out = aud / "episodes"
    out.mkdir(parents=True, exist_ok=True)
    total, bad = 0.0, 0
    for key in sorted(timelines, key=int):
        n = int(key)
        if a.eps and n not in a.eps:
            continue
        report = []
        x, placed, missing, muted, borrowed, mus = mx.build(n, timelines[key], a.pod, report)
        p = out / ("LOW_TIDE_EP%d_%s.wav" % (n, a.voices))
        M.write(p, x)
        secs = len(x) / mx.sr
        total += secs
        bad += missing
        print("  EP%d  %4.1f min  %3d sfx  %d ad pods  %d music  %s"
              % (n, secs / 60, placed, len(report), mus, p.name)
              + ("  MISSING %d" % missing if missing else "")
              + ("  muted %d" % muted if muted else "")
              + ("  %d lines borrowed" % borrowed if borrowed else ""))
    print("wrote %.1f min of audio -> audio/episodes/" % (total / 60))
    return 1 if bad else 0


def cmd_levels(a):
    mx = mixer_for(a.root, a.voices)
    tl = json.loads((Path(a.root) / "audio" / "timeline.json").read_text(encoding="utf-8"))
    for n in a.eps or sorted(map(int, tl)):
        runs, info = M.music_levels(mx, n, tl[str(n)])
        M.print_levels(n, runs, info)


def cmd_mp3(a):
    out = Path(a.root) / "audio" / "episodes"
    M.encode_all(sorted(out.glob("LOW_TIDE_EP*_%s.wav" % a.voices)), a.kbps)


def cmd_all(a):
    for stage in ("init", "script", "check", "timeline", "voices", "timeline", "sfx",
                  "backlog", "music", "mix", "levels"):
        print("\n== %s" % stage)
        rc = globals()["cmd_" + stage](a)
        if rc:
            print("stage %s failed (exit %d)" % (stage, rc))
            return rc
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["all", "init", "script", "check", "timeline", "voices",
                                      "sfx", "backlog", "music", "mix", "levels", "mp3"])
    ap.add_argument("eps", nargs="*", type=int)
    ap.add_argument("--root", default=str(REPO / "out" / "demo"))
    ap.add_argument("--cast", default="scratch", choices=sorted(SH.CASTS),
                    help="voices: which cast renders the lines")
    ap.add_argument("--voices", default="scratch", choices=sorted(SH.SOURCES),
                    help="timeline/mix/levels/mp3: which rendered lines to use")
    ap.add_argument("--force", action="store_true", help="voices: re-render existing lines")
    ap.add_argument("--backlog", default=None, help="music: a folder of songs to cut from")
    ap.add_argument("--pod", type=float, default=None, help="mix: ad pod seconds")
    ap.add_argument("--defaults", action="store_true", help="mix: ignore mixconfig.json")
    ap.add_argument("--kbps", type=int, default=96)
    a = ap.parse_args(argv)
    return globals()["cmd_" + a.stage](a) or 0


if __name__ == "__main__":
    sys.exit(main())
