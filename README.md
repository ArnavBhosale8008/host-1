# DroidPilot

**An advanced Android emulator desktop app with a built-in local AI assistant.**

DroidPilot is a cross-platform **desktop application** (PySide6/Qt) that wraps
Google's official Android Emulator and adds an AI control layer powered by a
**local, open-source model** (via [Ollama](https://ollama.com)) — no cloud API
keys required.

> **Why not a "BlueStacks for iOS"?** iOS cannot be legally emulated on a PC
> (proprietary, hardware-locked OS + DRM-signed apps). Android, however, is
> open source (AOSP), which is exactly what the official Android Emulator —
> and DroidPilot — build on.

## Features

- **Virtual device management** — create, start, and stop Android Virtual
  Devices (AVDs) from the desktop UI.
- **Live screen mirroring** — see the device screen in real time and interact
  with it (tap, swipe, type, hardware keys).
- **App management** — install / launch / uninstall APKs, capture screenshots,
  record the screen.
- **Built-in local AI** — type a natural-language goal ("open Settings and turn
  on airplane mode") and the agent drives the device for you, using the live UI
  hierarchy + a local LLM. Fully offline; degrades gracefully if no model is
  pulled.
- **Gaming controls** — "Optimize for games" launches the emulator with GPU
  acceleration and more RAM/cores, and a **key-mapping** system maps your
  keyboard/mouse to on-screen touches (a WASD movement stick + click-to-place
  action buttons). See [Playing games & key mapping](#playing-games--key-mapping).

## Requirements

- Python 3.10+
- The **Android SDK** with `platform-tools` and `emulator` (DroidPilot can help
  locate them; see `droidpilot doctor`).
- Hardware acceleration (KVM on Linux, HAXM/Hypervisor on Windows/macOS) for a
  usable emulator.
- *(Optional, for AI)* [Ollama](https://ollama.com) running locally with a
  vision-capable model such as `llama3.2-vision` or a text model such as
  `llama3.1`.

## Download (Windows)

A prebuilt `DroidPilot.exe` is published on the
[Releases page](https://github.com/ArnavBhosale8008/host-1/releases) (built by
the [`Build Windows executable`](.github/workflows/build-windows.yml) workflow).
It is the **control app only** (~tens of MB). On first run:

1. Enable hardware virtualization on your PC (BIOS "Intel VT-x / AMD-V", plus
   Windows "Windows Hypervisor Platform"). Without it the emulator can't run.
2. Install the Android SDK + a Play Store system image + an AVD in one command:
   ```
   DroidPilot.exe setup
   ```
   (or, from source, `droidpilot setup`). This downloads Google's command-line
   tools and installs `platform-tools`, `emulator`, an Android 14 **Play Store**
   image, and creates an AVD named `droidpilot`.
3. Launch `DroidPilot.exe`, pick the AVD, and press **Start**.

> **Note on games:** the in-app mirror refreshes a few times per second — great
> for the AI assistant, but for smooth gameplay tick **"Show native emulator
> window"** before pressing Start to use the emulator's own hardware-accelerated
> window. Heavy 3D games need a capable GPU.

## Install (from source)

```bash
pip install -e .
```

## Run

```bash
droidpilot            # launch the desktop app
droidpilot doctor     # check your environment (SDK, adb, emulator, Ollama)
droidpilot setup      # download the Android SDK + Play Store image + create an AVD
```

## Playing games & key mapping

In the **Game controls** panel:

1. **Optimize for games (GPU + more RAM)** — launches the emulator with
   `-gpu host` (hardware GPU), `-memory 4096`, and `-cores 4`. For the smoothest
   experience also tick **"Show native emulator window"** so you play in the
   emulator's own accelerated window rather than the in-app mirror.
2. **Enable key mapping (keyboard → touch)** — turns your keyboard into touch
   input. The default map is a **WASD movement stick** plus `J` (fire), `Space`
   (jump), `R` (reload), `F` (action).
3. **Edit keys** — click **Edit keys**, choose *Button* or *Move stick (WASD)*
   in the dropdown, then click on the screen where it should go. Buttons prompt
   for a key (e.g. `J`, `SPACE`). Bindings are stored as fractions of the screen
   so they survive resolution changes, and are saved automatically (Save/Load
   let you keep per-game layouts).

Under the hood the movement stick holds a single touch (`input motionevent`
DOWN/MOVE/UP) that follows your keys, and buttons fire `input tap`.

### Honest limitations (please read)

- **BGMI / Free Fire / other competitive shooters have emulator-detecting
  anti-cheat.** On a self-built emulator like this they will typically refuse to
  run, place you in emulator-only lobbies, or risk a ban. This is a policy/DRM
  limitation, not a bug — DroidPilot does **not** attempt to defeat anti-cheat
  (that would violate those games' terms of service). Casual and less-protected
  games work best.
- **Input latency.** Key/touch events go through `adb`, which adds tens of
  milliseconds per event — fine for many games, but not twitch-competitive.
- **The Play Store image is required** to install those games; run
  `DroidPilot.exe setup` (it installs a Play-Store-enabled Android 14 image).
- **Performance depends on your PC's GPU/CPU** and on hardware virtualization
  being enabled.

## Configuration

DroidPilot reads settings from environment variables and an optional
`~/.config/droidpilot/config.toml`. Key variables:

| Variable | Meaning | Default |
| --- | --- | --- |
| `ANDROID_HOME` / `ANDROID_SDK_ROOT` | Android SDK location | auto-detected |
| `DROIDPILOT_OLLAMA_HOST` | Ollama server URL | `http://127.0.0.1:11434` |
| `DROIDPILOT_OLLAMA_MODEL` | Local model name | `llama3.1` |

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## Project layout

```
droidpilot/
  core/     SDK discovery, ADB wrapper, emulator control, key mapping
  ai/       Local (Ollama) AI agent + prompts
  gui/      PySide6 desktop UI (main window, live screen view)
tests/      Unit tests
```
