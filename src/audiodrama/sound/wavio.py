"""WAV in and out, with nothing past numpy.

`read_int16` / `write_int16` are the drama's own format: mono 16-bit at the drama
rate. `read_any` is a small RIFF parser for everything else a backlog holds -- the
`wave` module refuses 32-bit float, which is what Reaper writes by default.
`to_rate` gets a track down to the drama rate without aliasing.
"""

import wave
from pathlib import Path

import numpy as np


class WavError(ValueError):
    pass


def read_int16(p):
    """A 16-bit mono wav as float32 in [-1, 1)."""
    with wave.open(str(p)) as w:
        n = w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    return x


def write_int16(p, x, sr=22050):
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_any(path):
    """(mono float32 signal, rate) from any PCM or float RIFF WAVE.

    Handles int16/24/32, float32/64 and WAVE_FORMAT_EXTENSIBLE. Only the fmt and
    data chunks are read; everything else is skipped by its declared size.
    """
    path = Path(path)
    raw = path.read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise WavError("%s is not a RIFF WAVE file" % path.name)
    fmt = data = None
    i = 12
    while i + 8 <= len(raw):
        cid, n = raw[i:i + 4], int.from_bytes(raw[i + 4:i + 8], "little")
        body = raw[i + 8:i + 8 + n]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            data = body
        i += 8 + n + (n & 1)            # chunks are word-aligned
    if fmt is None or data is None:
        raise WavError("%s has no fmt/data chunk" % path.name)
    tag = int.from_bytes(fmt[0:2], "little")
    nch = int.from_bytes(fmt[2:4], "little")
    rate = int.from_bytes(fmt[4:8], "little")
    bits = int.from_bytes(fmt[14:16], "little")
    if tag == 0xFFFE and len(fmt) >= 26:  # EXTENSIBLE names the real format in its tail
        tag = int.from_bytes(fmt[24:26], "little")
    if tag == 3:
        x = np.frombuffer(data, dtype="<f4" if bits == 32 else "<f8").astype(np.float32)
    elif tag == 1 and bits == 16:
        x = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    elif tag == 1 and bits == 32:
        x = np.frombuffer(data, dtype="<i4").astype(np.float32) / 2147483648.0
    elif tag == 1 and bits == 24:
        b = np.frombuffer(data[:len(data) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | b[:, 1].astype(np.int32) << 8
             | b[:, 2].astype(np.int8).astype(np.int32) << 16)
        x = v.astype(np.float32) / 8388608.0
    else:
        raise WavError("%s is format %d at %d-bit, which is not handled"
                       % (path.name, tag, bits))
    if nch > 1:
        x = x[:len(x) // nch * nch].reshape(-1, nch).mean(1)
    return x, rate


def to_rate(x, rate, sr=22050, cut=0.92):
    """Integer-factor decimation to sr, lowpassed first so it does not alias.

    The filter is an rFFT mask with a linear edge from cut*Nyquist to Nyquist:
    vectorised, and no scipy.
    """
    if rate == sr:
        return x
    step = rate / sr
    if abs(step - round(step)) > 1e-6:
        raise WavError("%d Hz is not an integer multiple of %d" % (rate, sr))
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / rate)
    lo = sr / 2 * cut
    g = np.ones_like(f)
    g[f > sr / 2] = 0.0
    edge = (f >= lo) & (f <= sr / 2)
    if edge.any():
        g[edge] = np.linspace(1, 0, edge.sum())
    return np.fft.irfft(X * g, len(x))[::int(round(step))].astype(np.float32)
