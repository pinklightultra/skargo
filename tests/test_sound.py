import numpy as np
import pytest

from audiodrama.sound import (Synth, WavError, build, coverage, cue_keys, read_any, read_int16,
                              to_rate, write_int16)


def riff(fmt, data, extra=b""):
    """A minimal RIFF WAVE: fmt chunk, any extra chunks, data chunk."""
    def chunk(cid, body):
        return cid + len(body).to_bytes(4, "little") + body + (b"\0" if len(body) & 1 else b"")
    body = b"WAVE" + chunk(b"fmt ", fmt) + extra + chunk(b"data", data)
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def fmt(tag, nch, rate, bits, ext_tag=None):
    block = nch * bits // 8
    f = (tag.to_bytes(2, "little") + nch.to_bytes(2, "little") + rate.to_bytes(4, "little")
         + (rate * block).to_bytes(4, "little") + block.to_bytes(2, "little")
         + bits.to_bytes(2, "little"))
    if ext_tag is not None:
        f += (22).to_bytes(2, "little") + bits.to_bytes(2, "little") + (0).to_bytes(4, "little")
        f += ext_tag.to_bytes(2, "little") + bytes(14)
    return f


def test_int16_round_trip(tmp_path):
    x = np.sin(np.linspace(0, 20, 1000)).astype(np.float32) * 0.8
    write_int16(tmp_path / "a.wav", x)
    assert np.max(np.abs(read_int16(tmp_path / "a.wav") - x)) < 2 / 32767


def test_read_any_float32_stereo_mixes_to_mono(tmp_path):
    lr = np.array([[0.5, 0.25]] * 4, dtype="<f4")
    p = tmp_path / "f.wav"
    p.write_bytes(riff(fmt(3, 2, 44100, 32), lr.tobytes()))
    x, rate = read_any(p)
    assert rate == 44100 and np.allclose(x, 0.375)


def test_read_any_24_bit_and_32_bit_pcm(tmp_path):
    vals = [-8388608, 0, 8388607]
    p = tmp_path / "24.wav"
    p.write_bytes(riff(fmt(1, 1, 22050, 24), b"".join(v.to_bytes(3, "little", signed=True)
                                                      for v in vals)))
    x, _ = read_any(p)
    assert np.allclose(x, [-1.0, 0.0, 1.0], atol=1e-6)
    p = tmp_path / "32.wav"
    p.write_bytes(riff(fmt(1, 1, 22050, 32), np.array([-2 ** 31, 2 ** 30], "<i4").tobytes()))
    assert np.allclose(read_any(p)[0], [-1.0, 0.5])


def test_read_any_extensible_and_odd_sized_chunks(tmp_path):
    # WAVE_FORMAT_EXTENSIBLE naming float in its tail, behind a 3-byte chunk that has
    # to be skipped with its pad byte
    p = tmp_path / "ext.wav"
    junk = b"LIST" + (3).to_bytes(4, "little") + b"abc\0"
    p.write_bytes(riff(fmt(0xFFFE, 1, 48000, 32, ext_tag=3),
                       np.array([0.1, -0.2], "<f4").tobytes(), junk))
    x, rate = read_any(p)
    assert rate == 48000 and np.allclose(x, [0.1, -0.2])


def test_read_any_refuses_what_it_cannot_read(tmp_path):
    (tmp_path / "no.wav").write_bytes(b"OggS" + bytes(40))
    with pytest.raises(WavError, match="not a RIFF"):
        read_any(tmp_path / "no.wav")
    (tmp_path / "u8.wav").write_bytes(riff(fmt(1, 1, 8000, 8), bytes(10)))
    with pytest.raises(WavError, match="not handled"):
        read_any(tmp_path / "u8.wav")


def test_to_rate_lowpasses_before_decimating():
    t = np.arange(44100) / 44100
    keep = to_rate(np.sin(2 * np.pi * 1000 * t), 44100)
    gone = to_rate(np.sin(2 * np.pi * 15000 * t), 44100)   # would alias to 7050 Hz
    assert len(keep) == 22050
    assert np.sqrt((keep ** 2).mean()) == pytest.approx(0.707, abs=0.01)
    assert np.sqrt((gone ** 2).mean()) < 0.01
    with pytest.raises(WavError, match="integer multiple"):
        to_rate(np.zeros(4800), 48000)


def test_synth_is_seeded():
    a, b = Synth(22050, seed=5), Synth(22050, seed=5)
    assert np.array_equal(a.room(60, 1800, -6), b.room(60, 1800, -6))
    assert not np.array_equal(Synth(seed=6).noise(0.1), Synth(seed=5).noise(0.1))


def test_band_keeps_the_band():
    S = Synth()
    t = S.t(1.0)
    y = S.band(np.sin(2 * np.pi * 100 * t) + np.sin(2 * np.pi * 1000 * t), 500, 2000)
    assert np.allclose(y, np.sin(2 * np.pi * 1000 * t), atol=1e-6)


def test_foley_build_and_coverage(tmp_path):
    made = build({"room-a": lambda: np.zeros(22050), "knock": lambda: np.ones(11025) * .1},
                 tmp_path)
    assert made == {"room-a": 1.0, "knock": 0.5}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["knock.wav", "room-a.wav"]
    cues = [{"kind": "foley", "key": "knock"}, {"kind": "foley", "key": "bell"},
            {"kind": "ad", "key": "ad-1.1"}]
    assert cue_keys(cues) == {"knock", "bell"}
    assert coverage(cue_keys(cues), made) == (["bell"], ["room-a"])
