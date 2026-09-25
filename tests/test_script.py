import pytest

from audiodrama.script import (FoleyRules, Show, classify, cue_sheet, group, parse_scenes,
                               render_episode, script_words, stamp_scene_markers)


def kinds_of(text):
    lines = text.split("\n")
    return [(l, k) for l, k in zip(lines, classify(lines)) if k != "blank"]


def test_back_to_scene_closes_an_insert():
    # BACK TO SCENE is also a transition. Tested the other way round, the insert never
    # closes and every line after it reads as screen text.
    got = kinds_of("INT. OFFICE - NIGHT\n\nINSERT - THE LETTER\n\nDEAR SIR\n\n"
                   "BACK TO SCENE\n\nMAEVE\nWho sent it?\n\nShe puts it down.")
    assert got == [("INT. OFFICE - NIGHT", "slug"), ("INSERT - THE LETTER", "action"),
                   ("DEAR SIR", "action"), ("BACK TO SCENE", "other"), ("MAEVE", "cue"),
                   ("Who sent it?", "dialogue"), ("She puts it down.", "action")]


def test_a_shot_heading_is_one_line_not_a_block():
    assert kinds_of("CLOSE ON THE BOTTLE\n\nTOBY\nLook.") == [
        ("CLOSE ON THE BOTTLE", "action"), ("TOBY", "cue"), ("Look.", "dialogue")]


def test_caps_followed_by_caps_is_a_sign_not_a_cue():
    assert kinds_of("CLOSED\nOPEN AT NINE\n\nIRIS\nHello.") == [
        ("CLOSED", "action"), ("OPEN AT NINE", "action"), ("IRIS", "cue"),
        ("Hello.", "dialogue")]


def test_markers_are_not_words():
    bare = "EXT. SHORE - DAY\nShe waits."
    cued = "EXT. SHORE - DAY\n[[foley:bread|a loaf onto a hard counter]]\nShe waits."
    assert script_words(cued) == script_words(bare) == 5


def test_parse_scenes_pulls_markers_and_keeps_cue_positions():
    body = ("EXT. A - DAY\n[[ep:1|Pilot]]\n[[day:3]]\n\n[[foley:gulls|gulls]]\nGulls.\n\n"
            "INT. B - NIGHT\n[[act:1]]\nDark.\n")
    a, b = parse_scenes(body)
    assert (a["n"], a["ep"], a["title"], a["act"], a["day"]) == (1, 1, "Pilot", 0, 3)
    assert a["foley"] == [{"key": "gulls", "note": "gulls", "at": 1}]
    assert a["body"][a["foley"][0]["at"]] == "Gulls."
    assert (b["n"], b["ep"], b["act"]) == (2, None, 1)


def test_a_marker_kind_not_asked_for_stays_in_the_body():
    (sc,) = parse_scenes("EXT. A - DAY\n[[ep:1|Pilot]]\nX.", markers=("day",))
    assert sc["ep"] is None and "[[ep:1|Pilot]]" in sc["body"]


PARTS = ["Title: T\n====\n\nEXT. ONE - DAY\nA.\n\nINT. TWO - DAY\nB.\n",
         "EXT. THREE - NIGHT\nC.\n"]


def test_scene_markers_count_across_parts_and_are_idempotent():
    marks = {1: ("ep", 1, "Pilot"), 3: ("act", 1, "night")}
    once, n, missing = stamp_scene_markers(PARTS, marks)
    assert (n, missing) == (3, [])
    assert "EXT. ONE - DAY\n[[ep:1|Pilot]]\nA." in once[0]
    assert once[1].startswith("EXT. THREE - NIGHT\n[[act:1]]\nC.")
    assert stamp_scene_markers(once, marks)[0] == once


def test_scene_markers_report_scenes_the_script_never_reaches():
    assert stamp_scene_markers(PARTS, {1: ("ep", 1, "x"), 9: ("act", 1, "y")})[2] == [9]


RULES = FoleyRules(rooms=[(r"INT\. SHOP", "room-shop", "a shop"),
                          (r"SHOP", "room-street", "outside a shop")],
                   events=[(r"\bbell\b", "bell", "a bell"), (r"\bdoor\b", "door", "a door")])
SHOP = ("Title: A bell and a door\n====\n\n"
        "INT. SHOP - DAY\n[[day:1]]\n\nThe bell rings. The door opens.\n\n"
        "MAEVE\nIs that the bell?\n\nThe bell again.\n\n"
        "EXT. SHOP - DAY\n\nA door slams.\n")


def test_foley_places_room_tone_first_then_events_on_action_lines():
    text, total, rooms, unroomed = RULES.stamp(SHOP)
    lines = text.split("\n")
    i = lines.index("INT. SHOP - DAY")
    assert lines[i + 1:i + 7] == ["[[day:1]]", "", "[[foley:room-shop|a shop]]",
                                  "[[foley:bell|a bell]]", "[[foley:door|a door]]",
                                  "The bell rings. The door opens."]
    # dialogue is not a cue, and a sound fires once per scene
    assert text.count("[[foley:bell|") == 1
    j = lines.index("EXT. SHOP - DAY")
    assert lines[j + 2:j + 5] == ["[[foley:room-street|outside a shop]]",
                                  "[[foley:door|a door]]", "A door slams."]
    assert (total, rooms, unroomed) == (5, 2, [])


def test_foley_leaves_the_title_block_alone():
    text = RULES.stamp(SHOP)[0]
    assert "[[foley" not in text.split("====")[0]


def test_foley_is_idempotent_and_reports_unroomed_slugs():
    text = RULES.stamp(SHOP)[0]
    assert RULES.stamp(text)[0] == text
    assert RULES.stamp("INT. CAVE - DAY\nDrip.")[3] == ["INT. CAVE - DAY"]


BODY = ("EXT. ONE - DAY\n[[ep:1|Pilot]]\n[[day:1]]\n[[foley:room-a|a room]]\nA.\n\n"
        "INT. TWO - DAY\n[[act:1]]\nB.\n\n"
        "EXT. THREE - NIGHT\n[[ep:2|Second]]\nC.\n")


def test_group_render_and_cue_sheet():
    eps = group(parse_scenes(BODY, markers=("ep", "act", "foley", "day")))
    assert [(e["ep"], e["title"], len(e["acts"])) for e in eps] == [
        (1, "Pilot", 2), (2, "Second", 1)]
    show = Show(title="T", recaps={2: [(None, "Before."), ("MAEVE", "A line.")]})
    ep1 = render_episode(eps[0], show)
    assert "[[ad:1.1]]" in ep1 and "> **MAIN TITLES** <" in ep1
    assert ep1.index("[[foley:room-a|a room]]") < ep1.index("\nA.")
    assert ep1.rstrip().endswith("> **END OF EPISODE 1** <")
    ep2 = render_episode(eps[1], show)
    assert "> **PREVIOUSLY ON T** <" in ep2 and "\nMAEVE\nA line.\n" in ep2
    cues, rows = cue_sheet(eps, show)
    assert [c["kind"] for c in cues] == ["foley", "ad"]
    assert [r["breaks"] for r in rows] == [1, 0]


def test_a_scene_before_the_first_episode_marker_is_an_error():
    with pytest.raises(ValueError, match="precedes"):
        group(parse_scenes("EXT. A - DAY\nX."))
