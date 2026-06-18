# %% Setup - imports and configuration
"""VoxCPM2 samples - voice design, cloning, and long-form generation.

Demonstrates:
  - Basic TTS with voice design (no reference audio)
  - Voice cloning from reference WAV + transcript
  - Long text -> chunk -> synthesize -> concatenate pipeline

Usage in VSCode: Run cells one by one with Shift+Enter or Ctrl+Alt+N
"""

import os
import tempfile
from pathlib import Path

import soundfile as sf


# %% Configuration - GPU device and model settings (edit here)
DEVICE = "cuda:1"  # Default cuda:1 (RTX 3090). Change to "cuda:0" for RTX 5090 if needed
MODEL_NAME = "openbmb/VoxCPM2"

# Override HuggingFace cache location to local models folder
script_dir = Path(__file__).resolve().parent.parent
os.environ["HF_HOME"] = str(script_dir / "models")


# %% Load model ONCE (run this cell first, then reuse for all demos)
print(f"Loading {MODEL_NAME} on {DEVICE}...")
from voxcpm import VoxCPM
model = VoxCPM.from_pretrained(
    MODEL_NAME,
    load_denoiser=False,
    cache_dir=str(script_dir / "models"),
    device=DEVICE,  # Device passed directly to from_pretrained()
)
sample_rate = model.tts_model.sample_rate

# Ensure outputs directory exists (creates it if missing)
outputs_dir = script_dir / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)

print(f"Ready. Sample rate: {sample_rate} Hz | Outputs saved to: {outputs_dir}")


# %% Helper function - generate audio (reuses pre-loaded model)
def generate_audio(
    text_input,
    output_wav_path="voxcpm2_sample.wav",  # Relative name only — caller prepends outputs_dir/
    reference_wav=None,
    reference_text=None,
    cfg_value=2.0,
    inference_timesteps=10,
    target_seconds=15.0,
    max_words=28,
):
    """Generate audio for text via chunking + synthesize + concatenate.

    Args:
        reference_wav: Path to reference audio for cloning (used as prompt_wav_path).
        reference_text: Transcript of reference audio (required when reference_wav is provided).
            VoxCPM requires both prompt_wav_path AND prompt_text together, or neither.
    """
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

    # Resolve output path relative to outputs_dir (not current working directory)
    full_output_path = outputs_dir / output_wav_path

    chunk_paths = []
    for i, segment in enumerate(segments, start=1):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            chunk_path = tmp.name

        kwargs = {"text": segment, "cfg_value": cfg_value, "inference_timesteps": inference_timesteps}
        
        # VoxCPM requires prompt_wav_path and prompt_text together (or neither)
        if reference_wav is not None and reference_text is not None:
            kwargs["prompt_wav_path"] = reference_wav  # Not reference_wav_path!
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

    from az_voice.utils.audio_utils import concatenate_wavs
    concatenate_wavs(chunk_paths, str(full_output_path), sample_rate=sample_rate)

    import wave
    with wave.open(str(full_output_path), "rb") as wf:
        total_duration = wf.getnframes() / wf.getframerate()

    for cp in chunk_paths:
        try:
            Path(cp).unlink()
        except OSError:
            pass

    return str(full_output_path), total_duration


# %% Example texts - define your input here (edit freely)
basic_text = "Hello! This is a test of VoxCPM2 text to speech synthesis."

voice_design_text = "(A young woman, gentle and sweet voice) Hello there! Welcome to the world of AI-generated speech. I can speak in any style you describe with just natural language instructions."

clone_text = "This is a cloned voice speaking using reference audio for maximum fidelity and natural prosody matching. The model preserves the speaker's unique characteristics while generating completely new content."

long_chinese_text = """
最后上来的是一个带蓝牙耳机的时髦女子，只见她袅袅娜娜地走到广告板前拿起笔来，在所有同事的回答之下又写了几个字：综上所述。
贝贝立马惊了：太有才了！所有的人都殚思竭虑，企图找出最佳答案，可这位蓝牙女子轻轻巧巧的四个字便夺了头彩。这简直是太有水平了：既有点幽默，又有点闷骚的意味儿，叫人回味无穷禁不住拍案叫好。
美眉们各自带着得意的神情，颇以自己的见解为傲，只等着杰克发言，期待他给大家来个精彩点评。
"""

long_english_text = """
That was the night I discovered what Seven could not do.
I sat at my kitchen table, staring at a blank document. The literary magazine wanted another story by Friday. Seven had already outlined three plot structures, generated five opening paragraphs, and prepared a bibliography of references. All I had to do was pick one and say go.
But I could not. Not because I did not trust Seven's writing - it was good, maybe better than anything I'd ever produced. But because the story was not mine. The ideas were not mine. The desire to write them was not mine.
"""

# %% Run: Basic TTS (uncomment and execute)
print("=== Basic TTS ===")
wav_path, duration = generate_audio(basic_text, output_wav_path="basic_tts.wav")
print(f"Done! {duration:.1f}s audio saved to {wav_path}")

# %% Run: Voice Design - no reference audio needed (uncomment and execute)
print("=== Voice Design ===")
wav_path, duration = generate_audio(voice_design_text, output_wav_path="voice_design.wav")
print(f"Done! {duration:.1f}s audio saved to {wav_path}")

# %% Run: Voice Cloning - requires BOTH reference WAV AND transcript (uncomment and execute)
ref_wav = "/home/andrewzhu/storage_1t_1/az_git_folder/az_samples/ai_models_eval/voice_models/qwen3-tts/role_voices/female_ch_1.wav"  # Edit this path to your reference audio
ref_text = "今夜的月光如此清亮，不做些什么真是浪费。随我一同去月下漫步吧，不许拒绝。"  # Transcript of the reference audio (REQUIRED)
print("=== Voice Cloning ===")
wav_path, duration = generate_audio(
    clone_text,
    output_wav_path="voice_clone.wav",
    reference_wav=ref_wav,
    reference_text=ref_text,  # Must be provided together with ref_wav!
)
print(f"Done! {duration:.1f}s audio saved to {wav_path}")

# %% Run: Long Chinese text (uncomment and execute)
print("=== Long Chinese Text ===")
wav_path, duration = generate_audio(long_chinese_text.strip(), output_wav_path="long_zh.wav")
print(f"Done! {duration:.1f}s audio saved to {wav_path}")

# %% Run: Long English text (uncomment and execute)
print("=== Long English Text ===")
wav_path, duration = generate_audio(long_english_text.strip(), output_wav_path="long_en.wav")
print(f"Done! {duration:.1f}s audio saved to {wav_path}")

# %% Cleanup - free GPU memory when done (uncomment and execute)
import torch
if torch.cuda.is_available():
    del model
    torch.cuda.empty_cache()
print("GPU cache cleared.")
