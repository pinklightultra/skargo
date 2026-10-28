# Control × outcome matrix

The desk (`python -m examples.demo.desk`) and the CLI (`python -m examples.demo.run`) run the same stages. The desk is the player: take choices live in `desk.json`, and buses, levels, and mutes live in `audio/mixconfig.json`.

Every control returns an outcome. `tone` is `ok`, `warn`, or `fail`. The summary is the line in the caption. The log is the pipeline text. `wrote` is the files that click created. A click that does not change the caption is a bug.

Programmatic coverage calls `examples.demo.desk.perform.click`. Browser coverage is Playwright against the page. Both are hermetic: scratch voices, synthesised songs, and a fixture encoder for mp3. Edge is not contacted. SAPI is not launched when `powershell` is absent, and the success and failure branches are patched so Windows CI does not speak.

## Stages

| id | click | outcome |
|---|---|---|
| `stage:init` | Copy the parts | `ok`. Summary `copied 2 parts`. The two fountain files land in `parts/`. A second click copies again and leaves the same bytes. |
| `stage:script` | Stamp and cut | On an empty folder, `fail`, summary `scene numbers not found`. After init, `ok`: markers, `LOW_TIDE.fountain`, `episodes/`, `cues.json`, `EPISODES.md`, `CUES.md`. A second click does not change the part bytes. |
| `stage:check` | Score the draft | No draft: `fail`, `FileNotFoundError`. A clean cut: `ok`, log contains `0 failures`. An em dash in the draft: `fail`, log contains `STYLE`. |
| `stage:timeline` | Build the clock | No episodes: `warn`, `0 utterances`, and the json files are still written. After the cut: `ok`, utterances written. With scratch lines present, each utterance gains `seconds`. With the line source set to edge and no `lines_edge` folder, `seconds` is left off. An uncast speaker prints `WARNING`. |
| `stage:voices` | Render the cast | No `jobs.json`: `fail`, `FileNotFoundError`. Scratch, lines already there: `ok`, log contains `kept`. Force on: `ok`, log contains `rendered`, and the bytes match the previous take. Scratch from nothing: wavs appear. `cast:sapi` without PowerShell: `fail`. Patched SAPI `render` false: `fail`. Patched true: `ok`. `cast:edge` without `edge-tts`: `fail` naming `edge_tts`, no retry loop. Patched `verify` false: `fail`. Patched true: `ok`. |
| `stage:sfx` | Synthesise cues | No `cues.json`: `fail`, `FileNotFoundError`, after the wavs are written. Covered sheet: `ok`, log contains `synthesised`. A cue key with no recipe: `fail`, log contains `MISSING`. |
| `stage:backlog` | Write the two songs | `ok`. `backlog/low_tide_theme.wav` and `backlog/harbour_bed.wav`. |
| `stage:music` | Cut slots | No songs: `fail`, `FileNotFoundError`. A 48 kHz source: `fail`, the rate is not an integer multiple of 22050. `start` past the end of the song: `fail`, `past the end`. After a good cut: `ok`, `titles`, `actin`, `actout`, `recap`. A second click logs `using music.json`. |
| `stage:mix` | Assemble | No timeline file: `fail`, `FileNotFoundError`. An empty timeline: `ok`, `0.0 min`. Lines missing: `fail`, log contains `MISSING`, and the episode wav is still written. Edge lines missing while scratch exists: `ok`, log contains `borrowed`. One episode selected: the log names that episode and not the other. Pod override 8s runs longer than 0s by more than one ad break. Player speech at 0 and every bus muted: the episode is silent, and the log says `from the player`. Ignore the player: the built-in mix is audible and that line is absent. A muted cue: the log contains `muted`. |
| `stage:levels` | Measure music | No timeline: `fail`, `FileNotFoundError`. A clock with none of the selected episodes: `fail`, `KeyError`. With music: `ok`, the log names `EP1` and `EP2`. One episode selected: only that episode is named. |
| `stage:mp3` | Encode | No wavs: `warn`, `0 files`. Wavs and no `lameenc`: `fail`. With the fixture encoder: `ok`, an `.mp3` whose header carries the bitrate from `kbps`. |
| `stage:all` | Run the show | `ok` on a fresh folder: parts, draft, episodes, lines, foley, songs, slots, both episode wavs, no mp3. If check returns 1, the outcome is `fail`, the log names `check`, and foley is not synthesised. |

## Take

| id | click | outcome |
|---|---|---|
| `cast:scratch` | Select scratch | `ok`. `Cast is scratch.` The next voices pass uses it. |
| `cast:sapi` | Select SAPI | `ok`. The next voices pass takes the SAPI branch. |
| `cast:edge` | Select Edge | `ok`. The next voices pass takes the Edge branch. |
| `voices:scratch` | Lines for the mix | `ok`. Mix, levels, mp3, and the timeline stamp use `lines_scratch`. |
| `voices:sapi` | Lines for the mix | `ok`. The primary folder is `lines_sapi`. Mix still falls back to scratch. The timeline stamp does not. |
| `voices:edge` | Lines for the mix | `ok`. Same split: mix falls back, the stamp does not. |
| `force` | Toggle | `ok`. On: `Force is on.` Off: `Force is off.` |
| `episode:1` | Toggle EP1 | `ok`, unless it is the last episode selected, in which case `warn` and the list stays put. |
| `episode:2` | Toggle EP2 | Same rule. |
| `defaults` | Ignore the player | `ok`. On: mix passes `--defaults`. Off: mix reads `mixconfig.json`. |
| `pod-override` | Seconds, or empty | Empty: `ok`, override cleared. A number from 0 to 30: `ok`, and it wins over the player pod. Outside that: `fail`, and the saved value is unchanged. |
| `kbps` | Bitrate | 32 to 320: `ok`. Anything else: `fail`. |
| `backlog` | Folder | Empty: `ok`, music uses `<root>/backlog`. A path: `ok`, the next music pass cuts from that folder. |
| `reset-slots` | Delete `music.json` | File present: `ok`, picks cleared. Absent: `warn`. |

## Player

| id | click | outcome |
|---|---|---|
| `bus:dial` | Dialogue | `ok`. Muted, then live. A muted bus keeps its time. |
| `bus:narr` | Narration | `ok`. Same. |
| `bus:sys` | System | `ok`. Same. |
| `bus:music` | Music | `ok`. Same. |
| `bus:sfx` | Foley hits | `ok`. Same. |
| `bus:bed` | Rooms | `ok`. Same. |
| `fader:gap` | Gap | `ok` inside 0 to 2. Outside: `fail`, file unchanged. |
| `fader:gapSpeech` | Speech gap | `ok` inside 0 to 2. |
| `fader:gapSlug` | Slug gap | `ok` inside 0 to 2. |
| `fader:preScene` | Before a scene | `ok` inside 0 to 3. |
| `fader:actout` | After an act | `ok` inside 0 to 5. |
| `fader:pod` | Player pod | `ok` inside 0 to 30. This is the mixconfig pod. The pod override wins when it is set. |
| `fader:bed` | Room level | `ok` inside 0 to 1. |
| `fader:sfx` | Foley level | `ok` inside 0 to 1.5. |
| `fader:music` | Music level | `ok` inside 0 to 1.5. |
| `fader:speech` | Speech level | `ok` inside 0 to 1.5. At 0, with the buses muted, the episode is silent. |
| `fader:master` | Ceiling | `ok` inside 0.05 to 1.2. |
| `reset-player` | Delete `mixconfig.json` | File present: `ok`. Absent: `warn`. |
| `mute:room-shore` | Mute that cue | `ok`. Pressed means muted. A second click lets it play. |
| `mute:room-postoffice` | Mute that cue | `ok`. |
| `mute:room-harbour` | Mute that cue | `ok`. |
| `mute:room-lamproom` | Mute that cue | `ok`. |
| `mute:room-stairwell` | Mute that cue | `ok`. |
| `mute:room-rock` | Mute that cue | `ok`. |
| `mute:gulls` | Mute that cue | `ok`. A mix afterwards logs `muted`. |
| `mute:steps` | Mute that cue | `ok`. |
| `mute:cork` | Mute that cue | `ok`. |
| `mute:paper` | Mute that cue | `ok`. |
| `mute:bottle` | Mute that cue | `ok`. |
| `mute:clock` | Mute that cue | `ok`. |
| `mute:radio` | Mute that cue | `ok`. |
| `mute:doorbell` | Mute that cue | `ok`. |
| `mute:door` | Mute that cue | `ok`. |
| `mute:switch` | Mute that cue | `ok`. |
| `mute:drawer` | Mute that cue | `ok`. |
| `mute:rope` | Mute that cue | `ok`. |
| `mute:surf` | Mute that cue | `ok`. |
| `mute:tin` | Mute that cue | `ok`. |
| `mute:lamp` | Mute that cue | `ok`. |
| `mute:bolt` | Mute that cue | `ok`. |
| `mute:franking` | Mute that cue | `ok`. |

## CLI process

These are not desk buttons. They are the module entry, covered by a subprocess clicker.

| control | outcome |
|---|---|
| no stage | exit 2, usage on stderr |
| `--help` | exit 0, the stage names on stdout |
| `--cast robot` | exit 2 |
| `init --root` | exit 0, `copied 2 parts` |
| `script` on an empty folder | exit 1, `scene numbers not found` |

## Not a button

`stage:nope`, `cast:robot`, and any other unknown id return `fail` and do not write the player.
