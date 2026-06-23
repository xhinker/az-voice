"""Example: Call the az-voice TTS API server to generate audio from text.

Prerequisites:
    1. Start the server in another terminal:
       az-voice serve --port 8766 --device cuda:1

    2. Run this example:
       python examples/tts_api_example.py

    3. Or with custom text:
       python examples/tts_api_example.py --text "Hello, this is a test." --output outputs/hello.mp3
"""

import argparse
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8766"


def check_health():
    """Check if the server is running."""
    resp = requests.get(f"{BASE_URL}/health")
    resp.raise_for_status()
    info = resp.json()
    print(f"Server status: {info['status']}")
    print(f"Model loaded: {info['model_loaded']}")
    print(f"Device: {info['device']}")
    return info


def list_models():
    """List available models."""
    resp = requests.get(f"{BASE_URL}/v1/models")
    resp.raise_for_status()
    data = resp.json()
    print("\nAvailable models:")
    for m in data["data"]:
        print(f"  - {m['id']} (owned by {m['owned_by']})")
    return data


def generate_speech(
    text: str,
    output_path: str = "speech.mp3",
    model: str = "voxcpm2",
    response_format: str = "mp3",
    speed: float = 1.0,
    control_instruction: str = None,
    reference_wav: str = None,
    reference_text: str = None,
):
    """Generate speech from text using the TTS API.

    Args:
        text: Text to synthesize.
        output_path: Path to save the audio file.
        model: Model ID (default: voxcpm2).
        response_format: Output format: mp3, wav, flac, opus.
        speed: Speed multiplier (0.25-4.0).
        control_instruction: Voice style control (e.g., "speaking slowly").
        reference_wav: Path to reference audio for cloning.
        reference_text: Transcript of reference audio.

    Returns:
        Path to the saved audio file.
    """
    payload = {
        "model": model,
        "input": text,
        "response_format": response_format,
        "speed": speed,
    }

    # Optional VoxCPM2-specific params
    if control_instruction:
        payload["control_instruction"] = control_instruction
    if reference_wav:
        payload["reference_wav"] = reference_wav
    if reference_text:
        payload["reference_text"] = reference_text

    print(f"\nGenerating speech...")
    print(f"  Text: {text[:80]}{'...' if len(text) > 80 else ''}")
    print(f"  Format: {response_format}")
    print(f"  Speed: {speed}x")
    if control_instruction:
        print(f"  Style: {control_instruction}")

    start = time.time()
    resp = requests.post(
        f"{BASE_URL}/v1/audio/speech",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()

    duration = time.time() - start

    # Save audio
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)

    audio_duration = resp.headers.get("X-Audio-Duration", "?")
    print(f"\n  Saved: {out} ({out.stat().st_size / 1024:.1f} KB)")
    print(f"  Audio duration: {audio_duration}s")
    print(f"  Generation time: {duration:.1f}s")

    return out


def main():
    parser = argparse.ArgumentParser(description="az-voice TTS API example")
    parser.add_argument(
        "--text",
        default="Hello! This is a test of the az-voice text-to-speech API. "
                "It supports both English and Chinese synthesis.",
        help="Text to synthesize",
    )
    parser.add_argument("--output", default="outputs/speech.mp3", help="Output file path")
    parser.add_argument("--format", choices=["mp3", "wav", "flac", "opus"], default="mp3")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed (0.25-4.0)")
    parser.add_argument(
        "--style",
        default=None,
        help='Style control (e.g., "speaking slowly, happy tone")',
    )
    parser.add_argument("--list-models", action="store_true", help="List models and exit")
    args = parser.parse_args()

    # Check server
    print("=" * 60)
    print("az-voice TTS API Example")
    print("=" * 60)

    info = check_health()
    if not info.get("model_loaded"):
        print("\nNote: Model not loaded yet. First request will trigger loading...")

    if args.list_models:
        list_models()
        return

    # Generate speech
    generate_speech(
        text=args.text,
        output_path=args.output,
        response_format=args.format,
        speed=args.speed,
        control_instruction=args.style,
    )

    print("\nDone! Play with: mpv", args.output)


if __name__ == "__main__":
    main()
