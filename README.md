# az-voice (in progress)

Text preprocessing, TTS, and ASR toolkit for English and Chinese.

Supports [VoxCPM2](https://github.com/OpenBMB/VoxCPM) and [Higgs Audio v3 TTS](https://huggingface.co/bosonai/higgs-audio-v3-tts-4b).

## Setup

### macOS (Apple Silicon)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

## Run Tests

```bash
pytest tests/utils/ -v
```

## Install from GitHub

```bash
pip install "az-voice @ git+https://github.com/xhinker/az-voice.git"
```
