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

## Requirements

- Python 3.10+
- The **Android SDK** with `platform-tools` and `emulator` (DroidPilot can help
  locate them; see `droidpilot doctor`).
- Hardware acceleration (KVM on Linux, HAXM/Hypervisor on Windows/macOS) for a
  usable emulator.
- *(Optional, for AI)* [Ollama](https://ollama.com) running locally with a
  vision-capable model such as `llama3.2-vision` or a text model such as
  `llama3.1`.

## Install

```bash
pip install -e .
```

## Run

```bash
droidpilot            # launch the desktop app
droidpilot doctor     # check your environment (SDK, adb, emulator, Ollama)
```

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
  core/     SDK discovery, ADB wrapper, emulator process control
  ai/       Local (Ollama) AI agent + prompts
  gui/      PySide6 desktop UI (main window, live screen view)
tests/      Unit tests
```
