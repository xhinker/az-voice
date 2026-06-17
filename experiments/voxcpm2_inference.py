"""VoxCPM2 inference demo for Linux (GPU required).

Prerequisites:
    pip install voxcpm>=2.0 torch torchaudio soundfile

Usage:
    # Basic TTS
    python experiments/voxcpm2_inference.py --text "Hello, this is a test of VoxCPM2."

    # Voice design (no reference audio needed)
    python experiments/voxcpm2_inference.py \\
        --text "(A young woman, gentle voice) Hello there!"

    # Voice cloning from reference audio
    python experiments/voxcpm2_inference.py \\
        --text "This is a cloned voice speaking." \\
        --reference-wav path/to/speaker.wav

Requirements:
    - NVIDIA GPU with at least 8GB VRAM (model loads in ~4-5 GB bf16)
    - Linux/Ubuntu recommended for CUDA support
"""

import argparse
from pathlib import Path

import soundfile as sf


def main():
    parser = argparse.ArgumentParser(description="VoxCPM2 inference demo")
    parser.add_argument("--text", type=str, required=True, help="Text to synthesize (can include voice design in parentheses)")
    parser.add_argument("--reference-wav", type=str, default=None, help="Path to reference audio for cloning")
    parser.add_argument("--prompt-text", type=str, default=None, help="Transcript of the reference audio (for ultimate cloning)")
    parser.add_argument("--output", "-o", type=str, default="voxcpm2_output.wav", help="Output WAV file path")
    parser.add_argument("--model-name", type=str, default="openbmb/VoxCPM2", help="Model name or local path")
    parser.add_argument("--cfg-value", type=float, default=2.0, help="Classifier-free guidance scale (higher = more expressive)")
    parser.add_argument("--inference-timesteps", type=int, default=10, help="Diffusion steps (fewer = faster, 7-15 recommended)")
    args = parser.parse_args()

    print(f"Loading model: {args.model_name}")
    from voxcpm import VoxCPM
    model = VoxCPM.from_pretrained(args.model_name, load_denoiser=False)

    kwargs = {
        "text": args.text,
        "cfg_value": args.cfg_value,
        "inference_timesteps": args.inference_timesteps,
    }
    if args.reference_wav:
        kwargs["reference_wav_path"] = args.reference_wav
        print(f"Using reference audio: {args.reference_wav}")
    if args.prompt_text:
        kwargs["prompt_text"] = args.prompt_text

    print(f"\nSynthesizing ({len(args.text)} chars)...")
    wav = model.generate(**kwargs)

    out_path = Path(args.output)
    sf.write(str(out_path), wav, model.tts_model.sample_rate)
    duration = len(wav) / model.tts_model.sample_rate
    print(f"Saved: {out_path} ({duration:.1f}s audio, {out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
