# Cite-GPT: Talk To Your Zotero Library

Foundational Python project that wires together a desktop toggle UI, OpenAI audio transcription, and PyZotero search hooks. The current implementation provides ready-to-extend service classes and a Tkinter window with an on/off switch so you can begin iterating quickly.

## Features
- Tkinter window with an on/off switch, rolling log output, live transcript preview, and a mic activity meter
- Natural-language intent parsing backed by an OpenAI text model that maps phrases like "find Zimmerman papers" to structured Zotero filters
- Interactive item picker so you can choose which Zotero record to open when several match
- Controller skeleton that links audio capture, OpenAI transcription (forced to English), and Zotero queries
- Microphone capture powered by `sounddevice`/`soundfile`, configurable via env vars and observable via the GUI meter
- PyZotero client that can open PDFs or citation URLs plus a CLI-only search mode
- Toggle between the cloud API and the local Zotero connector; the CLI prints which target is active
- `.env` loading via `python-dotenv` for API keys and library metadata

## Requirements
- Python 3.11+
- OpenAI API key with access to audio models
- Zotero API key plus your library id/type (user or group)

## Getting Started
1. Create a virtual environment and install dependencies:
   ```pwsh
   cd zotero_voice_assistant
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -e .
   ```
2. Copy the example environment file and populate credentials:
   ```pwsh
   Copy-Item .env.example .env
   ```
3. Launch the GUI:
   ```pwsh
   python -m zotero_voice_assistant.main
   ```

## CLI Zotero Search
You can exercise the Zotero portion without recording audio via the bundled CLI:

```pwsh
zva search --author "smith" --title quantum --year 2022 --limit 10
```

Add `--raw` to dump the raw JSON returned by the Zotero API for debugging.

Each invocation prints whether you're hitting the local Zotero connector or the hosted web API so you can confirm the environment matches your expectation.

Need to discover the correct `AUDIO_INPUT_DEVICE`? List every PortAudio device via:

```pwsh
zva audio-devices
```

Use the displayed index (e.g., `[2]`) or the exact name in your `.env`.

## Configuring Zotero Access
- Set `ZOTERO_LIBRARY_ID` and `ZOTERO_LIBRARY_TYPE` (`user` or `group`) in `.env`.
- Provide `ZOTERO_API_KEY` when using the cloud API.
- Flip `ZOTERO_USE_LOCAL=true` (or legacy `ZOTERO_LOCAL_BOOL=1`) to route traffic through the local Zotero connector; no API key is required in that case, but the desktop app must be open.

## Audio Settings
The GUI now records microphone snippets via `sounddevice`. Control the capture behavior with:

- `AUDIO_SAMPLE_RATE` (default `16000`)
- `AUDIO_CHANNELS` (default `1`)
- `AUDIO_INPUT_DEVICE` (optional exact device name or device index from `zva audio-devices`)
- `AUDIO_DEFAULT_DURATION` (seconds per snippet, default `5`)

Set `OPENAI_TEXT_MODEL` if you prefer a different reasoning model for natural-language parsing, and `OPENAI_TRANSCRIPTION_LANGUAGE` (default `en`) to force transcription into a specific language.

## Audio Capture Options
`AudioCaptureService` defaults to `sounddevice` + `soundfile`, but you can swap in other tooling if needed:

- `sounddevice`: lightweight wrapper over PortAudio with NumPy buffers; great for short pulls. Record to WAV via `soundfile`.
- `pyaudio`: mature PortAudio bindings, especially if you already know its callback model.
- `pydub`/`ffmpeg`: handy when you need format conversion before sending to OpenAI.
- OS-specific backends (CoreAudio via `av`, WASAPI via `soundcard`) if you need loopback/virtual devices.

Whichever library you pick, write captured frames to a temporary WAV/MP3 file that `OpenAIAudioClient.transcribe_file` can consume, then return the path from `record_snippet`.

