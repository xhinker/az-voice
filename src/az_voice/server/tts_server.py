"""OpenAI-compatible TTS API server powered by VoxCPM2.

Usage:
    az-voice serve --port 8766 --device cuda:0

API endpoints (OpenAI-compatible):
    POST /v1/audio/speech      - Generate speech from text
    GET  /v1/models             - List available models
    GET  /health                - Health check
"""

import asyncio
import io
import json
import logging
import sys
import textwrap
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

# ── Model registry ────────────────────────────────────────────────────────────

MODELS = [
    {
        "id": "voxcpm2",
        "object": "model",
        "created": 2026,
        "owned_by": "openbmb",
    },
]

DEFAULT_MODEL = "voxcpm2"
DEFAULT_DEVICE = "cuda:0"
DEFAULT_PORT = 8766


# ── Engine manager (lazy-load, singleton) ─────────────────────────────────────

class _EngineManager:
    """Lazy-loads VoxCPM2Engine on first request, reuses across calls."""

    def __init__(self, device: str = "cuda:0", cache_dir: Optional[str] = None):
        self.device = device
        self.cache_dir = cache_dir
        self._engine = None
        self._loading = False
        self._lock = asyncio.Lock()

    @property
    def engine(self):
        return self._engine

    async def get_engine(self):
        """Get or load the engine. Thread-safe lazy initialization."""
        if self._engine is not None:
            return self._engine

        async with self._lock:
            if self._engine is not None:
                return self._engine

            if self._loading:
                while self._engine is None:
                    await asyncio.sleep(0.1)
                return self._engine

            self._loading = True
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._load_sync)
                return self._engine
            finally:
                self._loading = False

    def _load_sync(self):
        """Blocking model load (runs in executor)."""
        from az_voice.tts.voxcpm2 import VoxCPM2Engine

        self._engine = VoxCPM2Engine(
            model_name="openbmb/VoxCPM2",
            device=self.device,
            cache_dir=self.cache_dir,
        )
        self._engine.load_model()
        logger.info("VoxCPM2 engine loaded on %s", self.device)


engine_manager: Optional[_EngineManager] = None


# ── API handlers ──────────────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    loaded = engine_manager.engine is not None if engine_manager else False
    return web.json_response({
        "status": "ok",
        "model_loaded": loaded,
        "device": engine_manager.device if engine_manager else "not configured",
    })


async def handle_models(request: web.Request) -> web.Response:
    """List available models (OpenAI-compatible)."""
    return web.json_response({"object": "list", "data": MODELS})


async def handle_speech(request: web.Request) -> web.Response:
    """Generate speech from text (OpenAI-compatible POST /v1/audio/speech).

    Request body (JSON):
        model: str       - Model ID (default: "voxcpm2")
        input: str       - Text to synthesize (required)
        voice: str       - Voice identifier (ignored, VoxCPM2 uses reference_wav)
        response_format: str - Output format: "mp3" (default), "wav", "flac", "opus"
        speed: float     - Speed multiplier (0.25-4.0, default: 1.0)

    Optional (VoxCPM2-specific, passed as extra JSON fields):
        reference_wav: str    - Path to reference audio for cloning
        reference_text: str   - Transcript of reference audio
        control_instruction: str - Style control instruction
        cfg_value: float      - Classifier-free guidance (default: 2.0)
        inference_timesteps: int - Diffusion steps (default: 10)
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response(
            {"error": {"message": "Invalid JSON", "type": "invalid_request_error"}},
            status=400,
        )

    text = body.get("input")
    if not text or not isinstance(text, str):
        return web.json_response(
            {"error": {"message": "'input' is required and must be a non-empty string",
                        "type": "invalid_request_error"}},
            status=400,
        )

    model = body.get("model", DEFAULT_MODEL)
    response_format = body.get("response_format", "mp3")
    speed = float(body.get("speed", 1.0))

    reference_wav = body.get("reference_wav")
    reference_text = body.get("reference_text")
    control_instruction = body.get("control_instruction")
    cfg_value = float(body.get("cfg_value", 2.0))
    inference_timesteps = int(body.get("inference_timesteps", 10))

    model_ids = {m["id"] for m in MODELS}
    if model not in model_ids:
        return web.json_response(
            {"error": {"message": f"Model '{model}' not found. Available: {list(model_ids)}",
                        "type": "invalid_request_error"}},
            status=400,
        )

    if response_format not in ("mp3", "wav", "flac", "opus"):
        return web.json_response(
            {"error": {"message": f"Unsupported format: '{response_format}'. Use mp3, wav, flac, or opus.",
                        "type": "invalid_request_error"}},
            status=400,
        )

    if not (0.25 <= speed <= 4.0):
        return web.json_response(
            {"error": {"message": "Speed must be between 0.25 and 4.0",
                        "type": "invalid_request_error"}},
            status=400,
        )

    try:
        engine = await engine_manager.get_engine()
    except Exception as exc:
        logger.error("Failed to load engine: %s", exc)
        return web.json_response(
            {"error": {"message": f"Model load failed: {exc}", "type": "server_error"}},
            status=503,
        )

    try:
        wav, sample_rate = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: engine.generate(
                text=text,
                reference_wav=reference_wav,
                reference_text=reference_text,
                control_instruction=control_instruction,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
            ),
        )

        audio_bytes = _encode_audio(wav, sample_rate, response_format, speed)

        content_types = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "flac": "audio/flac",
            "opus": "audio/opus",
        }

        return web.Response(
            body=audio_bytes,
            content_type=content_types.get(response_format, "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="speech.{response_format}"',
                "X-Audio-Duration": f"{len(wav) / sample_rate:.2f}",
            },
        )

    except ValueError as exc:
        return web.json_response(
            {"error": {"message": str(exc), "type": "invalid_request_error"}},
            status=400,
        )
    except Exception as exc:
        logger.error("TTS generation failed: %s", exc, exc_info=True)
        return web.json_response(
            {"error": {"message": f"Generation failed: {exc}", "type": "server_error"}},
            status=500,
        )


# ── Audio encoding ────────────────────────────────────────────────────────────

def _encode_audio(
    wav: "numpy.ndarray",
    sample_rate: int,
    format: str,
    speed: float = 1.0,
) -> bytes:
    """Encode numpy audio array to the requested format."""
    import numpy as np
    import soundfile as sf

    if speed != 1.0:
        target_sr = int(sample_rate * speed)
        try:
            from scipy.signal import resample
            num_samples = int(len(wav) / speed)
            wav = resample(wav, num_samples)
            sample_rate = target_sr
        except ImportError:
            logger.warning("scipy not installed; speed change skipped. Install with: pip install scipy")

    buf = io.BytesIO()

    if format == "wav":
        sf.write(buf, wav, sample_rate, format="WAV")
    elif format == "flac":
        sf.write(buf, wav, sample_rate, format="FLAC")
    elif format == "mp3":
        try:
            from pydub import AudioSegment
            audio = AudioSegment(
                data=(wav * 32767).astype(np.int16).tobytes(),
                sample_width=2,
                frame_rate=sample_rate,
                channels=1,
            )
            audio.export(buf, format="mp3")
        except ImportError:
            logger.warning("pydub not installed; returning WAV as MP3. Install with: pip install pydub")
            sf.write(buf, wav, sample_rate, format="WAV")
    elif format == "opus":
        logger.warning("Opus encoding not directly supported; returning WAV. Consider: pip install pydub")
        sf.write(buf, wav, sample_rate, format="WAV")
    else:
        sf.write(buf, wav, sample_rate, format="WAV")

    return buf.getvalue()


# ── App factory ───────────────────────────────────────────────────────────────

def create_app(device: str = "cuda:0", cache_dir: Optional[str] = None) -> web.Application:
    """Create the aiohttp web application."""
    global engine_manager
    engine_manager = _EngineManager(device=device, cache_dir=cache_dir)

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_post("/v1/audio/speech", handle_speech)
    app.router.add_post("/audio/speech", handle_speech)

    return app


# ── CLI entry point with subcommand support ───────────────────────────────────

def _serve_command(args):
    """Handle the 'serve' subcommand."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = create_app(device=args.device, cache_dir=args.cache_dir)

    logger.info("Starting az-voice TTS server on %s:%s", args.host, args.port)
    logger.info("Health check: http://%s:%s/health", args.host, args.port)
    logger.info("Models list:  http://%s:%s/v1/models", args.host, args.port)
    logger.info("TTS endpoint: POST http://%s:%s/v1/audio/speech", args.host, args.port)

    web.run_app(app, host=args.host, port=args.port, print=None)


def main():
    """CLI entry point: az-voice serve"""
    import argparse

    parser = argparse.ArgumentParser(
        prog="az-voice",
        description="az-voice: Text preprocessing, TTS, and ASR toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'serve' subcommand
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start OpenAI-compatible TTS API server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              az-voice serve                      # Start on port 8766, cuda:0
              az-voice serve --port 8080          # Custom port
              az-voice serve --device cuda:1      # Use second GPU
              az-voice serve --host 0.0.0.0       # Listen on all interfaces

            API usage (OpenAI-compatible):
              curl http://localhost:8766/v1/audio/speech \\
                -H "Content-Type: application/json" \\
                -d '{
                  "model": "voxcpm2",
                  "input": "Hello, this is a test.",
                  "response_format": "mp3"
                }' -o speech.mp3
        """),
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
    serve_parser.add_argument("--device", default=DEFAULT_DEVICE, help=f"GPU device (default: {DEFAULT_DEVICE})")
    serve_parser.add_argument("--cache-dir", default=None, help="Model cache directory")

    args = parser.parse_args()

    if args.command == "serve":
        _serve_command(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
