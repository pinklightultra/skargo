"""Run one desk control and return its outcome.

The page and the programmatic clicker both call `click`. A pipeline failure is an
outcome (tone, summary, log). It is not an uncaught exception and it does not
open a network connection by itself.
"""

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from audiodrama.mix import DEFAULT_CFG, load_config

from .. import run as pipeline
from .controls import (
    BUS_LABEL, CASTS, EPISODES, FADER_LABEL, FADER_RANGE, FOLEY_KEYS,
    STAGE_LABEL, VOICES,
)

_SUMMARY_CAP = 400
_DETAIL_CAP = 16000


def desk_path(root):
    return Path(root) / "desk.json"


def mix_path(root):
    return Path(root) / "audio" / "mixconfig.json"


def load_desk(root):
    desk = {
        "cast": "scratch",
        "voices": "scratch",
        "force": False,
        "defaults": False,
        "eps": list(EPISODES),
        "pod": None,
        "kbps": 96,
        "backlog": "",
    }
    path = desk_path(root)
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        for key in desk:
            if key in saved:
                desk[key] = saved[key]
    eps = []
    for n in desk["eps"] or []:
        n = int(n)
        if n in EPISODES and n not in eps:
            eps.append(n)
    desk["eps"] = eps or list(EPISODES)
    desk["force"] = bool(desk["force"])
    desk["defaults"] = bool(desk["defaults"])
    desk["kbps"] = int(desk["kbps"])
    desk["backlog"] = desk["backlog"] or ""
    if desk["cast"] not in CASTS:
        desk["cast"] = "scratch"
    if desk["voices"] not in VOICES:
        desk["voices"] = "scratch"
    return desk


def save_desk(root, desk):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    desk_path(root).write_text(json.dumps(desk, indent=1), encoding="utf-8")


def load_mix(root):
    cfg, _kept = load_config(mix_path(root))
    cfg["off"] = dict(cfg.get("off") or {})
    cfg["muted_keys"] = list(cfg.get("muted_keys") or [])
    return cfg


def save_mix(root, cfg):
    path = mix_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {key: cfg[key] for key in DEFAULT_CFG if key in cfg}
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")


def public_state(root):
    root = Path(root)
    desk = load_desk(root)
    return {
        "root": str(root),
        "cast": desk["cast"],
        "voices": desk["voices"],
        "force": desk["force"],
        "defaults": desk["defaults"],
        "eps": list(desk["eps"]),
        "pod": desk["pod"],
        "kbps": desk["kbps"],
        "backlog": desk["backlog"],
        "mix": load_mix(root),
        "episodes": list(EPISODES),
    }


def argv_for(root, stage, desk=None):
    """The CLI argv the desk uses for a stage. Same flags as the module entry."""
    desk = load_desk(root) if desk is None else desk
    # Episode numbers are a positional, and argparse only accepts them before options.
    argv = [stage]
    if stage in ("mix", "levels", "all") and desk.get("eps"):
        argv += [str(int(n)) for n in desk["eps"]]
    argv += ["--root", str(root)]
    if stage in ("voices", "all"):
        argv += ["--cast", desk["cast"]]
        if desk["force"]:
            argv.append("--force")
    if stage in ("timeline", "mix", "levels", "mp3", "all"):
        argv += ["--voices", desk["voices"]]
    if stage in ("mix", "all") and desk.get("pod") is not None:
        argv += ["--pod", str(desk["pod"])]
    if stage in ("mix", "all") and desk.get("defaults"):
        argv.append("--defaults")
    if stage in ("music", "all") and desk.get("backlog"):
        argv += ["--backlog", str(desk["backlog"])]
    if stage == "mp3":
        argv += ["--kbps", str(int(desk["kbps"]))]
    return argv


def _snap(root):
    root = Path(root)
    found = {}
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file():
                st = path.stat()
                found[path.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return found


def _diff(before, after):
    wrote = sorted(key for key in after if key not in before)
    changed = sorted(key for key in after if key in before and after[key] != before[key])
    return wrote, changed


def _clip(text, cap):
    text = (text or "").strip()
    if len(text) <= cap:
        return text
    return text[-cap:]


def _pack(ident, title, tone, code, summary, detail, stage=""):
    summary = _clip(summary, _SUMMARY_CAP) or title
    return {
        "id": ident,
        "control": ident.split(":", 1)[0],
        "stage": stage,
        "title": title,
        "ok": tone != "fail",
        "tone": tone,
        "code": int(code),
        "summary": summary,
        "detail": _clip(detail, _DETAIL_CAP),
        "wrote": [],
        "changed": [],
    }


def _note(ident, title, tone, summary, stage=""):
    return _pack(ident, title, tone, 0 if tone != "fail" else 1, summary, summary, stage)


def run_stage(root, stage, desk):
    """(tone, code, summary, detail) for one CLI stage. Never raises."""
    argv = argv_for(root, stage, desk)
    out, err = StringIO(), StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = int(pipeline.main(argv) or 0)
    except SystemExit as exc:
        c = exc.code
        if c in (None, 0):
            code = 0
        elif isinstance(c, int):
            code = c
        else:
            code = 1
            err.write(str(c))
    except Exception as exc:
        code = 1
        err.write("%s: %s" % (type(exc).__name__, exc))
    text = "\n".join(part for part in (out.getvalue(), err.getvalue()) if part.strip())
    lines = [line for line in text.splitlines() if line.strip()]
    summary = lines[-1] if lines else STAGE_LABEL[stage]
    if code == 0 and stage == "mp3" and "\n0 files" in "\n" + text:
        tone = "warn"
    elif code == 0 and stage == "timeline" and ", 0 utterances" in text:
        tone = "warn"
    elif code == 0:
        tone = "ok"
    else:
        tone = "fail"
    return tone, code, summary, text


def _run(root, stage):
    if stage not in STAGE_LABEL:
        return _note("stage:%s" % stage, "Stage", "fail", "Unknown stage.")
    tone, code, summary, detail = run_stage(root, stage, load_desk(root))
    return _pack("stage:%s" % stage, STAGE_LABEL[stage], tone, code, summary, detail, stage)


def _set_cast(root, ident, value, allowed, title, sentence):
    if value not in allowed:
        return _note(ident, title, "fail",
                     "%s must be one of %s." % (title, ", ".join(allowed)))
    desk = load_desk(root)
    key = "cast" if ident.startswith("cast:") else "voices"
    desk[key] = value
    save_desk(root, desk)
    return _note(ident, title, "ok", sentence % value)


def _toggle_flag(root, ident, key, title, on_text, off_text):
    desk = load_desk(root)
    desk[key] = not desk[key]
    save_desk(root, desk)
    return _note(ident, title, "ok", on_text if desk[key] else off_text)


def _toggle_episode(root, n):
    ident = "episode:%s" % n
    try:
        n = int(n)
    except (TypeError, ValueError):
        return _note(ident, "Episode", "fail", "Episode numbers are whole numbers.")
    if n not in EPISODES:
        return _note(ident, "Episode", "fail", "This show has no episode %s." % n)
    desk = load_desk(root)
    eps = list(desk["eps"])
    if n in eps and len(eps) == 1:
        return _note(ident, "EP%d" % n, "warn",
                     "Keep one episode selected. Mix and levels use this list.")
    if n in eps:
        eps.remove(n)
    else:
        eps.append(n)
        eps.sort()
    desk["eps"] = eps
    save_desk(root, desk)
    names = ", ".join("EP%d" % e for e in eps)
    return _note(ident, "EP%d" % n, "ok", "Mix and levels will run %s." % names)


def _set_pod(root, value):
    desk = load_desk(root)
    if value is None or value == "":
        desk["pod"] = None
        save_desk(root, desk)
        return _note("pod-override", "Pod override", "ok",
                     "Pod override cleared. Mix uses the player pod.")
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return _note("pod-override", "Pod override", "fail",
                     "Pod override has to be a number of seconds.")
    if not 0 <= seconds <= 30:
        return _note("pod-override", "Pod override", "fail",
                     "Pod override must be between 0 and 30 seconds.")
    desk["pod"] = seconds
    save_desk(root, desk)
    return _note("pod-override", "Pod override", "ok",
                 "Pod override is %g seconds. It wins over the player pod." % seconds)


def _set_kbps(root, value):
    try:
        kbps = int(value)
    except (TypeError, ValueError):
        return _note("kbps", "Bitrate", "fail", "Bitrate has to be a whole number.")
    if not 32 <= kbps <= 320:
        return _note("kbps", "Bitrate", "fail", "Bitrate must be between 32 and 320.")
    desk = load_desk(root)
    desk["kbps"] = kbps
    save_desk(root, desk)
    return _note("kbps", "Bitrate", "ok", "mp3 bitrate is %d kbps." % kbps)


def _set_backlog(root, value):
    desk = load_desk(root)
    desk["backlog"] = "" if value is None else str(value).strip()
    save_desk(root, desk)
    if desk["backlog"]:
        summary = "Music will cut from %s." % desk["backlog"]
    else:
        summary = "Music will cut from this folder's backlog."
    return _note("backlog", "Backlog folder", "ok", summary)


def _reset_slots(root):
    path = Path(root) / "audio" / "music.json"
    if path.exists():
        path.unlink()
        return _note("reset-slots", "Slot picks", "ok",
                     "Slot picks cleared. The next music pass rewrites them from the show.")
    return _note("reset-slots", "Slot picks", "warn", "No slot picks were saved.")


def _toggle_bus(root, bus):
    ident = "bus:%s" % bus
    if bus not in BUS_LABEL:
        return _note(ident, "Bus", "fail", "Unknown bus.")
    cfg = load_mix(root)
    off = dict(cfg["off"])
    label = BUS_LABEL[bus]
    if off.get(bus) is False:
        off.pop(bus, None)
        summary = "%s is live." % label
    else:
        off[bus] = False
        summary = "%s is muted. The next mix keeps its time and drops its sound." % label
    cfg["off"] = off
    save_mix(root, cfg)
    return _note(ident, label, "ok", summary)


def _set_fader(root, key, value):
    ident = "fader:%s" % key
    if key not in FADER_RANGE:
        return _note(ident, "Level", "fail", "Unknown level.")
    lo, hi = FADER_RANGE[key]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _note(ident, FADER_LABEL[key], "fail", "That level has to be a number.")
    if not lo <= number <= hi:
        return _note(ident, FADER_LABEL[key], "fail",
                     "%s must be between %g and %g." % (FADER_LABEL[key], lo, hi))
    cfg = load_mix(root)
    cfg[key] = number
    save_mix(root, cfg)
    return _note(ident, FADER_LABEL[key], "ok", "%s is %g." % (FADER_LABEL[key], number))


def _toggle_mute(root, key):
    ident = "mute:%s" % key
    if key not in FOLEY_KEYS:
        return _note(ident, "Mute", "fail", "No cue is named %s." % key)
    cfg = load_mix(root)
    muted = list(cfg["muted_keys"])
    if key in muted:
        muted.remove(key)
        summary = "%s will play." % key
    else:
        muted.append(key)
        summary = "%s is muted. The next mix keeps its place and drops the sound." % key
    cfg["muted_keys"] = muted
    save_mix(root, cfg)
    return _note(ident, key, "ok", summary)


def _reset_player(root):
    path = mix_path(root)
    if path.exists():
        path.unlink()
        summary = "Player cleared. Levels, mutes, and buses are back to the built-in mix."
        tone = "ok"
    else:
        summary = "The player was already at the built-in mix."
        tone = "warn"
    return _note("reset-player", "Player", tone, summary)


def dispatch(root, body):
    """Outcome for one request body. Does not attach the file diff."""
    ident = str(body.get("id") or "")
    if ident.startswith("stage:"):
        return _run(root, ident.split(":", 1)[1])
    if ident.startswith("cast:"):
        value = ident.split(":", 1)[1]
        return _set_cast(root, ident, value, CASTS, "Cast",
                         "Cast is %s. The next voices pass uses it.")
    if ident.startswith("voices:"):
        value = ident.split(":", 1)[1]
        return _set_cast(root, ident, value, VOICES, "Voices",
                         "Mix, levels, and mp3 will use the %s lines.")
    if ident == "force":
        return _toggle_flag(
            root, ident, "force", "Force",
            "Force is on. The next voices pass re-renders every line.",
            "Force is off. Existing lines are kept.")
    if ident == "defaults":
        return _toggle_flag(
            root, ident, "defaults", "Player",
            "Mix will ignore the player and use the built-in levels.",
            "Mix will read the player.")
    if ident.startswith("episode:"):
        return _toggle_episode(root, ident.split(":", 1)[1])
    if ident == "pod-override":
        return _set_pod(root, body.get("value", None))
    if ident == "kbps":
        return _set_kbps(root, body.get("value"))
    if ident == "backlog":
        return _set_backlog(root, body.get("value", ""))
    if ident == "reset-slots":
        return _reset_slots(root)
    if ident.startswith("bus:"):
        return _toggle_bus(root, ident.split(":", 1)[1])
    if ident.startswith("fader:"):
        return _set_fader(root, ident.split(":", 1)[1], body.get("value"))
    if ident == "reset-player":
        return _reset_player(root)
    if ident.startswith("mute:"):
        return _toggle_mute(root, ident.split(":", 1)[1])
    return _note(ident or "unknown", "Desk", "fail", "That control is not on the desk.")


def click(root, control_id, value=...):
    """Programmatic clicker. `value=None` is a real payload; omit it to leave value out."""
    body = {"id": control_id}
    if value is not ...:
        body["value"] = value
    return handle_click(root, body)


def handle_click(root, body):
    root = Path(root)
    before = _snap(root)
    outcome = dispatch(root, body)
    wrote, changed = _diff(before, _snap(root))
    outcome["wrote"] = wrote
    outcome["changed"] = changed
    return outcome
