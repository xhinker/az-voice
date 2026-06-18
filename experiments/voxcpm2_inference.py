"""VoxCPM2 inference script - voice design, cloning, and long-form generation.

Prerequisites:
    pip install voxcpm>=2.0 torch torchaudio soundfile

Usage:
    # Basic TTS on RTX 3090 (cuda:1)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py --text "Hello, this is a test of VoxCPM2."

    # Voice design (no reference audio needed)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py \\
        --text "(A young woman, gentle voice) Hello there!"

    # Voice cloning from reference audio + transcript
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py \
        --text "This is a cloned voice speaking." \
        --reference-wav /home/andrewzhu/storage_1t_1/az_git_folder/az_samples/ai_models_eval/voice_models/qwen3-tts/role_voices/female_ch_1.wav \
        --reference-text "今夜的月光如此清亮，不做些什么真是浪费。随我一同去月下漫步吧，不许拒绝。" 

Requirements:
    - NVIDIA GPU with at least 8GB VRAM (model loads in ~4-5 GB bf16)
    - Linux/Ubuntu recommended for CUDA support
"""

import argparse
import os
import tempfile
from pathlib import Path

import soundfile as sf


def generate_audio(
    text_input,
    output_wav_path="outputs/voxcpm2_output.wav",
    model_name="openbmb/VoxCPM2",
    device="cuda:0",
    reference_wav=None,
    reference_text=None,
    cfg_value=2.0,
    inference_timesteps=10,
    target_seconds=15.0,
    max_words=28,
):
    """Generate audio for text via chunking + synthesize + concatenate."""
    # Setup paths and cache location
    script_dir = Path(__file__).resolve().parent.parent
    os.environ["HF_HOME"] = str(script_dir / "models")

    # Ensure outputs directory exists
    if not output_wav_path.startswith("/"):  # Relative path
        outputs_dir = script_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        full_output_path = outputs_dir / Path(output_wav_path).name
    else:
        Path(output_wav_path).parent.mkdir(parents=True, exist_ok=True)
        full_output_path = Path(output_wav_path)

    # Load model once
    print(f"Loading {model_name} on {device}...")
    from voxcpm import VoxCPM
    model = VoxCPM.from_pretrained(
        model_name,
        load_denoiser=False,
        cache_dir=str(script_dir / "models"),
        device=device,
    )
    sample_rate = model.tts_model.sample_rate

    # Split text into chunks using our utility
    from az_voice.utils.text_chunker import split_text_for_tts
    segments = split_text_for_tts(text_input, max_words=max_words, target_seconds=target_seconds)
    if not segments:
        raise ValueError("No text segments to generate.")

    print(f"Text split into {len(segments)} segment(s):")
    for i, seg in enumerate(segments, 1):
        preview = seg[:70] + ("..." if len(seg) > 70 else "")
        chars = len(seg.replace(" ", ""))
        print(f"  [{i}/{len(segments)}] {chars} chars | {preview}")
    print()

    # Synthesize each chunk (model is already loaded in VRAM on configured device)
    chunk_paths = []
    for i, segment in enumerate(segments, start=1):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            chunk_path = tmp.name

        kwargs = {"text": segment, "cfg_value": cfg_value, "inference_timesteps": inference_timesteps}

        # VoxCPM requires prompt_wav_path and prompt_text together (or neither)
        if reference_wav is not None and reference_text is not None:
            kwargs["prompt_wav_path"] = reference_wav
            kwargs["prompt_text"] = reference_text
        elif reference_wav is not None:
            print("WARNING: reference_wav provided without reference_text — voice cloning requires both. Using as basic TTS instead.")

        print(f"  [{i}/{len(segments)}] Generating...")
        wav = model.generate(**kwargs)
        sf.write(chunk_path, wav, sample_rate)
        duration = len(wav) / sample_rate
        chunk_paths.append(chunk_path)
        print(f"    -> {duration:.1f}s audio saved to {chunk_path}")

    if not chunk_paths:
        raise RuntimeError("No audio chunks were generated successfully.")

    # Concatenate all chunks using our utility
    from az_voice.utils.audio_utils import concatenate_wavs
    concatenate_wavs(chunk_paths, str(full_output_path), sample_rate=sample_rate)

    import wave
    with wave.open(str(full_output_path), "rb") as wf:
        total_duration = wf.getnframes() / wf.getframerate()

    # Clean up chunk files
    for cp in chunk_paths:
        try:
            Path(cp).unlink()
        except OSError:
            pass

    return str(full_output_path), total_duration


def main():
    parser = argparse.ArgumentParser(description="VoxCPM2 inference script")
    parser.add_argument("--text", type=str, required=True, help="Text to synthesize (can include voice design in parentheses)")
    parser.add_argument("--device", type=str, default="cuda:0", help="Device to run on (default: cuda:0). Use CUDA_VISIBLE_DEVICES env var or change here.")
    parser.add_argument("--reference-wav", type=str, default=None, help="Path to reference audio for cloning")
    parser.add_argument("--reference-text", type=str, default=None, help="Transcript of reference audio (required when --reference-wav is provided)")
    parser.add_argument("--output", "-o", type=str, default="outputs/voxcpm2_output.wav", help="Output WAV file path")
    parser.add_argument("--model-name", type=str, default="openbmb/VoxCPM2", help="Model name or local path")
    parser.add_argument("--cfg-value", type=float, default=2.0, help="Classifier-free guidance scale (higher = more expressive)")
    parser.add_argument("--inference-timesteps", type=int, default=10, help="Diffusion steps (fewer = faster, 7-15 recommended)")
    args = parser.parse_args()

    wav_path, duration = generate_audio(
        text_input=args.text,
        output_wav_path=args.output,
        model_name=args.model_name,
        device=args.device,
        reference_wav=args.reference_wav,
        reference_text=args.reference_text,
        cfg_value=args.cfg_value,
        inference_timesteps=args.inference_timesteps,
    )

    print()
    print(f"Done! {duration:.1f}s audio saved to {wav_path}")


if __name__ == "__main__":
    main()
