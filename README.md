# audiodrama

Turn a Fountain screenplay into a scored, mixed, quality-checked audio drama, with
nothing past numpy.

The pipeline was built to produce a six-episode radio serial, then split into
libraries with everything specific to that show moved into a config folder.
`examples/demo/` is a complete show written for this repo: *LOW TIDE*, two short
episodes about a letter that washes up at an island post office. The pipeline runs
it from script to finished WAVs offline, on any OS, in under half a minute.

```
pip install -e .                      # numpy is the only dependency
python -m examples.demo.run all       # -> out/demo/audio/episodes/LOW_TIDE_EP*.wav
```

Without installing, set `PYTHONPATH` to `src` plus the repo root (`src;.` on Windows,
`src:.` elsewhere).

The demo speaks with the **scratch cast**: placeholder murmurs as long as each line
takes to say, at each part's own pitch, levelled to the speech reference the music is
measured against. The pacing, ad pods, music levels and QA all run before any real
voice exists. For real voices:

```
pip install -e .[edge]                                  # Edge neural voices
python -m examples.demo.run voices --cast edge
python -m examples.demo.run timeline --voices edge      # stamp the real durations
python -m examples.demo.run mix --voices edge
```

Windows can use `--cast sapi` instead, which needs no extras.

## The six libraries

| package | what it does |
|---|---|
| `audiodrama.script` | Fountain parsing; `[[ep:]]` / `[[act:]]` scene markers; foley cue stamping (`FoleyRules`); cutting a feature draft into episodes with recaps, loglines, EPISODES.md and CUES.md (`write_cut`) |
| `audiodrama.voice` | turning screenplay lines into speakable text; the audio timeline (`TimelineParser`, `assign_wavs`); four casts: scratch (no engine), SAPI (Windows), Edge neural voices, and Synthesia avatar video with captions aligned back to lines |
| `audiodrama.sound` | WAV I/O for any PCM or float WAV; a seeded foley synth (`Synth`: modal, Karplus-Strong, band noise, room tones, footsteps, a hummed melody); `build` turns a dict of recipes into files |
| `audiodrama.score` | **music scoring.** Cuts slots (titles, act-ins, act-outs, recap beds, one bed per scene genre) from a folder of songs, levelled as RMS against measured speech; `analyze` holds the measurements the picks are made on |
| `audiodrama.mix` | the numpy mixer (lines, foley beds, music, ad pods, recaps, and a peak ceiling on the master); `music_levels` measures every music placement against the programme under it; scene A/B renders; mp3 export |
| `audiodrama.qa` | **draft scoring.** `DraftCheck` scores a draft on repetition, n-gram reuse, scene shape, template smell, slugs, time of day, set-ups and pay-offs, the episode cut, recaps and foley coverage. The show's own canon rules plug in as a function |

Nothing under `src/` knows the name of any show.

## The stages

```
python -m examples.demo.run init        # copy parts/*.fountain into --root
python -m examples.demo.run script      # markers, foley cues, full draft, episode cut
python -m examples.demo.run check       # draft quality report, exit 1 on failures
python -m examples.demo.run timeline    # episodes -> audio/timeline.json + jobs.json
python -m examples.demo.run voices      # --cast scratch|sapi|edge
python -m examples.demo.run timeline    # again, to stamp line durations
python -m examples.demo.run sfx         # synthesise foley, report uncovered cue keys
python -m examples.demo.run backlog     # synthesise the demo's two-track song backlog
python -m examples.demo.run music       # cut music slots from the backlog
python -m examples.demo.run mix         # [--voices scratch|sapi|edge] [EP ...]
python -m examples.demo.run levels      # how loud each music placement lands
python -m examples.demo.run mp3         # needs .[mp3]
```

Everything is written under `--root` (default `out/demo`). The source parts are only
ever read.

## Using your own music

No music ships with this repo. The demo's two tracks are synthesised by
`examples/demo/backlog.py`, so a fresh clone runs offline. To score a show with your
own songs, use music you have the rights to and:

1. **Put the songs in one folder, as WAV.** 16-, 24- or 32-bit PCM or 32-bit float,
   mono or stereo (stereo is mixed down). The sample rate must be a whole multiple of
   22,050 Hz: 44.1 kHz works, **48 kHz does not**, so export at 44.1 kHz. MP3 and FLAC
   are not read.
2. **Say which part of which song plays where.** The first `music` run writes
   `audio/music.json` under `--root` from `MUSIC_SLOTS` in `show.py`. From then on
   `music.json` wins, one slot at a time, so edit it rather than `show.py`. Each slot
   is a cut from one song:

   ```json
   "titles": {"track": "my_theme.wav", "start": 0.0, "seconds": 10.0,
              "rms_db": -3.0, "fade_in": 0.3, "fade_out": 2.5}
   ```

   `track` is a file name in your folder. `rms_db` is loudness relative to the
   show's speech, not a peak level: a bed sits around -14, a sting around -2. The
   slots the mixer plays are `titles`, `actin`, `actout`, `recap` and
   `scene_<genre>`. A variant such as `actout_three`, `actout_end` or `recap_ep2`
   overrides the plain slot where it applies.
3. **Cut, mix and check the levels:**

   ```
   python -m examples.demo.run music --backlog /path/to/your/songs
   python -m examples.demo.run mix
   python -m examples.demo.run levels
   ```

   `levels` reports how loud each placement lands over the speech under it. Adjust
   `rms_db` in `music.json` and run `music` and `mix` again.

To find the cuts, `audiodrama.score.profile(Backlog([folder]))` lists each song's
length, brightness and loudness range. `audiodrama.score.analyze` ranks candidate
windows for each role: `calmest_window` for a scene bed, `sting_onset` for an act-out,
`figure_windows` for an act-in and `steady_windows` for a recap. If you render with a
real cast, measure its level with `score.speech_rms(lines_folder)`, which returns
(mean, median), and set `SPEECH_RMS` in `show.py` to the mean.

## Making a new show

Copy `examples/demo/` and replace what is in it:

- `parts/`: the screenplay, as one or more Fountain files in order.
- `show.py`: everything about the show and nothing about audio drama in general:
  the episode cut, recaps, loglines, foley rooms and events, casts, music slots, the
  props the draft check tracks, and the show's own canon rules.
- `sounds.py`: foley recipes, one per cue key, drawn from a single seeded `Synth` so
  every rebuild is sample-identical.
- `backlog.py`: only the demo needs this. A real show points `music --backlog` at
  its songs (see [Using your own music](#using-your-own-music)).
- `run.py`: the pipeline as a CLI. It usually needs only the title changed.

## Things to know before changing a show

- **A wav name is the event's index in the episode** (`ep2_0042.wav`). Anything that
  adds or removes a timeline event, such as a new marker, a new foley cue, or a
  change to the transition set, renumbers every line after it. That invalidates
  rendered voices and any Synthesia manifest. Put music on events that already
  exist, and settle the transition set before you render.
- **Set music levels against speech RMS, not peak.** A dense mixdown normalised to
  peak 0.30 measured 10 dB over the narration it was meant to sit under.
- **Measure music placements from a music-on minus music-off render with the
  master ceiling lifted.** Otherwise the ceiling's rescaling leaks speech into the
  difference. `music_levels` does this.
- **Muting never moves the cut.** A muted voice or sound keeps its time, so an A/B
  of a mix lines up sample for sample.

## Tests

```
pip install pytest
python -m pytest
```

The suite covers each library and runs the demo end to end twice, checking the
second run is byte-identical to the first.

The libraries were also checked, as they stand in this repo, against the original
production scripts they were lifted from: the parts, the draft, the episode cut,
every line of the QA report, all 2,546 timeline events, every foley and music WAV,
and all six mixed episodes on one cast plus the first on another, sample for sample
and byte for byte against the files on disk. 61 checks, 0 differences. That harness
needs the original show, so it is not included here.

## License

MIT
