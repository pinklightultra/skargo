"""Make screenplay text speakable by a TTS engine.

Every function here exists because an engine read something wrong: letters for a
run of capitals, the verb for AM, a pause for a stray space before a comma.
"""

import re

ABBR = [("INT./EXT.", "Interior, exterior."), ("EXT./INT.", "Exterior, interior."),
        ("INT.", "Interior."), ("EXT.", "Exterior.")]


def tidy(s):
    """Fix the spacing that substitution leaves behind, so the engine does not pause."""
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,.;:])\s*\1+", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def title_caps(s, keep_meridiem=False):
    """Title-case runs of capitals so the engine reads words, not letters.

    keep_meridiem protects AM/PM in clock times: SAPI says the meridiem for "AM" and
    the verb for "Am", so a slug reading 5:58 AM must stay uppercase. Annotation tags
    want the opposite, because "I AM DOING WELL" is the verb.
    """
    if keep_meridiem:
        s = re.sub(r"\b([AP])\.?M\.?\b", lambda m: m.group(1) + "M", s)

    def one(m):
        w = m.group(1)
        if keep_meridiem and w in ("AM", "PM"):
            return w
        return w.title()
    s = re.sub(r"\b([A-Z]{2,})\b", one, s)
    return s.replace("'S ", "'s ").replace("'S.", "'s.").replace("'S,", "'s,")


def speakable_slug(s, abbr=ABBR):
    """A slug is orientation for the listener, so it has to read as English."""
    for a, b in abbr:
        if s.startswith(a):
            s = b + " " + s[len(a):].strip()
            break
    s = s.replace(" - ", ". ")
    return tidy(title_caps(s, keep_meridiem=True)).rstrip(".") + "."


def speakable_screen(s):
    """Signs, receipts, banners and documents, read by the narrator."""
    s = s.replace("--", ",").replace("&", " and ")
    return tidy(title_caps(s, keep_meridiem=True)).rstrip(".") + "."


def speakable_annotation(tag, prefix="System"):
    """A bracketed annotator tag (`[ SYSTEM / GENRE: FARCE ]`) read aloud.

    Returns (text, trailing_pause). text is None when the tag is empty: an empty tag
    is the annotator trying to label a scene and producing nothing, so it has to be
    silence rather than a spoken word. `GENRE:` with nothing after it is the same
    failure caught halfway, so it speaks and then stops.
    """
    t = re.sub(r"\s+", " ", tag.replace("_", " ")).strip()
    if not t:
        return None, 1.4
    pause = 0.0
    if t.endswith(":"):
        t = t[:-1].strip()
        pause = 1.1
        if not t:
            return None, 1.4
    t = t.replace("--", ",").replace("%", " percent").replace('"', "")
    t = tidy(title_caps(t)).strip(" .,")
    if not t:
        return None, 1.4
    return tidy(prefix + ". " + t[0].upper() + t[1:] + "."), pause


def xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))
