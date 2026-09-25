"""The demo show end to end, offline, on the scratch cast."""

import hashlib

import numpy as np
import pytest

from audiodrama.qa import Report, load_draft
from audiodrama.sound import read_int16
from examples.demo import run
from examples.demo import show as SH


def tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture(scope="session")
def demo(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo")
    assert run.main(["all", "--root", str(root)]) == 0
    return root


def test_every_stage_ran(demo):
    eps = sorted((demo / "audio" / "episodes").glob("*.wav"))
    assert [p.name for p in eps] == ["LOW_TIDE_EP1_scratch.wav", "LOW_TIDE_EP2_scratch.wav"]
    for p in eps:
        assert 3 * 60 < len(read_int16(p)) / 22050 < 6 * 60
    assert sorted(p.stem for p in (demo / "audio" / "music").glob("*.wav")) == [
        "actin", "actout", "recap", "titles"]


def test_the_draft_passes_its_own_check(demo):
    assert run.main(["check", "--root", str(demo)]) == 0


def test_music_is_levelled_against_the_speech(demo):
    for role, spec in SH.MUSIC_SLOTS.items():
        x = read_int16(demo / "audio" / "music" / ("%s.wav" % role)).astype(np.float64)
        want = SH.SPEECH_RMS * 10 ** (spec["rms_db"] / 20)
        assert np.sqrt((x ** 2).mean()) == pytest.approx(want, rel=0.02), role


def test_the_title_block_gets_no_foley(demo):
    head = (demo / "parts" / "10_causeway.fountain").read_text(encoding="utf-8")
    assert "[[foley" not in head.split("====")[0]


def test_stamping_is_idempotent(demo):
    before = tree(demo / "parts")
    run.main(["script", "--root", str(demo)])
    assert tree(demo / "parts") == before


def test_an_em_dash_fails_the_style_check(demo):
    body = load_draft(demo / "LOW_TIDE.fountain").replace("Did you bring the stamps?",
                                                          "Did you bring — the stamps?")
    chk = SH.checker(demo)
    assert chk.run(body, log=None) == 1
    assert any("STYLE" in f for f in chk.report.fails)


def test_a_rerun_is_byte_identical(demo, tmp_path):
    again = tmp_path / "again"
    assert run.main(["all", "--root", str(again)]) == 0
    assert tree(again) == tree(demo)


def test_report_exit_code():
    R = Report(log=None)
    R.ok("A", "fine")
    R.warn("B", "hm")
    assert R.finish() == 0
    R.check("C", False, "no")
    assert R.finish() == 1 and R.fails == ["[FAIL] C: no"]
