# az-voice

Text-to-speech (TTS) toolkit powered by [VoxCPM2](https://github.com/OpenBMB/VoxCPM) with bilingual (English + Chinese) support. Includes a text splitter for long-form content, an OpenAI-compatible HTTP API, and a web UI for easy use.

## Features

- **Text splitter** — Splits long English or Chinese text into segments for TTS inference, respecting sentence boundaries and estimated speech duration. Handles CJK and Latin text with different speech rates.
- **Batch TTS** — Generate complete audio files (MP3, WAV, FLAC, Opus) from text with automatic chunking.
- **Streaming TTS** — Real-time audio streaming via Server-Sent Events (SSE) for low-latency playback.
- **Voice cloning** — Clone voices using reference audio with optional transcript for Hi-Fi quality.
- **OpenAI-compatible API** — Drop-in compatible with OpenAI's `/v1/audio/speech` endpoint.
- **Web UI** — Browser-based interface with dark theme, batch generation, and real-time streaming tabs.

## Quick Start

### 1. Install

```bash
git clone https://github.com/xhinker/az-voice.git
cd az-voice
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

### 2. Start the server

```bash
az-voice serve --port 8766 --device cuda:0 --host 0.0.0.0
```

- `--device`: Use `cuda:0` (or `cuda:1`, etc.) for GPU, `cpu` for CPU-only
- `--port`: Default is `8766`
- `--host`: Default is `127.0.0.1`; use `0.0.0.0` for remote access

The model downloads automatically on first request (~2 GB).

### 3. Use the Web UI

Open `http://localhost:8766` in your browser:

- **Generate tab** — Enter text, pick format (MP3/WAV/FLAC), adjust speed and style, download the result
- **Stream tab** — Enter text and hear audio play in real-time as it generates
- Both tabs support **reference audio** upload for voice cloning

### 4. Use the API

#### Batch generation

```bash
curl -X POST http://localhost:8766/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "voxcpm2",
    "input": "Hello! This is a test of az-voice text-to-speech.",
    "response_format": "mp3",
    "speed": 1.0
  }' \
  --output output.mp3
```

#### Streaming

```bash
curl -N -X POST http://localhost:8766/v1/audio/speech/stream \
  -H "Content-Type: application/json" \
  -d '{
    "model": "voxcpm2",
    "input": "Hello! This is a streaming demo."
  }'
```

Returns SSE events with base64-encoded raw PCM audio chunks.

#### Voice cloning

```bash
curl -X POST http://localhost:8766/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "voxcpm2",
    "input": "Hello, this is my cloned voice.",
    "reference_wav": "/path/to/reference.wav",
    "reference_text": "The transcript of the reference audio"
  }' \
  --output cloned.mp3
```

- `reference_wav`: Path to reference audio (or base64 data URI from WebUI)
- `reference_text`: Transcript of reference audio (required for Hi-Fi cloning)
- Without `reference_text`, style control is used instead

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/v1/audio/speech` | POST | Batch TTS generation |
| `/v1/audio/speech/stream` | POST | Streaming TTS via SSE |
| `/v1/models` | GET | List available models |
| `/health` | GET | Health check with model status |
| `/` | GET | Web UI |

### Batch request parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `model` | string | Yes | `"voxcpm2"` | Model identifier |
| `input` | string | Yes | — | Text to synthesize |
| `response_format` | string | No | `"mp3"` | `mp3`, `wav`, `flac`, `opus` |
| `speed` | float | No | `1.0` | Speech speed (0.25–2.0) |
| `reference_wav` | string | No | — | Path to reference audio |
| `reference_text` | string | No | — | Transcript of reference audio |
| `control_instruction` | string | No | — | Style control (e.g., `"speaking slowly, happy tone"`) |
| `cfg_value` | float | No | `2.0` | Classifier-free guidance scale |
| `inference_timesteps` | int | No | `10` | Diffusion steps (7–15) |

### Streaming request parameters

Same as batch, minus `response_format` and `speed` (streaming outputs raw PCM).

### Streaming response format

Server-Sent Events with three event types:

```
data: {"type": "metadata", "sample_rate": 24000, "encoding": "pcm_s16le", "channels": 1}

data: {"type": "audio", "chunk": 0, "data": "<base64 pcm data>"}

data: {"type": "done", "total_chunks": 42}
```

## Text Splitter

The built-in text splitter handles long text by:

1. **Sentence splitting** — Splits on terminal punctuation (`.!?。！？`)
2. **Duration estimation** — CJK: ~4 chars/sec, Latin: ~1.8 words/sec
3. **Sentence merging** — Groups sentences until target duration (~15s) is reached
4. **Oversized handling** — Splits long sentences at punctuation (terminal → weak → em dash)
5. **Segment closing** — Ensures each segment ends with proper terminal punctuation

Usage in Python:

```python
from az_voice.utils.text_chunker import split_text_for_tts

segments = split_text_for_tts(
    "Your long text here...",
    max_words=28,        # Hard cap on words per segment
    target_seconds=15.0, # Target audio duration per segment
)
```

## Project Structure

```
az-voice/
├── src/az_voice/
│   ├── server/
│   │   ├── tts_server.py      # HTTP API server (aiohttp)
│   │   └── webui/             # Web UI (HTML/CSS/JS)
│   ├── tts/
│   │   └── voxcpm2.py         # VoxCPM2 engine (batch + streaming)
│   ├── utils/
│   │   ├── text_chunker.py    # Bilingual text splitter
│   │   └── audio_utils.py     # PCM encoding, audio smoothing
│   └── asr/                   # Speech recognition (future)
└── tests/
    └── utils/                 # Unit tests
```

## Requirements

- Python 3.10+
- PyTorch with CUDA support (recommended for GPU)
- ~2 GB disk space for model weights
- ~8 GB VRAM for GPU inference

## License

Apache-2.0
