"""VoxCPM2 usage example - demonstrates library API with all features.

Run:
    python examples/voxcpm2_usage_example.py
"""


from az_voice.tts import VoxCPM2Engine


def main():
    # === Step 1: Initialize and load model (do this once) ===
    print("=" * 60)
    print("Step 1: Loading VoxCPM2 model...")
    print("=" * 60)

    engine = VoxCPM2Engine(
        model_name="openbmb/VoxCPM2",
        device="cuda:1",  # RTX 3090
    )
    engine.load_model()
    print()

    # === Step 2: Basic TTS ===
    print("=" * 60)
    print("Step 2: Basic TTS")
    print("=" * 60)
    wav, sr = engine.generate(
        text="Hello! This is a test of VoxCPM2 text to speech synthesis.",
        output_wav_path="outputs/example_basic.wav",
    )
    print(f"Generated {len(wav) / sr:.1f}s audio")
    print()

    # === Step 3: Voice Design (no reference audio needed) ===
    print("=" * 60)
    print("Step 3: Voice Design")
    print("=" * 60)
    wav, sr = engine.generate(
        text="(A young woman, gentle and sweet voice) Hello there! Welcome to the world of AI-generated speech.",
        output_wav_path="outputs/example_voice_design.wav",
    )
    print(f"Generated {len(wav) / sr:.1f}s audio")
    print()

    # === Step 4: Voice Cloning with reference audio + transcript (Hi-Fi mode) ===
    print("=" * 60)
    print("Step 4: Voice Cloning (Hi-Fi mode with transcript)")
    print("=" * 60)
    wav, sr = engine.generate(
        text="This is a cloned voice speaking using reference audio for maximum fidelity and natural prosody matching.",
        reference_wav="/home/andrewzhu/storage_1t_1/az_git_folder/az_samples/ai_models_eval/voice_models/qwen3-tts/role_voices/female_ch_1.wav",
        reference_text="今夜的月光如此清亮，不做些什么真是浪费。随我一同去月下漫步吧，不许拒绝。",
        output_wav_path="outputs/example_clone.wav",
    )
    print(f"Generated {len(wav) / sr:.1f}s audio")
    print()

    # === Step 5: Voice Cloning with style control (no transcript) ===
    print("=" * 60)
    print("Step 5: Voice Cloning with Style Control")
    print("=" * 60)
    wav, sr = engine.generate(
        text="Hello, I can speak in different styles and emotions.",
        reference_wav="/home/andrewzhu/storage_1t_1/az_git_folder/az_samples/ai_models_eval/voice_models/qwen3-tts/role_voices/female_ch_1.wav",
        control_instruction="speaking slowly, calm tone",  # Style control instead of transcript
        output_wav_path="outputs/example_clone_control.wav",
    )
    print(f"Generated {len(wav) / sr:.1f}s audio")
    print()

    # === Step 6: Long Chinese text with stability features ===
    print("=" * 60)
    print("Step 6: Long Chinese Text (with voice anchor for stability)")
    print("=" * 60)
    long_chinese = """
    最后上来的是一个带蓝牙耳机的时髦女子，只见她袅袅娜娜地走到广告板前拿起笔来，在所有同事的回答之下又写了几个字：综上所述。
    贝贝立马惊了：太有才了！所有的人都殚思竭虑，企图找出最佳答案，可这位蓝牙女子轻轻巧巧的四个字便夺了头彩。
    这简直是太有水平了：既有点幽默，又有点闷骚的意味儿，叫人回味无穷禁不住拍案叫好。
    美眉们各自带着得意的神情，颇以自己的见解为傲，只等着杰克发言，期待他给大家来个精彩点评。
    """
    wav, sr = engine.generate(
        text=long_chinese.strip(),
        reference_wav="/home/andrewzhu/storage_1t_1/az_git_folder/az_samples/ai_models_eval/voice_models/qwen3-tts/role_voices/female_ch_1.wav",
        reference_text="今夜的月光如此清亮，不做些什么真是浪费。随我一同去月下漫步吧，不许拒绝。",
        output_wav_path="outputs/example_long_zh.wav",
    )
    print(f"Generated {len(wav) / sr:.1f}s audio")
    print()

    # === Step 7: Long English text ===
    print("=" * 60)
    print("Step 7: Long English Text")
    print("=" * 60)
    long_english = """
    That was the night I discovered what Seven could not do.
    I sat at my kitchen table, staring at a blank document. The literary magazine wanted another story by Friday.
    Seven had already outlined three plot structures, generated five opening paragraphs, and prepared a bibliography of references.
    All I had to do was pick one and say go. But I could not.
    Not because I did not trust Seven's writing - it was good, maybe better than anything I'd ever produced.
    But because the story was not mine. The ideas were not mine. The desire to write them was not mine.
    """
    wav, sr = engine.generate(
        text=long_english.strip(),
        output_wav_path="outputs/example_long_en.wav",
    )
    print(f"Generated {len(wav) / sr:.1f}s audio")
    print()

    # === Step 8: Cleanup ===
    print("=" * 60)
    print("Step 8: Cleanup")
    print("=" * 60)
    engine.cleanup()
    print("Done! All audio files saved to outputs/ folder.")


if __name__ == "__main__":
    main()
