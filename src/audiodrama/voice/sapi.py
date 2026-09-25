"""Windows SAPI cast: every line rendered inside ONE PowerShell process.

Spawning a process per line would cost more than the synthesis does, so the jobs go
into a JSON manifest and one script walks it.

A cast is {part: (voice, pitch %, rate -10..10)}. Rate rides SpeechSynthesizer.Rate,
pitch rides SSML prosody, because System.Speech honours rate more reliably there.
Two installed voices can carry a whole cast this way; whether that is thin or on
brief depends on the show.
"""

import json
import subprocess
from pathlib import Path

from .text import xml_escape  # noqa: F401  (re-exported for SSML callers)

DAVID, ZIRA = "Microsoft David Desktop", "Microsoft Zira Desktop"

PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$jobs = Get-Content -Raw -Encoding UTF8 '{jobs}' | ConvertFrom-Json
$dir = '{dir}'
$i = 0
$lastVoice = ''
foreach ($j in $jobs) {{
    $i++
    if ($j.voice -ne $lastVoice) {{ $synth.SelectVoice($j.voice); $lastVoice = $j.voice }}
    $synth.Rate = [int]$j.rate
    $out = Join-Path $dir $j.wav
    $synth.SetOutputToWaveFile($out)
    $ssml = '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">' +
            '<prosody pitch="' + $j.pitch + '%">' + $j.text + '</prosody></speak>'
    try {{ $synth.SpeakSsml($ssml) }} catch {{ $synth.Speak($j.text) }}
    if ($i % 200 -eq 0) {{ Write-Host "  rendered $i / $($jobs.Count)" }}
}}
$synth.SetOutputToNull()
$synth.Dispose()
Write-Host "DONE $i"
"""


def apply_castconfig(cast, path):
    """Fold a player's saved pitch offsets (in cents) into the cast. Mutates cast.

    A browser auditions a pitch change by resampling, so it can only speak in cents,
    and resampling drags the speed along with it. Here the shift becomes an SSML
    prosody percentage, which moves pitch and leaves the pace alone.
    Returns {part: (old pitch, new pitch)}.
    """
    path = Path(path)
    if not path.exists():
        return {}
    cents = json.loads(path.read_text(encoding="utf-8"))
    applied = {}
    for name, c in cents.items():
        if name not in cast or not c:
            continue
        voice, pitch, rate = cast[name]
        shifted = round((1 + pitch / 100.0) * 2 ** (float(c) / 1200) * 100 - 100)
        cast[name] = (voice, max(-95, min(200, shifted)), rate)
        applied[name] = (pitch, cast[name][1])
    return applied


def render_jobs(jobs, cast):
    """Generic jobs ({wav, voice_as, text}) -> SAPI jobs with voice, pitch and rate."""
    out = []
    for j in jobs:
        voice, pitch, rate = cast[j["voice_as"]]
        out.append({"wav": j["wav"], "voice": voice, "pitch": pitch,
                    "rate": rate, "text": j["text"]})
    return out


def render(sapi_jobs, line_dir, work_dir, log=print):
    """Run the batch. Writes jobs.json and render.ps1 into work_dir."""
    line_dir, work_dir = Path(line_dir), Path(work_dir)
    line_dir.mkdir(parents=True, exist_ok=True)
    jf = work_dir / "jobs.json"
    jf.write_text(json.dumps(sapi_jobs), encoding="utf-8")
    ps = work_dir / "render.ps1"
    ps.write_text(PS.format(jobs=str(jf).replace("\\", "\\\\"),
                            dir=str(line_dir).replace("\\", "\\\\")), encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", str(ps)], capture_output=True, text=True)
    if log:
        log(r.stdout.strip()[-800:] or r.stderr.strip()[-800:])
    return r.returncode == 0
