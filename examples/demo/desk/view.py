"""Paint the desk from the control list and the current player state."""

from html import escape
from pathlib import Path

from .controls import BUSES, CASTS, EPISODES, FADERS, FOLEY_KEYS, STAGES, VOICES

STATIC = Path(__file__).resolve().parent / "static"
_PAGE = (STATIC / "page.html").read_text(encoding="utf-8")


def _pressed(on):
    return "true" if on else "false"


def _choice(control, value, label, pressed, aria):
    return (
        '<button type="button" data-id="%s:%s" data-control="%s" data-value="%s" '
        'aria-pressed="%s" aria-label="%s">%s</button>'
        % (control, escape(str(value)), control, escape(str(value)),
           _pressed(pressed), escape(aria), escape(label))
    )


def stages_html():
    rows = []
    for index, (sid, label, blurb) in enumerate(STAGES, start=1):
        aria = label if sid == "all" else "Run %s" % label
        rows.append(
            '<li><button type="button" class="stage%s" data-id="stage:%s" '
            'data-control="stage" data-stage="%s" aria-label="%s">'
            '<span class="num">%02d</span><span class="name">%s</span>'
            '<span class="blurb">%s</span></button></li>'
            % (" primary" if sid == "all" else "", sid, sid, escape(aria),
               index, escape(label), escape(blurb))
        )
    return "\n".join(rows)


def take_html(state):
    cast = "".join(
        _choice("cast", name, name, state["cast"] == name, "Cast %s" % name)
        for name in CASTS)
    voices = "".join(
        _choice("voices", name, name, state["voices"] == name, "Voices %s" % name)
        for name in VOICES)
    episodes = "".join(
        _choice("episode", n, "EP%d" % n, n in state["eps"], "Episode %d" % n)
        for n in EPISODES)
    pod = "" if state["pod"] is None else escape(("%g" % state["pod"]))
    parts = [
        '<h2>Take</h2>',
        '<p class="group-label">Cast</p>',
        '<div class="choices">%s</div>' % cast,
        '<p class="group-label">Lines the mix reads</p>',
        '<div class="choices">%s</div>' % voices,
        '<button type="button" data-id="force" data-control="force" '
        'aria-pressed="%s" aria-label="Force a new take">Force a new take</button>'
        % _pressed(state["force"]),
        '<p class="group-label">Episodes</p>',
        '<div class="choices">%s</div>' % episodes,
        '<button type="button" data-id="defaults" data-control="defaults" '
        'aria-pressed="%s" aria-label="Ignore the player">Ignore the player</button>'
        % _pressed(state["defaults"]),
        '<label class="field">Pod override'
        '<input id="pod-override" data-id="pod-override" data-control="pod-override" '
        'type="number" min="0" max="30" step="0.5" value="%s" '
        'aria-label="Pod override"></label>' % pod,
        '<label class="field">mp3 bitrate'
        '<input id="kbps" data-id="kbps" data-control="kbps" type="number" '
        'min="32" max="320" step="1" value="%d" aria-label="mp3 bitrate"></label>'
        % int(state["kbps"]),
        '<label class="field">Backlog folder'
        '<input id="backlog" data-id="backlog" data-control="backlog" type="text" '
        'value="%s" spellcheck="false" aria-label="Backlog folder" '
        'placeholder="this folder\'s backlog"></label>' % escape(state["backlog"]),
        '<button type="button" data-id="reset-slots" data-control="reset-slots" '
        'aria-label="Restore slot picks">Restore slot picks</button>',
    ]
    return "\n".join(parts)


def player_html(state):
    mix = state["mix"]
    off = mix.get("off") or {}
    muted = set(mix.get("muted_keys") or [])
    buses = "".join(
        '<button type="button" data-id="bus:%s" data-control="bus" data-bus="%s" '
        'aria-pressed="%s" aria-label="%s bus">%s</button>'
        % (bid, bid, _pressed(off.get(bid) is not False), escape(label), escape(label))
        for bid, label in BUSES)
    faders = []
    for key, label, lo, hi, step in FADERS:
        value = mix.get(key, lo)
        faders.append(
            '<label class="fader"><span>%s</span>'
            '<input data-id="fader:%s" data-control="fader" data-key="%s" '
            'type="range" min="%g" max="%g" step="%g" value="%g" '
            'aria-label="%s">'
            '<output>%g</output></label>'
            % (escape(label), key, key, lo, hi, step, float(value),
               escape(label), float(value))
        )
    mutes = "".join(
        '<button type="button" data-id="mute:%s" data-control="mute" data-key="%s" '
        'aria-pressed="%s" aria-label="Mute %s">%s</button>'
        % (escape(key), escape(key), _pressed(key in muted),
           escape(key.replace("-", " ")), escape(key.replace("-", " ")))
        for key in FOLEY_KEYS)
    return "\n".join([
        '<h2>Player</h2>',
        '<p class="lede">Buses and levels are written to the player. '
        'Mix reads them unless the margin says to ignore it.</p>',
        '<p class="group-label">Buses</p>',
        '<div class="choices">%s</div>' % buses,
        '<div class="faders">%s</div>' % "\n".join(faders),
        '<button type="button" class="texty" data-id="reset-player" '
        'data-control="reset-player" aria-label="Reset the player">Reset the player</button>',
        '<p class="group-label">Mute a cue</p>',
        '<div class="choices mutes">%s</div>' % mutes,
    ])


def short_root(path):
    parts = [part for part in str(path).replace("\\", "/").split("/") if part]
    if len(parts) <= 2:
        return str(path)
    return "/".join(parts[-2:])


def render_page(state):
    html = _PAGE
    html = html.replace("<!--ROOT-->", escape(state["root"]))
    html = html.replace("<!--SHORT-->", escape(short_root(state["root"])))
    html = html.replace("<!--STAGES-->", stages_html())
    html = html.replace("<!--TAKE-->", take_html(state))
    html = html.replace("<!--PLAYER-->", player_html(state))
    return html
