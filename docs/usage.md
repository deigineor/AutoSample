# AutoSample: usage guide

AutoSample plays notes on your synth over MIDI, records what the synth sends back to your sound card, processes the recordings and exports a ready-to-play instrument (WAV files plus an SFZ and/or DecentSampler mapping).

## What you need

- **Audio interface** with at least one input.
- **MIDI interface** with a MIDI OUT port (USB MIDI is fine).
- **Synth wiring:**
  - MIDI OUT of the interface → MIDI IN of the synth.
  - Audio OUT of the synth → an input of the audio interface.

## First-time setup

### Windows
Pick the **WASAPI** driver (the safe default). Use **ASIO** only if you know why you need it; see the troubleshooting section below.

### Linux
Pick the entry that your sound server exposes: **ALSA**, **JACK** or **PulseAudio/PipeWire**.

## Connect

On the **Connect** tab:

- **Audio input:** driver, device, input channels (a stereo pair or a single mono channel), sample rate (44.1, 48, 88.2 or 96 kHz) and bit depth (16, 24 or 32-bit float).
- **MIDI output:** MIDI port and channel. The channel must match the one your synth listens on.
- **Monitoring:** output device for listening to the synth while you work. "Same as input (recommended)" is the right choice in most cases.
- Use **Refresh device list** if you plug in a device after the app started.

Then check the connection:

1. Press **♪ Test note**. The app plays a note from the middle of the range at full velocity.
2. The level meter should move. If it does not, check the audio cable, the synth's audio output and the MIDI channel.
3. Press **Measure noise**. The app records 1.5 s of silence, shows the noise floor (RMS and peak) and sets the trim thresholds used later.

## Recording settings

On the **Record** tab:

- **Note range:** first and last note. **Step** is the distance between sampled notes: 1 = every note, 3 = minor third, 12 = octave.
- **Velocity layers:** a comma-separated list of velocities from 1 to 127. Each value is a separate layer. The helper fills in N evenly spaced values (up to 16).
- **Round robin:** how many times each note is recorded (up to 16). Useful for a more natural sound on repeated notes.
- **Note length (hold):** how long the key is held before note-off.
- **Tail:**
  - **Fixed tail:** record a set number of seconds after note-off.
  - **Until silence:** the app detects the end of the release on its own. You set the maximum tail and the silence threshold in dB.
- **Pre-roll** (time before note-on) and **gap** (pause between samples).

The summary line shows the number of samples and the estimated recording time.

Press **● Start recording** to begin and **■ Stop** to abort. Keep the synth and the cables untouched while it runs.

### Expression layers

Expression layers record each note at several values of a second controller, like velocity:

- **Mode:** Off, **Aftertouch** (channel pressure) or **MIDI CC**.
- **Values:** a list from 0 to 127. Each value is one layer.
- **CC number:** only for MIDI CC mode. See your synth's MIDI implementation chart.
- **Pause after CC:** time to wait after sending the CC before the note starts.
- **Crossfade controller:** which controller switches or crossfades layers in the sampler: the same one as recorded, or the mod wheel (CC1).

### Swell

Enable **Record swell articulation** to record an extra set of notes in which aftertouch or a CC ramps up during the note. The swell is saved as a separate "<name> Swell" instrument. Set the start and end values, the delay before the ramp and the ramp time. The note is held at least delay + ramp + 0.5 s.

### Batch programs

Enable **Send Program Change** to record several synth programs in one run. Set the program range (1 to 128). Each program becomes its own instrument.

- **Bank MSB / LSB:** optional. -1 means "do not send".
- **Wait after program change:** time for the synth to load the program before the first note.

## Processing

On the **Process** tab:

- **Trim silence:** remove silence at the start and at the end. The thresholds come from the noise measurement. If start trimming is off, the **latency** setting shifts the start point relative to note-on.
- **Fades and DC:** fade in and fade out in milliseconds, and optional removal of DC offset.
- **Normalize:** off, each sample separately, or the whole instrument. Whole-instrument normalization keeps the loudness differences between velocity layers.
- **Root note:**
  - from the MIDI note that was sent,
  - from the real detected pitch,
  - from the real pitch with precise tuning.

  AutoSample always measures the real pitch of each sample. If it differs from the sent note, you get a warning. That usually means the synth is transposed (Octave or Transpose setting in the preset).
- **Auto loop:** finds loop points between the attack and the note-off, using zero crossings and the best correlation. Set the minimum loop length and the crossfade length.

## Export

On the **Export** tab:

- **Name:** the instrument name, used in file and folder names.
- **Output folder:** where the instrument is saved. The **…** button chooses it.
- **Naming pattern:** tokens `{name}`, `{note}`, `{midi}`, `{vel}`, `{rr}`, `{prog}`, `{expr}`, `{art}`. The example line shows the result.
- **Note names:** C3 = 60 (Ableton, Yamaha) or C4 = 60 (Roland, MIDI standard).
- **Formats:** SFZ (for Sforzando, TAL-Sampler, Bitwig, or import into Kontakt), DecentSampler (`.dspreset`), or both.

WAV files always contain the root note and loop points (smpl chunk), so samplers that read them pick the right pitch and loop.

Folder layout:

```
<output folder>/<name>/
    <name>_<note>_v<vel>_rr<rr>.wav   # samples
    <name>.sfz                        # SFZ mapping
    <name>.dspreset                   # DecentSampler mapping
```

With batch programs, each program gets its own subfolder `<name>_P001/`, `<name>_P002/` and so on. The swell instrument has its own mapping, named "<name> Swell".

The **Update SFZ / DS** button rewrites the mapping files from the samples already recorded, without recording again. **Open folder** opens the output folder.

## Auditioning, re-recording and deleting

The sample table lists every recorded sample: program, note, velocity, layer, round robin, detected pitch and length.

- Select one or more rows and press **▶ Play** (or **Space**) to listen.
- **⟳ Re-record** records the selected samples again.
- **✕ Delete** removes them after a confirmation.
- The same actions are in the right-click menu.

## Presets

**Save preset** and **Open preset** store all the settings in a file. Presets are kept in the `presets` folder inside the app's config folder: `%APPDATA%\AutoSample` on Windows, `~/AutoSample` on Linux. The last settings are restored automatically when you start the app.

## Hotkeys

- **Space:** play the selected sample.
- **Esc:** stop recording if it is running, otherwise stop playback.

## Language

Use the **Language** selector in the header of the main window to switch between English and Ukrainian. The window reloads in the new language right away; the choice is remembered. English is the default.

## Troubleshooting

**No signal, the level meter does not move.**
Check the audio cable from the synth's audio output to the interface input, the selected input channel, and the MIDI port and channel. Then press **Test note** again.

**ASIO: the synth is silent, or the card is busy.**
ASIO takes the sound card exclusively. If the monitoring output is another driver, nothing plays. Set the output to **Same as input (recommended)**.

**Warning: the synth sounds transposed.**
The real pitch of the recording differs from the MIDI note that was sent. Check the Octave or Transpose setting in the synth's preset. Or set the root note to **from the real pitch** so the sampler uses the measured pitch.

**Linux: the AppImage does not start.**
Make it executable with `chmod +x AutoSample-*.AppImage`. AppImages need FUSE. If FUSE is not available, run it with `./AutoSample-*.AppImage --appimage-extract-and-run`.
