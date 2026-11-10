# skargo

skargo (`import audiodrama`) turns a Fountain screenplay into mixed episode WAVs for someone who wants the cut, the cues, and a scratch mix before a cast records.

The pipeline was built to produce a six-episode radio serial, then split into
libraries with everything specific to that show moved into a config folder.
`examples/demo/` is a complete show written for this repo: *LOW TIDE*, two short
episodes about a letter that washes up at an island post office. The pipeline runs
it from script to finished WAVs offline, on any OS, in under half a minute.

## Quickstart

From the repo root, on Python 3.10 or newer:

```
pip install -e .
python -m examples.demo.run all
```

`pip install -e .` installs the `audiodrama` package. Numpy is the only dependency.
The demo runner is not an installed script: Python finds `examples/` because the
current directory is the repo root.

`all` writes the scratch-cast episodes here:

```
out/demo/audio/episodes/LOW_TIDE_EP1_scratch.wav
out/demo/audio/episodes/LOW_TIDE_EP2_scratch.wav
```

Without installing, set `PYTHONPATH` to `src` plus the repo root (`src;.` on Windows,
`src:.` elsewhere) and run the same command from the repo root.

The demo speaks with the **scratch cast**: placeholder murmurs about as long as each
line takes to say, at each part's own pitch, levelled to the speech reference the
music is measured against. The pacing, ad pods, music levels and draft check all run
before any real voice exists. For real voices:

```
pip install -e '.[edge]'
python -m examples.demo.run voices --cast edge
python -m examples.demo.run timeline --voices edge
python -m examples.demo.run mix --voices edge
```

Edge fetches each line from the read-aloud endpoint, so that cast needs a network,
and the endpoint can change. Fine for a draft. Windows can use `--cast sapi`
instead, which needs no extras.

## Example

This is stdout from `python -m examples.demo.run all` on the scratch cast, default
root. Both WAVs are mono 16-bit at 22050 Hz, 4.4 minutes each.

```
== init
copied 2 parts

== script
stamped 6 markers across 7 scenes
stamped 37 foley cues (7 room tones) across 2 parts
wrote 2 episodes -> episodes/
  EP1 The Causeway             3 acts  2 ads  story 3:33  slot 8:33   23 foley
  EP2 High Water               3 acts  2 ads  story 3:18  slot 8:18   14 foley
  TOTAL                       6:51 story, 16:51 slot, 41 cues

== check
=== LOW TIDE check :: 7 scenes ===

[ ok ] REPETITION: 65/65 substantive lines unique (1.0000); 0 motifs over budget
[ ok ] NGRAM: no 7-gram repeats 3+ times across 951 tokens
[ ok ] SHAPE: scene words 82-183, mean 136, CV 0.28
[ ok ] POSITIONAL: no slot shared by 30%+ of scenes
[ ok ] SLUG: 7 slugs valid, 3 distinct time tokens
[ ok ] DAY: days 1..2 monotonic across 7 scenes
[ ok ] CLOCK: 0 timestamped scenes run forward within all 0 days
[ ok ] CAST: 5 speakers, 52 cues; top [('MAEVE', 17), ('TOBY', 15), ('IRIS', 13), ('OWEN', 5)]
[ ok ] CANON: the keeper is unnamed until the door opens -- first 'iris' at 51%, door at 49%
[ ok ] CANON: the sister is revealed once, late -- 1 mention, at 78%
[ ok ] PLANT: the stamps: 6 mentions, 18% -> 96%
[ ok ] PLANT: the biscuit tins: 5 mentions, 36% -> 82%
[ ok ] STYLE: no em dashes
[ ok ] EPISODES: 2 episodes, 6 acts, 4 ad breaks, 3-3 min
[ ok ] EPISODES: no episode is orphaned mid-day -- spread 1.08x
[ ok ] EPISODES: episodes fit one slot (longest < 1.4x shortest) -- spread 1.08x
[ ok ] RECAPS: 3 quoted clips across 1 recap, all verbatim and correctly attributed
[ ok ] FOLEY: every scene has a room tone -- 0 exceptions
[ ok ] FOLEY: the room tone is the first cue -- 0 exceptions
[ ok ] FOLEY: 37 cues, 23 distinct sounds to build
[ ok ] FOLEY: 0 scenes carry room tone only
[ ok ] CUT: 2 episode files, 4 ad breaks, 0 landing anywhere but an act break
[ ok ] CUT: cues.json written for the audio pass
[ ok ] LENGTH: 1058 words, 7 scenes, est. 7 pages


0 failures, 0 warnings

== timeline
timeline: action 27, actout 8, ad 4, card 9, foley 37, recap 1, screen 1, slug 7, speech 55
wrote audio/timeline.json, 100 utterances

== voices
scratch cast: 100 lines rendered, 0 kept -> lines_scratch

== timeline
timeline: action 27, actout 8, ad 4, card 9, foley 37, recap 1, screen 1, slug 7, speech 55
wrote audio/timeline.json, 100 utterances

== sfx
synthesised 23 sounds -> audio/sfx/ (6 room tones, 17 events)

== backlog
wrote 2 backlog tracks -> backlog/

== music
wrote music.json with the default picks; edit and re-run
  titles        low_tide_theme.wav        10.0s  -3 dB vs speech  rms 0.0499  peak 0.24
  actin         low_tide_theme.wav         3.0s  -4 dB vs speech  rms 0.0445  peak 0.29
  actout        low_tide_theme.wav         4.5s  -2 dB vs speech  rms 0.0560  peak 0.42
  recap         harbour_bed.wav           30.0s  -14 dB vs speech  rms 0.0141  peak 0.04
4 slots in actin/actout/recap/titles, from 2 of the backlog's tracks

== mix
  EP1   4.4 min   19 sfx  2 ad pods  6 music  LOW_TIDE_EP1_scratch.wav
  EP2   4.4 min   11 sfx  2 ad pods  7 music  LOW_TIDE_EP2_scratch.wav
wrote 8.7 min of audio -> audio/episodes/

== levels
EP1  4.4 min  music-only energy in 28.8s of it
6 runs
  at          secs     music      prog    delta
   0:39.14   10.0    0.0500    0.0189    +8.4 dB
   0:49.79    4.5    0.0562    0.0000   +99.0 dB
   0:57.87    3.0    0.0442    0.0602    -2.7 dB
   3:05.30    4.5    0.0562    0.0019   +29.5 dB
   3:13.38    3.0    0.0442    0.0575    -2.3 dB
   4:16.77    4.5    0.0562    0.0020   +28.8 dB

full-mix peak with music 0.548 (ceiling 0.89)
EP2  4.4 min  music-only energy in 50.1s of it
7 runs
  at          secs     music      prog    delta
   0:00.01   21.4    0.0140    0.0662   -13.5 dB
   1:04.83   10.0    0.0500    0.0189    +8.4 dB
   1:15.48    4.5    0.0562    0.0000   +99.0 dB
   1:23.55    3.0    0.0442    0.0592    -2.5 dB
   2:46.90    4.5    0.0562    0.0027   +26.2 dB
   2:54.97    3.0    0.0442    0.0586    -2.4 dB
   4:18.17    4.5    0.0562    0.0019   +29.6 dB

full-mix peak with music 0.533 (ceiling 0.89)
```

The `slot` column prices each ad break at 150 seconds. The mix uses the 6-second
audition pod, which is why a 3:33 story comes back as a 4.4 minute WAV.

The script pass counts a room cue on each of the 7 scenes. The synth writes 6 room
files because the post office tone is used in both episodes, plus 17 event sounds.

A delta of +99.0 dB is a placement whose programme RMS rounds to 0.0000, so the
ratio is the music over near-silence. The recap on episode 2 sits under speech and
measures -13.5 dB; that slot is set at -14.

## The six libraries

| package | what it does |
|---|---|
| `audiodrama.script` | Fountain parsing; `[[ep:]]` / `[[act:]]` scene markers; foley cue stamping (`FoleyRules`); cutting a feature draft into episodes with recaps, loglines, EPISODES.md and CUES.md (`write_cut`) |
| `audiodrama.voice` | turning screenplay lines into speakable text; the audio timeline (`TimelineParser`, `assign_wavs`); four casts: scratch (no engine), SAPI (Windows), Edge neural voices, and Synthesia avatar video with captions aligned back to lines |
| `audiodrama.sound` | WAV I/O for any PCM or float WAV; a seeded foley synth (`Synth`: modal, Karplus-Strong, band noise, room tones, footsteps, a hummed melody); `build` turns a dict of recipes into files |
| `audiodrama.score` | music scoring. Cuts slots (titles, act-ins, act-outs, recap beds, one bed per scene genre) from a folder of songs, levelled as RMS against measured speech; `analyze` holds the measurements the picks are made on |
| `audiodrama.mix` | the numpy mixer (lines, foley beds, music, ad pods, recaps, and a peak ceiling on the master); `music_levels` measures every music placement against the programme under it; scene A/B renders; mp3 export |
| `audiodrama.qa` | draft scoring. `DraftCheck` scores a draft on repetition, n-gram reuse, scene shape, template smell, slugs, time of day, set-ups and pay-offs, the episode cut, recaps and foley coverage. The show's own canon rules plug in as a function |

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
python -m examples.demo.run mp3         # needs the mp3 extra: pip install -e '.[mp3]'
```

The same stages, and the player that writes `mixconfig.json`, are on one page.
The desk binds to 127.0.0.1, port 8765 unless you pass `--port`, and prints the URL:

```
python -m examples.demo.desk --root out/demo
```

Every control runs a stage or saves a setting, and the caption is the outcome.
The control × outcome matrix is [docs/control-outcome-matrix.md](docs/control-outcome-matrix.md).

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

MIT. See [LICENSE](LICENSE).
