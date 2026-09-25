"""Quality scoring for a draft: repetition, template smell, continuity, the episode
cut, recaps, foley coverage, and a hook for the show's own canon.

    from audiodrama.qa import DraftCheck, Prop, load_draft
    chk = DraftCheck(title="MYSHOW", declared={...}, props={"the key": Prop("key", .2, .8)})
    raise SystemExit(chk.run(load_draft("MYSHOW.fountain")))
"""

from .report import Report
from .checks import DraftCheck, Prop, load_draft, parse, episode_map, norm, ANON, TOD

__all__ = ["Report", "DraftCheck", "Prop", "load_draft", "parse", "episode_map", "norm",
           "ANON", "TOD"]
