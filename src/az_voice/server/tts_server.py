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

# Default model cache directory
_DEFAULT_CACHE_DIR = str(Path.home() / ".az-voice" / "models")


# ── Engine manager (lazy-load, singleton) ─────────────────────────────────────

class _EngineManager:
    """Lazy-loads VoxCPM2Engine on first request, reuses across calls.
    
    Tracks model download progress for WebUI status display.
    """

    MODEL_NAME = "openbmb/VoxCPM2"

    def __init__(self, device: str = "cuda:0", cache_dir: Optional[str] = None):
        self.device = device
        self.cache_dir = cache_dir
        self._engine = None
        self._loading = False
        self._lock = asyncio.Lock()
        # Download progress tracking
        self._download_progress = None  # dict with status, message, percent
        self._check_model_cached()

    def _check_model_cached(self):
        """Check if model is already cached locally."""
        import os
        base = self.cache_dir or _DEFAULT_CACHE_DIR
        
        # Check for HuggingFace cache
        model_dir = os.path.join(base, "models--openbmb--VoxCPM2")
        if os.path.isdir(model_dir):
            self._download_progress = {"status": "cached", "message": "Model files cached · Will load on first request", "percent": 90}
        else:
            self._download_progress = {"status": "pending", "message": "Model not cached - will download on first request", "percent": 0}

    @property
    def download_progress(self):
        """Get current download progress for WebUI status."""
        return self._download_progress or {"status": "unknown", "message": "", "percent": 0}

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
        """Blocking model load (runs in executor). Tracks download progress."""
        from az_voice.tts.voxcpm2 import VoxCPM2Engine

        self._download_progress = {"status": "loading", "message": "Loading VoxCPM2 model...", "percent": 10}
        logger.info("Loading VoxCPM2 model (first request, may download)...")

        self._engine = VoxCPM2Engine(
            model_name=self.MODEL_NAME,
            device=self.device,
            cache_dir=self.cache_dir or _DEFAULT_CACHE_DIR,
        )

        self._download_progress = {"status": "loading", "message": "Initializing model on %s..." % self.device, "percent": 50}
        self._engine.load_model()
        logger.info("VoxCPM2 engine loaded on %s", self.device)
        # Mark ready AFTER engine is fully loaded
        self._download_progress = {"status": "ready", "message": "Model ready on %s" % self.device, "percent": 100}


# WebUI static files path
_WEBUI_DIR = Path(__file__).parent / 'webui'

engine_manager: Optional[_EngineManager] = None


# ── API handlers ──────────────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint with model download progress."""
    if not engine_manager:
        return web.json_response({
            "status": "ok",
            "model_loaded": False,
            "device": "not configured",
            "model_progress": {"status": "unknown", "message": "", "percent": 0},
        })
    
    loaded = engine_manager.engine is not None
    progress = engine_manager.download_progress
    return web.json_response({
        "status": "ok",
        "model_loaded": loaded,
        "device": engine_manager.device,
        "model_progress": progress,
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
    """Create the aiohttp web application with WebUI and API endpoints."""
    global engine_manager
    engine_manager = _EngineManager(device=device, cache_dir=cache_dir)

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_post("/v1/audio/speech", handle_speech)
    app.router.add_post("/audio/speech", handle_speech)

    # Serve WebUI static files
    if _WEBUI_DIR.exists():
        async def _serve_index(request):
            idx = _WEBUI_DIR / "index.html"
            if idx.exists():
                return web.FileResponse(idx)
            return web.Response(status=404)
        # Root handler MUST be added before static route (aiohttp matches first)
        app.router.add_get("/", _serve_index)
        app.router.add_static("/", str(_WEBUI_DIR), name="webui")
        logger.info("WebUI served at root path /")

    return app


# ── CLI entry point with subcommand support ───────────────────────────────────

def _start_background_download(engine_mgr):
    """Start model download in background if not cached."""
    import os
    
    base = engine_mgr.cache_dir or _DEFAULT_CACHE_DIR
    
    model_dir = os.path.join(base, "models--openbmb--VoxCPM2")
    
    if os.path.isdir(model_dir):
        logger.info("Model already cached: %s", model_dir)
        engine_mgr._download_progress = {"status": "cached", "message": "Model files cached · Will load on first request", "percent": 90}
        return
    
    async def _download_task():
        engine_mgr._download_progress = {"status": "downloading", "message": "Downloading VoxCPM2 model...", "percent": 0}
        logger.info("=" * 60)
        logger.info("Downloading VoxCPM2 model...")
        logger.info("Cache directory: %s", base)
        logger.info("=" * 60)
        
        try:
            from huggingface_hub import snapshot_download
            
            # Run blocking download in thread executor so event loop stays responsive
            def _do_download():
                engine_mgr._download_progress = {"status": "downloading", "message": "Downloading model files...", "percent": 30}
                snapshot_download(
                    repo_id="openbmb/VoxCPM2",
                    cache_dir=base,
                )
                engine_mgr._download_progress = {"status": "downloading", "message": "Finalizing download...", "percent": 80}
            
            await asyncio.get_event_loop().run_in_executor(None, _do_download)
            
            engine_mgr._download_progress = {"status": "cached", "message": "Download complete · Will load on first request", "percent": 90}
            logger.info("Model download complete!")
            
        except ImportError:
            engine_mgr._download_progress = {"status": "pending", "message": "huggingface_hub not installed. Model will download on first request.", "percent": 0}
            logger.warning("huggingface_hub not installed. Model will download on first request.")
            logger.warning("Install with: pip install huggingface_hub")
        except Exception as e:
            engine_mgr._download_progress = {"status": "error", "message": f"Download failed: {e}", "percent": 0}
            logger.error("Model download failed: %s", e)
    
    # Return the coroutine for the caller to schedule
    return _download_task()


def _serve_command(args):
    """Handle the 'serve' subcommand."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = create_app(device=args.device, cache_dir=args.cache_dir)
    
    # Schedule background download via aiohttp on_startup (event loop is running)
    async def _on_startup(app):
        try:
            task = _start_background_download(engine_manager)
            if task:
                asyncio.get_event_loop().create_task(task)
        except Exception as e:
            logger.error("Failed to start background download: %s", e)

    app.on_startup.append(_on_startup)

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
    serve_parser.add_argument("--cache-dir", default=None, help=f"Model cache directory (default: ~{_DEFAULT_CACHE_DIR})")

    args = parser.parse_args()

    if args.command == "serve":
        _serve_command(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
