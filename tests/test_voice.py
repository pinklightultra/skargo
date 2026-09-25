import numpy as np
import pytest

from audiodrama.sound.wavio import read_int16, write_int16
from audiodrama.voice import (LEGACY_TRANSITIONS, TimelineParser, assign_wavs, durations,
                              kind_counts, speakable_annotation, speakable_slug,
                              stamp_seconds, title_caps)
from audiodrama.voice import sapi, scratch
from audiodrama.voice.synthesia import align, parse_srt, scenes_of

EPISODE = """Title: T
====

> **PREVIOUSLY ON T** <

A bottle came in.

SMASH TO:

> **COLD OPEN** <

EXT. CAUSEWAY - 5:58 AM
[[day:1]]
[[foley:room-shore|sea]]

Gulls wheel.

INSERT - THE LETTER

WISH YOU WERE HERE

BACK TO SCENE

TOBY
(quietly)
Who writes a joke?

FADE TO BLACK.

> **END OF COLD OPEN** <

[[ad:1.1]]

> **ACT ONE** <

[ SYSTEM / GENRE: DRAMA ]

[ SYSTEM / ]
"""


def test_timeline_kinds_in_order():
    tl = TimelineParser().parse_text(EPISODE)
    assert [e["kind"] for e in tl] == [
        "card", "recap", "card", "slug", "foley", "action", "action", "screen", "speech",
        "actout", "ad", "card", "system", "sysfail"]
    by = {e["kind"]: e for e in tl}
    assert by["slug"]["text"] == "Exterior. Causeway. 5:58 AM."
    assert by["speech"] == {"kind": "speech", "speaker": "TOBY", "text": "Who writes a joke?"}
    assert by["system"]["text"] == "System. Genre: Drama."
    assert by["sysfail"]["hold"] == 1.4
    assert tl[0]["text"] == "Previously On T."


def test_the_transition_set_decides_what_is_spoken_and_so_the_wav_names():
    new = TimelineParser().parse_text(EPISODE)
    old = TimelineParser(transitions=LEGACY_TRANSITIONS).parse_text(EPISODE)
    spoken = [e["text"] for e in old if e["kind"] == "action"]
    assert "FADE TO BLACK." in spoken and "SMASH TO:" not in spoken
    # one more utterance, so everything after it moves up one index
    t_new, _, _ = assign_wavs({1: new}, {"NARRATOR", "CARD", "SYSTEM", "TOBY"})
    t_old, _, _ = assign_wavs({1: old}, {"NARRATOR", "CARD", "SYSTEM", "TOBY"})
    act = lambda tl: next(e["wav"] for e in tl[1] if e.get("text") == "Act One.")
    assert (act(t_new), act(t_old)) == ("ep1_0011.wav", "ep1_0012.wav")


def test_assign_wavs_names_by_index_and_reports_the_uncast():
    tl = TimelineParser().parse_text(EPISODE)
    timelines, jobs, unknown = assign_wavs({1: tl}, {"NARRATOR", "CARD", "SYSTEM"}, "MAN")
    assert unknown == ["TOBY"]
    assert len(jobs) == 10          # the act-out, foley, ad and empty tag are silent
    speech = next(j for j in jobs if j["text"] == "Who writes a joke?")
    assert speech == {"wav": "ep1_0008.wav", "voice_as": "MAN", "text": "Who writes a joke?"}
    assert kind_counts(timelines)["card"] == 3


def test_durations_and_stamp_seconds(tmp_path):
    write_int16(tmp_path / "ep1_0000.wav", np.zeros(11025))
    (tmp_path / "ep1_0001.wav").write_bytes(b"not a wav")
    dur = durations(tmp_path)
    assert dur == {"ep1_0000.wav": 0.5, "ep1_0001.wav": 0.0}
    tl = {1: [{"wav": "ep1_0000.wav"}, {"wav": "ep1_0009.wav"}, {"kind": "foley"}]}
    stamp_seconds(tl, dur)
    assert [e.get("seconds") for e in tl[1]] == [0.5, 0.0, None]


def test_speakable_text():
    assert speakable_slug("INT./EXT. VAN - NIGHT") == "Interior, exterior. Van. Night."
    assert title_caps("5:58 AM", keep_meridiem=True) == "5:58 AM"
    # in a tag, AM is the verb
    assert speakable_annotation("I AM DOING WELL") == ("System. I Am Doing Well.", 0.0)
    assert speakable_annotation("") == (None, 1.4)
    assert speakable_annotation("GENRE:") == ("System. Genre.", 1.1)


def test_scratch_is_deterministic_per_line_and_timing_true():
    text = "one two three four five six seven eight nine ten eleven twelve thirteen"
    a = scratch.murmur(text, 150, seed=scratch.seed_of("A", text))
    b = scratch.murmur(text, 150, seed=scratch.seed_of("A", text))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, scratch.murmur(text + ".", 150, seed=1))
    assert 4.5 < len(a) / 22050 < 5.5          # 13 words at 2.6 a second
    rms = float(np.sqrt((a.astype(np.float64) ** 2).mean()))
    assert abs(rms - scratch.RMS) < 0.002 or np.max(np.abs(a)) == pytest.approx(0.95)


def test_scratch_render_keeps_existing_lines_unless_forced(tmp_path):
    jobs = [{"wav": "ep1_0000.wav", "voice_as": "IRIS", "text": "Hello."},
            {"wav": "ep1_0001.wav", "voice_as": "NOBODY", "text": "Hm."}]
    assert scratch.render(jobs, tmp_path, {"IRIS": 200}, log=None) == (2, 0)
    first = (tmp_path / "ep1_0001.wav").read_bytes()
    assert scratch.render(jobs, tmp_path, {"IRIS": 200}, log=None) == (0, 2)
    assert scratch.render(jobs, tmp_path, {"IRIS": 200}, force=True, log=None) == (2, 0)
    assert (tmp_path / "ep1_0001.wav").read_bytes() == first
    assert len(read_int16(tmp_path / "ep1_0000.wav")) > 0
    assert 90 <= scratch.pitch_for("NOBODY") <= 240
    assert scratch.pitch_for("NOBODY") == scratch.pitch_for("NOBODY")


def test_sapi_jobs_and_cast_config(tmp_path):
    cast = {"A": ("V1", 0, 1), "B": ("V2", 10, 0)}
    jobs = sapi.render_jobs([{"wav": "w", "voice_as": "A", "text": "t"}], cast)
    assert jobs == [{"wav": "w", "voice": "V1", "pitch": 0, "rate": 1, "text": "t"}]
    assert sapi.apply_castconfig(cast, tmp_path / "absent.json") == {}
    (tmp_path / "cast.json").write_text('{"A": 1200, "B": 2400, "C": 50, "X": 0}')
    applied = sapi.apply_castconfig(cast, tmp_path / "cast.json")
    assert applied == {"A": (0, 100), "B": (10, 200)}      # an octave, then clamped
    assert cast["A"] == ("V1", 100, 1)


SRT = """1
00:00:00,000 --> 00:00:01,500
Who writes

2
00:00:01,500 --> 00:00:02,250
a joke?

3
00:00:02,500 --> 00:00:03,000
Nobody.
"""


def test_synthesia_captions_align_back_to_lines():
    caps = parse_srt(SRT)
    assert caps[1] == (1.5, 2.25, "a joke?")
    events = [{"wav": "ep1_0001.wav", "speaker": "TOBY", "text": "Who writes a joke?"},
              {"wav": "ep1_0002.wav", "speaker": "IRIS", "text": "Nobody."}]
    out = align(events, caps, log=None)
    assert [(o["wav"], o["start"], o["end"]) for o in out] == [
        ("ep1_0001.wav", 0.0, 2.25), ("ep1_0002.wav", 2.5, 3.0)]
    with pytest.raises(ValueError, match="alignment failed"):
        align([dict(events[0], text="Something else entirely.")], caps, log=None)


def test_synthesia_scenes_carry_the_cold_open_card_into_scene_one():
    tl = [{"kind": "card", "text": "Cold Open."}, {"kind": "slug", "text": "A."},
          {"kind": "speech", "text": "x"}, {"kind": "actout", "text": "END OF ACT ONE"},
          {"kind": "slug", "text": "B."}, {"kind": "speech", "text": "y"}]
    assert [[e["text"] for e in sc] for sc in scenes_of(tl)] == [
        ["Cold Open.", "A.", "x"], ["B.", "y"]]
