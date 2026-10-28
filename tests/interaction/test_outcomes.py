"""Programmatic clicker: every desk control, and the outcomes that matter."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from audiodrama.sound import read_int16, write_int16
from examples.demo import run as pipeline
from examples.demo import show as SH
from examples.demo.desk.controls import control_ids
from examples.demo.desk.perform import argv_for, click, load_desk, public_state
from examples.demo.desk.view import render_page

REPO = Path(__file__).resolve().parents[2]
LAME = REPO / "tests" / "fixtures" / "lameenc"
EP1 = Path("audio/episodes/LOW_TIDE_EP1_scratch.wav")


def _value_for(ident):
    if ident.startswith("fader:"):
        return 0.2
    if ident == "kbps":
        return 96
    if ident == "pod-override":
        return 4
    if ident == "backlog":
        return ""
    return ...


def _duration(path):
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


def _rms(path):
    samples = read_int16(path).astype(np.float64)
    if not len(samples):
        return 0.0
    return float(np.sqrt((samples ** 2).mean()))


def _part_hashes(root):
    return {path.name: hashlib.sha1(path.read_bytes()).hexdigest()
            for path in sorted((root / "parts").glob("*.fountain"))}


def _cli(argv):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(("src", "."))
    return subprocess.run(
        [sys.executable, "-m", "examples.demo.run", *argv],
        cwd=REPO, env=env, capture_output=True, text=True, check=False)


@pytest.fixture
def show(finished, tmp_path):
    dest = tmp_path / "show"
    shutil.copytree(finished, dest)
    return dest


def test_the_page_lists_every_control(tmp_path):
    html = render_page(public_state(tmp_path))
    for ident in control_ids():
        assert 'data-id="%s"' % ident in html
    assert "Low Tide" in html
    buttons = sum(1 for ident in control_ids()
                  if not ident.startswith(("fader:", "pod-", "kbps", "backlog")))
    assert html.count("<button") == buttons


def test_the_matrix_names_every_control():
    text = (REPO / "docs" / "control-outcome-matrix.md").read_text(encoding="utf-8")
    missing = [ident for ident in control_ids() if "`%s`" % ident not in text]
    assert not missing


def test_every_non_stage_control_returns_an_outcome(tmp_path):
    root = tmp_path / "desk"
    root.mkdir()
    for ident in control_ids():
        if ident.startswith("stage:"):
            continue
        value = _value_for(ident)
        out = click(root, ident) if value is ... else click(root, ident, value=value)
        assert out["id"] == ident
        assert out["tone"] in ("ok", "warn", "fail")
        assert out["summary"].strip()


def test_rejected_values_do_not_write_the_player(tmp_path):
    root = tmp_path / "desk"
    root.mkdir()
    assert click(root, "fader:master", value=9)["tone"] == "fail"
    assert click(root, "pod-override", value=40)["tone"] == "fail"
    assert click(root, "kbps", value=8)["tone"] == "fail"
    assert click(root, "cast:robot")["tone"] == "fail"
    assert click(root, "stage:nope")["tone"] == "fail"
    assert click(root, "not-a-control")["tone"] == "fail"
    assert not (root / "audio" / "mixconfig.json").exists()
    assert not (root / "desk.json").exists()


def test_empty_folder_outcomes(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    script = click(root, "stage:script")
    assert script["tone"] == "fail" and "scene numbers" in script["summary"]
    check = click(root, "stage:check")
    assert check["tone"] == "fail" and "FileNotFoundError" in check["summary"]
    voices = click(root, "stage:voices")
    assert voices["tone"] == "fail" and "FileNotFoundError" in voices["summary"]
    music = click(root, "stage:music")
    assert music["tone"] == "fail" and "FileNotFoundError" in music["summary"]
    mix = click(root, "stage:mix")
    assert mix["tone"] == "fail" and "FileNotFoundError" in mix["summary"]
    levels = click(root, "stage:levels")
    assert levels["tone"] == "fail" and "FileNotFoundError" in levels["summary"]
    mp3 = click(root, "stage:mp3")
    assert mp3["tone"] == "warn" and "0 files" in mp3["summary"]
    sfx = click(root, "stage:sfx")
    assert sfx["tone"] == "fail" and "FileNotFoundError" in sfx["summary"]
    assert (root / "audio" / "sfx" / "gulls.wav").exists()
    timeline = click(root, "stage:timeline")
    assert timeline["tone"] == "warn" and ", 0 utterances" in timeline["summary"]
    again = click(root, "stage:voices")
    assert again["tone"] == "ok" and "0 lines rendered" in again["detail"]
    empty_mix = click(root, "stage:mix")
    assert empty_mix["tone"] == "ok" and "0.0 min" in empty_mix["summary"]
    # The take still names EP1 and EP2, and the empty clock has neither.
    missing_ep = click(root, "stage:levels")
    assert missing_ep["tone"] == "fail" and "KeyError" in missing_ep["summary"]
    init = click(root, "stage:init")
    assert init["tone"] == "ok" and "copied 2 parts" in init["summary"]
    assert (root / "parts" / "10_causeway.fountain").exists()


def test_a_48k_backlog_is_refused(tmp_path):
    songs = tmp_path / "songs"
    songs.mkdir()
    write_int16(songs / "low_tide_theme.wav", np.zeros(48000, np.float32), 48000)
    root = tmp_path / "show"
    root.mkdir()
    assert click(root, "backlog", value=str(songs))["tone"] == "ok"
    out = click(root, "stage:music")
    assert out["tone"] == "fail"
    assert "48000" in out["detail"] or "not an integer multiple" in out["detail"]


def test_an_em_dash_fails_the_check(tmp_path):
    root = tmp_path / "show"
    root.mkdir()
    assert click(root, "stage:init")["tone"] == "ok"
    assert click(root, "stage:script")["tone"] == "ok"
    draft = root / "LOW_TIDE.fountain"
    draft.write_text(draft.read_text(encoding="utf-8").replace(
        "Did you bring the stamps?", "Did you bring — the stamps?"), encoding="utf-8")
    out = click(root, "stage:check")
    assert out["tone"] == "fail"
    assert "STYLE" in out["detail"]


def test_timeline_warns_when_a_speaker_is_uncast(tmp_path, monkeypatch):
    root = tmp_path / "show"
    root.mkdir()
    click(root, "stage:init")
    click(root, "stage:script")
    monkeypatch.setattr(SH, "SCRATCH_CAST", {"NARRATOR": 110, "CARD": 150})
    out = click(root, "stage:timeline")
    assert out["tone"] == "ok"
    assert "WARNING" in out["detail"] and "MAEVE" in out["detail"]


def test_all_stops_when_the_check_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "cmd_check", lambda _args: 1)
    root = tmp_path / "show"
    out = click(root, "stage:all")
    assert out["tone"] == "fail"
    assert "check" in out["detail"]
    assert (root / "parts").is_dir()
    assert not (root / "audio" / "sfx").exists()


def test_all_builds_the_show(finished):
    assert "[[ep:" in (finished / "parts" / "10_causeway.fountain").read_text(encoding="utf-8")
    assert "[[foley" not in (finished / "parts" / "10_causeway.fountain").read_text(
        encoding="utf-8").split("====")[0]
    assert (finished / "LOW_TIDE.fountain").is_file()
    assert list((finished / "episodes").glob("EP*.fountain"))
    assert (finished / "cues.json").is_file()
    assert (finished / "EPISODES.md").is_file() and (finished / "CUES.md").is_file()
    assert len(list((finished / "audio" / "lines_scratch").glob("*.wav"))) > 10
    timeline = json.loads((finished / "audio" / "timeline.json").read_text(encoding="utf-8"))
    spoken = next(event for event in timeline["1"] if event.get("wav"))
    assert spoken["seconds"] > 0
    for name in ("titles", "actin", "actout", "recap"):
        assert (finished / "audio" / "music" / ("%s.wav" % name)).is_file()
    episodes = sorted(path.name for path in (finished / "audio" / "episodes").glob("*.wav"))
    assert episodes == ["LOW_TIDE_EP1_scratch.wav", "LOW_TIDE_EP2_scratch.wav"]
    assert not list((finished / "audio" / "episodes").glob("*.mp3"))


def test_argv_carries_the_take(tmp_path):
    root = tmp_path / "show"
    click(root, "cast:edge")
    click(root, "voices:sapi")
    click(root, "force")
    click(root, "defaults")
    click(root, "pod-override", value=2.5)
    click(root, "kbps", value=128)
    click(root, "backlog", value=str(tmp_path / "songs"))
    click(root, "episode:1")
    desk = load_desk(root)
    assert argv_for(root, "voices", desk) == [
        "voices", "--root", str(root), "--cast", "edge", "--force"]
    mix = argv_for(root, "mix", desk)
    assert mix[:3] == ["mix", "2", "--root"]
    assert "--defaults" in mix and "--pod" in mix
    assert "--kbps" in argv_for(root, "mp3", desk)
    assert "128" in argv_for(root, "mp3", desk)
    assert "--backlog" in argv_for(root, "all", desk)


def test_finished_show_controls(show):
    parts = _part_hashes(show)
    script = click(show, "stage:script")
    assert script["tone"] == "ok"
    assert _part_hashes(show) == parts
    # Init copies the source parts back over the stamped ones. That is a new copy,
    # not a claim that the stamped text is what lives in examples/demo/parts.
    assert "copied 2 parts" in click(show, "stage:init")["summary"]
    assert click(show, "stage:script")["tone"] == "ok"

    check = click(show, "stage:check")
    assert check["tone"] == "ok" and "0 failures" in check["detail"]

    kept = click(show, "stage:voices")
    assert kept["tone"] == "ok" and "0 lines rendered" in kept["detail"]
    sample = next((show / "audio" / "lines_scratch").glob("*.wav"))
    before = sample.read_bytes()
    assert click(show, "force")["summary"].startswith("Force is on")
    rendered = click(show, "stage:voices")
    assert "rendered" in rendered["detail"] and "0 kept" in rendered["detail"]
    assert sample.read_bytes() == before
    assert click(show, "force")["summary"].startswith("Force is off")

    click(show, "voices:edge")
    click(show, "stage:timeline")
    timeline = json.loads((show / "audio" / "timeline.json").read_text(encoding="utf-8"))
    assert "seconds" not in next(event for event in timeline["1"] if event.get("wav"))
    click(show, "voices:scratch")
    click(show, "stage:timeline")
    timeline = json.loads((show / "audio" / "timeline.json").read_text(encoding="utf-8"))
    assert next(event for event in timeline["1"] if event.get("wav"))["seconds"] > 0

    click(show, "voices:edge")
    borrowed = click(show, "stage:mix")
    assert borrowed["tone"] == "ok" and "borrowed" in borrowed["detail"]
    click(show, "voices:scratch")

    assert "EP2" in click(show, "episode:1")["summary"]
    levels = click(show, "stage:levels")
    assert "EP2" in levels["detail"] and "EP1" not in levels["detail"]
    mixed = click(show, "stage:mix")
    assert "EP2" in mixed["detail"] and "EP1" not in mixed["detail"]
    warned = click(show, "episode:2")
    assert warned["tone"] == "warn"
    assert load_desk(show)["eps"] == [2]
    assert click(show, "episode:1")["tone"] == "ok"
    assert load_desk(show)["eps"] == [1, 2]

    click(show, "pod-override", value=0)
    click(show, "stage:mix")
    short = _duration(show / EP1)
    click(show, "pod-override", value=8)
    click(show, "stage:mix")
    assert _duration(show / EP1) > short + 10
    assert click(show, "pod-override", value=None)["tone"] == "ok"

    assert click(show, "stage:sfx")["tone"] == "ok"
    assert "using music.json" in click(show, "stage:music")["detail"]
    assert "backlog" in click(show, "stage:backlog")["detail"]

    assert click(show, "mute:gulls")["summary"].startswith("gulls is muted")
    muted = click(show, "stage:mix")
    assert "muted" in muted["detail"]
    assert click(show, "mute:gulls")["summary"].startswith("gulls will play")

    for bus in ("dial", "narr", "sys", "music", "sfx", "bed"):
        assert click(show, "bus:%s" % bus)["tone"] == "ok"
    assert click(show, "fader:speech", value=0)["tone"] == "ok"
    silent = click(show, "stage:mix")
    assert "from the player" in silent["detail"]
    assert _rms(show / EP1) < 1e-4
    assert click(show, "defaults")["summary"].startswith("Mix will ignore")
    audible = click(show, "stage:mix")
    assert "from the player" not in audible["detail"]
    assert _rms(show / EP1) > 0.01

    assert click(show, "reset-player")["tone"] == "ok"
    assert not (show / "audio" / "mixconfig.json").exists()
    assert click(show, "reset-slots")["tone"] == "ok"
    assert not (show / "audio" / "music.json").exists()

    cues = json.loads((show / "cues.json").read_text(encoding="utf-8"))
    cues.append({"kind": "foley", "key": "not-a-sound", "note": "no recipe"})
    (show / "cues.json").write_text(json.dumps(cues), encoding="utf-8")
    missing = click(show, "stage:sfx")
    assert missing["tone"] == "fail" and "not-a-sound" in missing["detail"]

    assert click(show, "stage:music")["tone"] == "ok"
    music = json.loads((show / "audio" / "music.json").read_text(encoding="utf-8"))
    music["titles"]["start"] = 100000
    (show / "audio" / "music.json").write_text(json.dumps(music), encoding="utf-8")
    past = click(show, "stage:music")
    assert past["tone"] == "fail" and "past the end" in (past["summary"] + past["detail"])


def test_lines_missing_still_writes_the_episode(show):
    shutil.rmtree(show / "audio" / "lines_scratch")
    out = click(show, "stage:mix")
    assert out["tone"] == "fail" and "MISSING" in out["detail"]
    assert (show / EP1).is_file()


def test_sapi_and_edge_branches(show, monkeypatch):
    from audiodrama.voice import sapi
    from audiodrama.voice.edge import EdgeCast

    click(show, "cast:sapi")
    monkeypatch.setattr(sapi, "render", lambda *args, **kwargs: False)
    assert click(show, "stage:voices")["tone"] == "fail"
    monkeypatch.setattr(sapi, "render", lambda *args, **kwargs: True)
    assert click(show, "stage:voices")["tone"] == "ok"

    click(show, "cast:edge")
    monkeypatch.setattr(EdgeCast, "render", lambda self, jobs, force=False: ["ok"] * len(jobs))
    monkeypatch.setattr(EdgeCast, "durations", lambda self, jobs: 0)
    monkeypatch.setattr(EdgeCast, "verify", lambda self, jobs: False)
    assert click(show, "stage:voices")["tone"] == "fail"
    monkeypatch.setattr(EdgeCast, "verify", lambda self, jobs: True)
    forced = {}

    def _render(self, jobs, force=False):
        forced["force"] = force
        return ["ok"] * len(jobs)

    monkeypatch.setattr(EdgeCast, "render", _render)
    click(show, "force")
    assert click(show, "stage:voices")["tone"] == "ok"
    assert forced["force"] is True


def test_edge_fails_closed_without_the_extra(show):
    if shutil.which("edge-tts"):
        pytest.skip("edge-tts is installed")
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("edge-tts is installed")
    click(show, "cast:edge")
    out = click(show, "stage:voices")
    assert out["tone"] == "fail"
    assert "edge_tts" in out["detail"]


def test_sapi_fails_closed_without_powershell(show):
    if shutil.which("powershell") or shutil.which("powershell.exe"):
        pytest.skip("powershell is installed; SAPI is covered by the patched branch")
    click(show, "cast:sapi")
    out = click(show, "stage:voices")
    assert out["tone"] == "fail"
    assert "FileNotFoundError" in out["detail"] or "powershell" in out["detail"].lower()


def test_mp3_uses_the_fixture_encoder(show, monkeypatch):
    sys.path.insert(0, str(LAME))
    sys.modules.pop("lameenc", None)
    try:
        click(show, "kbps", value=128)
        out = click(show, "stage:mp3")
        assert out["tone"] == "ok", out["detail"]
        encoded = show / "audio" / "episodes" / "LOW_TIDE_EP1_scratch.mp3"
        assert encoded.read_bytes().startswith(b"LAME" + (128).to_bytes(2, "little"))
    finally:
        sys.path.remove(str(LAME))
        sys.modules.pop("lameenc", None)


def test_cli_process(tmp_path):
    bare = _cli([])
    assert bare.returncode == 2 and "usage" in bare.stderr.lower()
    help_text = _cli(["--help"])
    assert help_text.returncode == 0
    for stage in ("init", "script", "check", "timeline", "voices", "sfx", "backlog",
                  "music", "mix", "levels", "mp3", "all"):
        assert stage in help_text.stdout
    assert _cli(["voices", "--cast", "robot"]).returncode == 2
    root = tmp_path / "cli"
    init = _cli(["init", "--root", str(root)])
    assert init.returncode == 0 and "copied 2 parts" in init.stdout
    script = _cli(["script", "--root", str(tmp_path / "bare")])
    assert script.returncode == 1 and "scene numbers" in (script.stderr + script.stdout)
