"""VoxCPM2 inference script - voice design, cloning, and long-form generation.

Prerequisites:
    pip install voxcpm>=2.0 torch torchaudio soundfile

Usage:
    # Basic TTS on RTX 3090 (cuda:1)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py --text "Hello, this is a test of VoxCPM2."

    # Voice design (no reference audio needed)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py \\
        --text "(A young woman, gentle voice) Hello there!"

    # Voice cloning from reference audio + transcript (requires BOTH ref_wav AND ref_text)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py \\
        --text "This is a cloned voice speaking using reference audio for maximum fidelity and natural prosody matching." \\
        --reference-wav /home/andrewzhu/storage_1t_1/az_git_folder/az_samples/ai_models_eval/voice_models/qwen3-tts/role_voices/female_ch_1.wav \\
        --reference-text "今夜的月光如此清亮，不做些什么真是浪费。随我一同去月下漫步吧，不许拒绝。"

    # Voice cloning with style/emotion control (no transcript required)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py \\
        --text "Hello, I can speak in different styles." \\
        --reference-wav path/to/speaker.wav \\
        --control "speaking slowly, happy tone"

    # Long Chinese text (splits into chunks automatically)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py \\
        --text "最后上来的是一个带蓝牙耳机的时髦女子，只见她袅袅娜娜地走到广告板前拿起笔来，在所有同事的回答之下又写了几个字：综上所述。贝贝立马惊了：太有才了！所有的人都殚思竭虑，企图找出最佳答案，可这位蓝牙女子轻轻巧巧的四个字便夺了头彩。这简直是太有水平了：既有点幽默，又有点闷骚的意味儿，叫人回味无穷禁不住拍案叫好。美眉们各自带着得意的神情，颇以自己的见解为傲，只等着杰克发言，期待他给大家来个精彩点评。" \\
        --reference-wav /home/andrewzhu/storage_1t_1/az_git_folder/az_samples/ai_models_eval/voice_models/qwen3-tts/role_voices/female_ch_1.wav \\
        --reference-text "今夜的月光如此清亮，不做些什么真是浪费。随我一同去月下漫步吧，不许拒绝。"

    # Long English text (splits into chunks automatically)
    CUDA_VISIBLE_DEVICES=1 python experiments/voxcpm2_inference.py \\
        --text "That was the night I discovered what Seven could not do. I sat at my kitchen table, staring at a blank document. The literary magazine wanted another story by Friday. Seven had already outlined three plot structures, generated five opening paragraphs, and prepared a bibliography of references. All I had to do was pick one and say go. But I could not. Not because I did not trust Seven's writing - it was good, maybe better than anything I'd ever produced. But because the story was not mine. The ideas were not mine. The desire to write them was not mine."

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
    control_instruction=None,
    cfg_value=2.0,
    inference_timesteps=10,
    target_seconds=15.0,
    max_words=28,
    voice_anchor_strength=None,
):
    """Generate audio for text via chunking + synthesize + concatenate."""
    # Setup paths and cache location
    script_dir = Path(__file__).resolve().parent.parent
    os.environ["HF_HOME"] = str(script_dir / "models")

    # Ensure outputs directory exists (always saves to repo/outputs/)
    outputs_dir = script_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    # Resolve output path: absolute paths stay as-is; relative paths go into outputs/
    out_path = Path(output_wav_path)
    if out_path.is_absolute():
        full_output_path = out_path
        full_output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        full_output_path = outputs_dir / out_path.name  # Just use filename to avoid double prepending

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
    seed_prompt_wav = None  # Fixed-seed anchor from first generated chunk
    
    for i, segment in enumerate(segments, start=1):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            chunk_path = tmp.name

        kwargs = {"text": segment, "cfg_value": cfg_value, "inference_timesteps": inference_timesteps}

        # VoxCPM requires prompt_wav_path and prompt_text together (or neither)
        if reference_wav is not None and reference_text is not None:
            kwargs["prompt_wav_path"] = reference_wav
            kwargs["prompt_text"] = reference_text
        
        # Fixed-seed continuation: use first generated chunk as prompt anchor for subsequent chunks (prevents re-entry instability)
        elif seed_prompt_wav is not None:
            kwargs["prompt_wav_path"] = seed_prompt_wav
            kwargs["prompt_text"] = segments[0]  # Use actual transcript of first segment, NOT control instruction
        
        # Apply voice anchor strength for long-form stability (blends reference latent features back during generation)
        if voice_anchor_strength is not None:
            kwargs["voice_anchor_strength"] = voice_anchor_strength
            print(f"  [Voice anchor strength: {voice_anchor_strength}]")
        
        elif reference_wav is not None:
            # Reference audio without transcript allows style control via text parentheses or --control
            if control_instruction is not None:
                segment_with_control = f"({control_instruction}){segment}"
                kwargs["text"] = segment_with_control
            kwargs["reference_wav_path"] = reference_wav

        print(f"  [{i}/{len(segments)}] Generating...")
        wav = model.generate(**kwargs)
        sf.write(chunk_path, wav, sample_rate)
        
        # Fixed-seed chunking: after first chunk, use it as stable prompt anchor for subsequent chunks (prevents drift)
        if i == 1 and len(segments) > 1:
            seed_prompt_wav = chunk_path

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

    # Clean up chunk files (keep seed prompt if needed for debugging)
    for cp in chunk_paths[1:] if len(chunk_paths) > 1 else chunk_paths:  # Keep first chunk for reference
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
    parser.add_argument("--control", type=str, default=None, help="Voice design/style control instruction (e.g., 'speaking slowly, happy tone'). Cannot be used with --reference-text.")
    parser.add_argument("--output", "-o", type=str, default="outputs/voxcpm2_output.wav", help="Output WAV file path")
    parser.add_argument("--model-name", type=str, default="openbmb/VoxCPM2", help="Model name or local path")
    parser.add_argument("--cfg-value", type=float, default=2.0, help="Classifier-free guidance scale (higher = more expressive)")
    parser.add_argument("--inference-timesteps", type=int, default=10, help="Diffusion steps (fewer = faster, 7-15 recommended)")
    parser.add_argument("--voice-anchor-strength", type=float, default=None, help="Voice anchor strength for long-form stability (0.0-1.0). Higher values stabilize speaker identity but may reduce expressiveness.")
    args = parser.parse_args()

    # Validate: --control cannot be used with --reference-text  
    if args.control is not None and args.reference_text is not None:
        print("ERROR: --control cannot be used together with --reference-text. Use either style control OR Hi-Fi cloning with transcript, but not both.")
        return

    wav_path, duration = generate_audio(
        text_input=args.text,
        output_wav_path=args.output,
        model_name=args.model_name,
        device=args.device,
        reference_wav=args.reference_wav,
        reference_text=args.reference_text,
        control_instruction=args.control,
        cfg_value=args.cfg_value,
        inference_timesteps=args.inference_timesteps,
        voice_anchor_strength=args.voice_anchor_strength,
    )

    print()
    print(f"Done! {duration:.1f}s audio saved to {wav_path}")


if __name__ == "__main__":
    main()
