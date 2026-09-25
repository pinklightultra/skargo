import json

import numpy as np
import pytest

from audiodrama.mix import DEFAULT_CFG, Mixer, ScoreRules, load_config, music_levels, window
from audiodrama.mix.measure import moving_mean
from audiodrama.sound import write_int16

SR = 22050


def const(seconds, v=0.1):
    return np.full(int(seconds * SR), v, np.float32)


@pytest.fixture
def lines(tmp_path):
    """ep1_0000..0003: one second each; ep1_0009 is thirteen seconds of silence."""
    d = tmp_path / "lines"
    d.mkdir()
    for i in range(4):
        write_int16(d / ("ep1_%04d.wav" % i), const(1.0, 0.05))
    write_int16(d / "ep1_0009.wav", const(13.0, 0.0))
    return d


def say(i, kind="speech", text="x", **kw):
    return dict(kind=kind, speaker="A", text=text, wav="ep1_%04d.wav" % i, **kw)


def secs(x):
    return len(x) / SR


def test_the_clock_runs_on_lines_and_gaps(lines):
    x, *_ = Mixer({}, sources=[lines]).build(1, [say(0), say(1)])
    assert secs(x) == pytest.approx(1.0 + DEFAULT_CFG["gapSpeech"] + 1.0, abs=1e-3)


def test_muting_never_moves_the_cut(lines):
    tl = [{"kind": "foley", "key": "knock"}, say(0), say(1, kind="action")]
    sfx = {"knock": const(0.2)}
    loud = Mixer(sfx, sources=[lines]).build(1, tl)
    cfg = dict(DEFAULT_CFG, muted_keys=["knock"], off={"dial": False})
    quiet = Mixer(sfx, sources=[lines], cfg=cfg).build(1, tl)
    assert len(quiet[0]) == len(loud[0])
    assert (loud[1], loud[3]) == (1, 0) and (quiet[1], quiet[3]) == (0, 2)
    # the muted dialogue is silent, the narration is not
    assert np.max(np.abs(quiet[0][:SR // 2])) == 0.0 and np.max(np.abs(quiet[0][-SR // 2:])) > 0


def test_the_main_titles_theme_is_the_one_slot_that_advances_the_clock(lines):
    tl = [say(0, kind="card", text="Main Titles."), say(1)]
    bare = Mixer({}, sources=[lines]).build(1, tl)[0]
    scored = Mixer({}, {"titles": const(2.0, 0.01)}, sources=[lines]).build(1, tl)[0]
    assert secs(bare) == pytest.approx(1.0 + DEFAULT_CFG["gap"] + 1.0, abs=1e-3)
    assert secs(scored) == pytest.approx(2.0 + DEFAULT_CFG["preScene"] + 1.0, abs=1e-3)


def test_role_variant_first_then_role(lines):
    music = {"actout": const(1.0, 0.01), "actout_one": const(3.0, 0.01)}
    mx = Mixer({}, music, sources=[lines])
    one = mx.build(1, [{"kind": "actout", "text": "END OF ACT ONE"}])[0]
    two = mx.build(1, [{"kind": "actout", "text": "END OF ACT TWO"}])[0]
    assert (secs(one), secs(two)) == (pytest.approx(3.0), pytest.approx(1.0))


def test_act_out_then_end_of_episode_stings_once(lines):
    music = {"actout_three": const(1.0, 0.01), "actout_end": const(2.0, 0.01)}
    x, *_, placed = Mixer({}, music, sources=[lines]).build(
        1, [{"kind": "actout", "text": "END OF ACT THREE"},
            {"kind": "actout", "text": "END OF EPISODE 1"}])
    assert placed == 1
    assert secs(x) == pytest.approx(DEFAULT_CFG["actout"] + 2.0, abs=1e-3)


def genre(i, said):
    return say(i, kind="system", text="System. Genre: %s." % said)


@pytest.mark.parametrize("said,placed", [("Drama", 1), ("Comedy, Load-Bearing", 1),
                                         ("Mystery", 0)])
def test_a_genre_tag_opens_scene_music(lines, said, placed):
    music = {"scene_drama": const(60.0, 0.01), "scene_comedy": const(60.0, 0.01)}
    tl = [genre(0, said), say(9), {"kind": "slug", "speaker": "N", "text": "A."}]
    assert Mixer({}, music, sources=[lines]).build(1, tl)[5] == placed


def test_an_empty_tag_kills_the_scene_score(lines):
    tl = [genre(0, "Drama"), {"kind": "sysfail", "hold": 1.4}, say(9),
          {"kind": "slug", "speaker": "N", "text": "A."}]
    assert Mixer({}, {"scene_drama": const(60.0, 0.01)}, sources=[lines]).build(1, tl)[5] == 0


def test_a_room_tone_is_a_bed_until_the_next_slug(tmp_path):
    d = tmp_path / "quiet"
    d.mkdir()
    for i in range(2):
        write_int16(d / ("ep1_%04d.wav" % i), const(1.0, 0.0))
    tl = [{"kind": "foley", "key": "room-a"}, say(0),
          {"kind": "slug", "speaker": "N", "text": "B."}, say(1)]
    x = Mixer({"room-a": const(0.3, 0.1)}, sources=[d]).build(1, tl)[0]
    assert x[int(0.5 * SR)] == pytest.approx(0.1 * DEFAULT_CFG["bed"], abs=1e-4)
    assert x[int(2.5 * SR)] == 0.0


def test_missing_and_borrowed_lines(lines, tmp_path):
    first = tmp_path / "first"
    first.mkdir()
    write_int16(first / "ep1_0000.wav", const(1.0, 0.05))
    out = Mixer({}, sources=[first, lines]).build(
        1, [say(0), say(1), say(7), {"kind": "foley", "key": "nothing"}])
    assert (out[2], out[4]) == (2, 1)                      # missing, fell back


def test_score_rules():
    R = ScoreRules()
    assert [R.variant_of(t) for t in ("END OF ACT THREE", "Act Two.", "END OF COLD OPEN",
                                      "END OF EPISODE 2", "Main Titles.")] == [
        "three", "two", "cold", "end", None]
    assert R.genre_of("System. Genre: Farce.") == "farce"
    assert R.genre_of("System. Weather: Farce.") is None


def test_music_levels_isolates_each_placement_and_leaves_the_mixer_alone(lines):
    mx = Mixer({}, {"actout": const(1.0, 0.02)}, sources=[lines])
    cfg = dict(mx.cfg)
    tl = [say(0), {"kind": "actout", "text": "END OF ACT ONE"}, say(1)]
    runs, info = music_levels(mx, 1, tl)
    assert len(runs) == 1
    assert runs[0]["at"] == pytest.approx(1.0 + DEFAULT_CFG["gapSpeech"], abs=0.1)
    assert runs[0]["music"] == pytest.approx(0.02, rel=0.1)
    assert mx.cfg == cfg and set(mx.music) == {"actout"} and mx.music["actout"].any()


def test_moving_mean_matches_the_convolution():
    x = np.random.default_rng(0).random(1000)
    for w in (1, 2, 7, 100, 999, 1000, 1500):
        assert np.allclose(moving_mean(x, w), np.convolve(x, np.ones(w) / w, "same")), w


def test_window_is_a_stable_offset_into_a_long_bed():
    bed = np.arange(SR * 60, dtype=np.float32)
    a, b = window(bed, 10, seed=3), window(bed, 10, seed=3)
    assert np.array_equal(a, b) and len(a) == 10 * SR
    assert not np.array_equal(a, window(bed, 10, seed=4))


def test_load_config_keeps_only_what_the_mixer_owns(tmp_path):
    assert load_config(tmp_path / "none.json") == (DEFAULT_CFG, None)
    (tmp_path / "m.json").write_text(json.dumps({"bed": 0.2, "playerTheme": "dark"}))
    cfg, kept = load_config(tmp_path / "m.json")
    assert kept == {"bed": 0.2} and cfg["bed"] == 0.2 and "playerTheme" not in cfg
