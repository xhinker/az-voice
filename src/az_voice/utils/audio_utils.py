"""Audio file utilities: WAV concatenation."""

import wave
from pathlib import Path


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


__all__ = ["concatenate_wavs"]
