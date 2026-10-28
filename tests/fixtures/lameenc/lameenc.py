"""Hermetic stand-in for the mp3 extra. Records the bitrate in the file header."""


class Encoder:
    def __init__(self):
        self.br = 96
        self.sr = 0
        self.ch = 0
        self.q = 0

    def set_bit_rate(self, value):
        self.br = int(value)

    def set_in_sample_rate(self, value):
        self.sr = int(value)

    def set_channels(self, value):
        self.ch = int(value)

    def set_quality(self, value):
        self.q = int(value)

    def encode(self, pcm):
        return b"LAME" + self.br.to_bytes(2, "little") + len(pcm).to_bytes(4, "little")

    def flush(self):
        return b"\n"
