"""VoxCPM2 TTS engine - callable library for text-to-speech generation.

Usage:
    from az_voice.tts import VoxCPM2Engine

    # Load model once (reuses across calls)
    engine = VoxCPM2Engine(device="cuda:1")
    engine.load_model()

    # Generate audio
    wav, sample_rate = engine.generate(
        text="Hello world",
        reference_wav="speaker.wav",  # Optional: for cloning
        reference_text="Transcript",   # Optional: required with reference_wav for Hi-Fi cloning
        control_instruction="speaking slowly",  # Optional: style control (no transcript)
    )

    # Cleanup when done
    engine.cleanup()
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf


class VoxCPM2Engine:
    """VoxCPM2 text-to-speech engine with model caching and VRAM cleanup.

    Load the model once, then call generate() multiple times. The engine
    handles chunking, fixed-seed stability, and VRAM cleanup automatically.
    """

    def __init__(
        self,
        model_name: str = "openbmb/VoxCPM2",
        device: str = "cuda:0",
        cache_dir: Optional[str] = None,
    ):
        """Initialize engine (does not load model yet).

        Args:
            model_name: HuggingFace model ID or local path.
            device: GPU device (e.g., "cuda:0", "cuda:1") or "cpu".
            cache_dir: Directory to cache downloaded models (default: repo/models/).
        """
        self.model_name = model_name
        self.device = device
        self._model = None
        self._sample_rate = None

        # Setup cache directory
        if cache_dir is None:
            script_dir = Path(__file__).resolve().parent.parent.parent.parent
            cache_dir = str(script_dir / "models")
        self.cache_dir = cache_dir
        os.environ["HF_HOME"] = cache_dir

    def load_model(self) -> None:
        """Load VoxCPM2 model into memory (call once before generate())."""
        from voxcpm import VoxCPM

        print(f"Loading {self.model_name} on {self.device}...")
        self._model = VoxCPM.from_pretrained(
            self.model_name,
            load_denoiser=False,
            cache_dir=self.cache_dir,
            device=self.device,
        )
        self._sample_rate = self._model.tts_model.sample_rate
        print(f"Ready. Sample rate: {self._sample_rate} Hz")

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    @property
    def sample_rate(self) -> int:
        """Get model sample rate."""
        if self._sample_rate is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        return self._sample_rate

    def generate(
        self,
        text: str,
        output_wav_path: Optional[str] = None,
        reference_wav: Optional[str] = None,
        reference_text: Optional[str] = None,
        control_instruction: Optional[str] = None,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        target_seconds: float = 15.0,
        max_words: int = 28,
    ) -> Tuple[np.ndarray, int]:
        """Generate audio from text.

        Args:
            text: Text to synthesize (can include voice design in parentheses).
            output_wav_path: Optional path to save WAV file. If None, returns audio only.
            reference_wav: Path to reference audio for cloning.
            reference_text: Transcript of reference audio (required with reference_wav for Hi-Fi cloning).
            control_instruction: Voice design/style control (e.g., "speaking slowly, happy tone").
                Cannot be used with reference_text.
            cfg_value: Classifier-free guidance scale (higher = more expressive).
            inference_timesteps: Diffusion steps (fewer = faster, 7-15 recommended).
            target_seconds: Target duration per chunk.
            max_words: Hard cap on words per segment.

        Returns:
            (wav_array, sample_rate) tuple.

        Raises:
            RuntimeError: If model not loaded.
            ValueError: If invalid parameter combination.
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Validate parameters
        if control_instruction is not None and reference_text is not None:
            raise ValueError(
                "control_instruction cannot be used with reference_text. "
                "Use either style control OR Hi-Fi cloning with transcript, but not both."
            )

        # Split text into chunks
        from az_voice.utils.text_chunker import split_text_for_tts
        segments = split_text_for_tts(text, max_words=max_words, target_seconds=target_seconds)
        if not segments:
            raise ValueError("No text segments to generate.")

        print(f"Text split into {len(segments)} segment(s)")

        # Synthesize chunks
        chunk_wavs = []
        seed_prompt_wav = None  # Fixed-seed anchor from first chunk

        for i, segment in enumerate(segments, start=1):
            kwargs = {
                "text": segment,
                "cfg_value": cfg_value,
                "inference_timesteps": inference_timesteps,
            }

            # VoxCPM requires prompt_wav_path and prompt_text together (or neither)
            if reference_wav is not None and reference_text is not None:
                # Hi-Fi cloning with transcript
                kwargs["prompt_wav_path"] = reference_wav
                kwargs["prompt_text"] = reference_text
            elif seed_prompt_wav is not None:
                # Fixed-seed continuation: use first chunk as stable anchor
                kwargs["prompt_wav_path"] = seed_prompt_wav
                kwargs["prompt_text"] = segments[0]
            elif reference_wav is not None:
                # Reference audio without transcript allows style control
                if control_instruction is not None:
                    kwargs["text"] = f"({control_instruction}){segment}"
                kwargs["reference_wav_path"] = reference_wav

            # Generate chunk
            wav = self._model.generate(**kwargs)
            chunk_wavs.append(wav)

            # Save first chunk as seed anchor for subsequent chunks (prevents drift)
            if i == 1 and len(segments) > 1:
                import tempfile
                seed_fd, seed_prompt_wav = tempfile.mkstemp(suffix=".wav")
                sf.write(seed_prompt_wav, wav, self._sample_rate)
                os.close(seed_fd)

        # Concatenate chunks
        full_wav = np.concatenate(chunk_wavs, axis=0)

        # Save to file if requested
        if output_wav_path is not None:
            out_path = Path(output_wav_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(out_path), full_wav, self._sample_rate)
            print(f"Saved: {out_path} ({len(full_wav) / self._sample_rate:.1f}s)")

        # Cleanup temp objects in VRAM
        self._clear_vram()

        return full_wav, self._sample_rate

    def _clear_vram(self) -> None:
        """Clear temporary objects from VRAM after generation."""
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def cleanup(self) -> None:
        """Unload model and free all VRAM memory."""
        import torch

        if self._model is not None:
            del self._model
            self._model = None
            print("Model unloaded.")

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            print("VRAM cleared.")
