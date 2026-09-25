import json

import numpy as np
import pytest

from audiodrama.score import Backlog, build_slots, cut, fold_config, profile
from audiodrama.score.analyze import sting_onset
from audiodrama.sound import read_int16, write_int16

SPEC = {"track": "t.wav", "start": 1.0, "seconds": 2.0, "rms_db": -6.0,
        "fade_in": 0.2, "fade_out": 0.5}


def tone(seconds, rate, f=440.0, amp=0.5):
    return (amp * np.sin(2 * np.pi * f * np.arange(int(seconds * rate)) / rate)).astype(np.float32)


def rms(x):
    return float(np.sqrt((np.asarray(x, np.float64) ** 2).mean()))


def test_a_cut_is_levelled_against_speech_not_peak():
    out = cut(SPEC, tone(5, 44100), 44100, speech_rms=0.0705, log=None)
    assert len(out) == 2 * 22050
    assert rms(out) == pytest.approx(0.0705 * 10 ** (-6 / 20), rel=1e-4)
    assert out[0] == 0.0                                   # faded in


def test_a_hot_transient_is_capped_and_reported():
    x = np.zeros(44100 * 4, np.float32)
    x[44100 * 2] = 1.0
    said = []
    out = cut(dict(SPEC, rms_db=0.0, fade_in=0.0, fade_out=0.0), x, 44100, log=said.append)
    assert np.max(np.abs(out)) == pytest.approx(0.85)
    assert "hot transient" in said[0]


def test_a_cut_past_the_end_is_an_error():
    with pytest.raises(ValueError, match="past the end"):
        cut(dict(SPEC, start=9.0), tone(5, 22050), 22050, log=None)


def test_fold_config_merges_per_role(tmp_path):
    defaults = {"titles": {"track": "a.wav", "start": 0.0, "rms_db": -3.0},
                "actin": {"track": "a.wav", "start": 30.0, "rms_db": -4.0}}
    path = tmp_path / "music.json"
    assert fold_config(defaults, path, log=None) == defaults
    assert json.loads(path.read_text()) == defaults         # written for editing
    path.write_text(json.dumps({"titles": {"start": 5.0}, "recap": {"track": "b.wav"}}))
    cfg = fold_config(defaults, path, log=None)
    assert cfg["titles"] == {"track": "a.wav", "start": 5.0, "rms_db": -3.0}
    assert cfg["actin"] == defaults["actin"] and cfg["recap"] == {"track": "b.wav"}


def test_backlog_finds_across_roots_and_dedupes_on_the_pcm(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    write_int16(a / "song.wav", tone(1, 22050))
    write_int16(b / "song.wav", tone(1, 22050, f=220))
    write_int16(b / "song (1).wav", tone(1, 22050))           # an export's duplicate
    (b / "notes.txt").write_text("not audio")
    bl = Backlog([a, b])
    assert bl.find("song.wav") == a / "song.wav"               # earlier roots win
    assert sorted(p.name for p, *_ in bl.tracks()) == ["song.wav", "song.wav"]
    with pytest.raises(FileNotFoundError):
        bl.find("missing.wav")


def test_profile_reports_a_48k_track_instead_of_failing(tmp_path):
    write_int16(tmp_path / "a.wav", tone(3, 44100), 44100)
    write_int16(tmp_path / "b.wav", tone(3, 48000), 48000)   # a common export default
    rows = {r["track"]: r for r in profile(Backlog([tmp_path]))}
    assert rows["a.wav"]["seconds"] == pytest.approx(3.0)
    assert "48000 Hz" in rows["b.wav"]["error"]


def test_build_slots_removes_slots_no_longer_configured(tmp_path):
    src, out = tmp_path / "src", tmp_path / "music"
    src.mkdir(), out.mkdir()
    write_int16(src / "t.wav", tone(5, 22050))
    write_int16(out / "actout_one.wav", tone(1, 22050))      # left over from a prior pick
    built = build_slots({"titles": SPEC}, Backlog([src]), out, log=None)
    assert list(built) == ["titles"]
    assert sorted(p.name for p in out.iterdir()) == ["titles.wav"]
    assert rms(read_int16(out / "titles.wav")) == pytest.approx(0.0705 / 2, rel=0.01)


def test_sting_onset_finds_the_hit():
    sr = 22050
    x = tone(10, sr, amp=0.02)
    x[int(6 * sr):int(7 * sr)] += tone(1, sr, f=110, amp=0.5)
    (rise, onset, start), *_ = sting_onset(x, sr)
    # a frame is timed at its window's start, so the loudest rise lands within one
    # 0.1 s window after the hit
    assert rise > 0.2 and 6.0 <= onset <= 6.1
    assert start == pytest.approx(onset - 0.06)
