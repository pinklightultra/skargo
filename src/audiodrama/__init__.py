"""Libraries for turning a Fountain screenplay into a scored, mixed audio drama.

Six libraries, each usable on its own:

    audiodrama.script   Fountain parsing, [[marker]] handling, episode cutting, cue sheets
    audiodrama.voice    speakable text, the audio timeline, and SAPI / Edge / Synthesia casts
    audiodrama.sound    WAV I/O and the foley synthesis primitives (modal, Karplus-Strong, noise)
    audiodrama.score    music scoring: slots cut from a backlog, levelled against speech
    audiodrama.mix      the numpy mixer, music level measurement, A/B renders, mp3 export
    audiodrama.qa       draft-integrity scoring: repetition, shape, slugs, plants, recaps, foley

Nothing in here knows about any one show. A show is a config module that hands these
libraries its tables -- cast, recaps, foley rules, sound recipes, music slots, canon
checks. examples/demo/ is a complete one, small enough to read in one sitting.

Everything runs mono at 22050 Hz by default and needs nothing past numpy: no ffmpeg,
no scipy. Edge voices need `edge-tts` and `miniaudio`, mp3 export needs `lameenc`.
"""

__version__ = "0.1.0"
SR = 22050
