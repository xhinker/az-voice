"""Audio utilities for WAV files and PCM conversion."""

import wave
from pathlib import Path


def encode_pcm_s16le(wav: "numpy.ndarray") -> bytes:
    """Encode mono float audio as raw little-endian signed 16-bit PCM."""
    import numpy as np

    pcm = np.asarray(wav, dtype=np.float32).reshape(-1)
    pcm = np.nan_to_num(pcm, nan=0.0, posinf=1.0, neginf=-1.0)
    pcm = np.clip(pcm, -1.0, 1.0)
    return (pcm * 32767.0).astype("<i2", copy=False).tobytes()


class StreamingAudioSmoother:
    """Crossfade streaming chunks before they are encoded for playback."""

    def __init__(self, crossfade_samples: int = 256, discontinuity_threshold: float = 0.04):
        self.crossfade_samples = crossfade_samples
        self.discontinuity_threshold = discontinuity_threshold
        self._tail = None

    def push(self, wav: "numpy.ndarray") -> "numpy.ndarray | None":
        """Return audio that is safe to stream now, holding a short tail."""
        import numpy as np

        chunk = np.asarray(wav, dtype=np.float32).reshape(-1)
        chunk = np.nan_to_num(chunk, nan=0.0, posinf=1.0, neginf=-1.0)
        chunk = np.clip(chunk, -1.0, 1.0)
        if chunk.size == 0:
            return None

        keep = min(self.crossfade_samples, chunk.size)

        if self._tail is None:
            self._tail = chunk[-keep:].copy()
            if chunk.size == keep:
                return None
            return chunk[:-keep]

        fade = min(self.crossfade_samples, self._tail.size, chunk.size)
        discontinuity = abs(float(self._tail[-1]) - float(chunk[0]))

        if discontinuity >= self.discontinuity_threshold:
            ramp = np.linspace(0.0, 1.0, fade, endpoint=False, dtype=np.float32)
            joined = self._tail[-fade:] * (1.0 - ramp) + chunk[:fade] * ramp
        else:
            joined = np.concatenate([self._tail[-fade:], chunk[:fade]])

        if discontinuity >= self.discontinuity_threshold:
            if self._tail.size > fade:
                output = np.concatenate([self._tail[:-fade], joined, chunk[fade:-keep]])
            else:
                output = np.concatenate([joined, chunk[fade:-keep]])
        else:
            output = np.concatenate([self._tail[:-fade], joined, chunk[fade:-keep]])

        self._tail = chunk[-keep:].copy()
        return output if output.size else None

    def flush(self) -> "numpy.ndarray | None":
        """Return the final held tail."""
        tail = self._tail
        self._tail = None
        return tail


def concatenate_wavs(
    wav_paths: list[str | Path],
    output_path: str | Path,
    sample_rate: int = 24000,
) -> Path:
    """Concatenate multiple WAV files into one.

    All input WAVs must have the same sample rate and be mono 16-bit PCM.
    Silently skips empty or unreadable files.

    Args:
        wav_paths: List of paths to WAV files to concatenate.
        output_path: Path for the output WAV file.
        sample_rate: Expected sample rate (for validation, default 24000).

    Returns:
        Path to the concatenated WAV file.

    Raises:
        ValueError: If no valid WAV frames are found in any input file.
    """
    all_frames = []
    for wp in wav_paths:
        p = Path(wp)
        if not p.exists():
            continue
        try:
            with wave.open(str(p), "rb") as wf:
                if wf.getframerate() != sample_rate:
                    print(f"  WARNING: {p.name} has sample rate {wf.getframerate()}, expected {sample_rate}. Skipping.")
                    continue
                nframes = wf.getnframes()
                if nframes == 0:
                    continue
                raw = wf.readframes(nframes)
                all_frames.append(raw)
        except Exception as e:
            print(f"  WARNING: Could not read {p.name}: {e}")

    if not all_frames:
        raise ValueError("No valid WAV frames to concatenate.")

    combined = b"".join(all_frames)
    out = Path(output_path)
    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(combined)

    duration = len(combined) / 2 / sample_rate
    print(f"Concatenated {len(all_frames)} WAV(s) -> {out} ({duration:.1f}s)")
    return out


__all__ = ["concatenate_wavs", "encode_pcm_s16le", "StreamingAudioSmoother"]
