"""Encode rendered episode WAVs to mp3 without ffmpeg.

`lameenc` is LAME behind a Python binding and takes raw PCM, which is what `wave`
already hands back. A mono 22050 Hz drama at 96 kbps is transparent for speech and
holds the music beds; the WAV is roughly 11x the size for no audible gain.

Needs the `mp3` extra: pip install audiodrama[mp3]
"""

import wave
from pathlib import Path


def encode(src, kbps=96, quality=2, dest=None):
    """(dest, seconds, wav bytes, mp3 bytes). quality 2 is LAME's near-best."""
    import lameenc

    src = Path(src)
    with wave.open(str(src)) as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if sw != 2:
            raise ValueError("%s is %d-bit; this expects 16" % (src.name, sw * 8))
        pcm = w.readframes(n)
    enc = lameenc.Encoder()
    enc.set_bit_rate(kbps)
    enc.set_in_sample_rate(sr)
    enc.set_channels(ch)
    enc.set_quality(quality)
    data = enc.encode(pcm) + enc.flush()
    dest = Path(dest) if dest else src.with_suffix(".mp3")
    dest.write_bytes(data)
    return dest, n / sr, src.stat().st_size, len(data)


def encode_all(srcs, kbps=96, log=print):
    srcs = list(srcs)
    if log:
        log("%d files at %d kbps" % (len(srcs), kbps))
    tot_wav = tot_mp3 = tot_sec = 0
    out = []
    for s in srcs:
        dest, sec, wav_b, mp3_b = encode(s, kbps)
        tot_wav += wav_b
        tot_mp3 += mp3_b
        tot_sec += sec
        out.append(dest)
        if log:
            log("  %-26s %5.1f min  %6.1f MB -> %5.1f MB  (%.1fx smaller)"
                % (dest.name, sec / 60, wav_b / 1048576, mp3_b / 1048576, wav_b / mp3_b))
    if log and srcs:
        log("%.1f min total, %.0f MB -> %.0f MB"
            % (tot_sec / 60, tot_wav / 1048576, tot_mp3 / 1048576))
    return out
