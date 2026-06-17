"""Tests for audio utilities (utils/audio_utils.py)."""

import os
import struct
import tempfile
from pathlib import Path

import pytest
from az_voice.utils.audio_utils import concatenate_wavs, _normalize_cjk_spaces


# ---------------------------------------------------------------------------
# Helper: create a minimal WAV file for testing
# ---------------------------------------------------------------------------

def _make_test_wav(path: str | Path, sample_rate: int = 24000, duration_sec: float = 1.0):
    """Create a minimal mono 16-bit PCM WAV file with silence."""
    import wave
    n_frames = int(sample_rate * duration_sec)
    frames = b"\x00\x00" * n_frames  # silence (16-bit, little-endian)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(frames)


# ---------------------------------------------------------------------------
# _normalize_cjk_spaces
# ---------------------------------------------------------------------------

class TestNormalizeCjkSpaces:
    def test_removes_space_between_cjk(self):
        assert _normalize_cjk_spaces("你好 世界") == "你好世界"

    def test_preserves_space_around_latin(self):
        assert _normalize_cjk_spaces("Hello world") == "Hello world"

    def test_mixed_language(self):
        result = _normalize_cjk_spaces("Hello 你好 世界 World")
        # Space between Latin and CJK should be kept, space between two CJK removed
        assert "你好世界" in result

    def test_empty_string(self):
        assert _normalize_cjk_spaces("") == ""

    def test_no_spaces(self):
        text = "HelloWorld你好世界"
        assert _normalize_cjk_spaces(text) == text

    def test_multiple_consecutive_spaces_between_cjk(self):
        result = _normalize_cjk_spaces("你 好")
        assert "  " not in result and ("你好" in result or "你 好" in result)


# ---------------------------------------------------------------------------
# concatenate_wavs — basic functionality
# ---------------------------------------------------------------------------

class TestConcatenateWavsBasic:
    def test_concatenate_two_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            w1 = str(Path(tmpdir) / "a.wav")
            w2 = str(Path(tmpdir) / "b.wav")
            out = str(Path(tmpdir) / "out.wav")

            _make_test_wav(w1, duration_sec=0.5)
            _make_test_wav(w2, duration_sec=0.5)

            result_path = concatenate_wavs([w1, w2], out)

            assert Path(out).exists()
            assert isinstance(result_path, Path)
            # Total should be ~1 second (within tolerance for print output parsing)
            import wave
            with wave.open(out, "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
            assert 0.9 < duration <= 1.1

    def test_concatenate_single_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            w1 = str(Path(tmpdir) / "a.wav")
            out = str(Path(tmpdir) / "out.wav")

            _make_test_wav(w1, duration_sec=1.0)
            result_path = concatenate_wavs([w1], out)

            assert Path(out).exists()
            import wave
            with wave.open(out, "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
            assert 0.9 < duration <= 1.1

    def test_concatenate_many_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_paths = []
            for i in range(5):
                wp = str(Path(tmpdir) / f"part_{i}.wav")
                _make_test_wav(wp, duration_sec=0.2)
                wav_paths.append(wp)

            out = str(Path(tmpdir) / "out.wav")
            result_path = concatenate_wavs(wav_paths, out)

            assert Path(out).exists()
            import wave
            with wave.open(out, "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
            # 5 × 0.2s = 1.0s total
            assert 0.9 < duration <= 1.1


# ---------------------------------------------------------------------------
# concatenate_wavs — edge cases and error handling
# ---------------------------------------------------------------------------

class TestConcatenateWavsEdgeCases:
    def test_skips_nonexistent_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            w1 = str(Path(tmpdir) / "real.wav")
            out = str(Path(tmpdir) / "out.wav")

            _make_test_wav(w1, duration_sec=0.5)

            result_path = concatenate_wavs([w1, "/nonexistent/file.wav"], out)
            assert Path(out).exists()

    def test_skips_empty_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            w1 = str(Path(tmpdir) / "a.wav")
            empty = str(Path(tmpdir) / "empty.wav")
            out = str(Path(tmpdir) / "out.wav")

            _make_test_wav(w1, duration_sec=0.5)
            # Create an empty file (not a valid WAV)
            Path(empty).touch()

            result_path = concatenate_wavs([w1, empty], out)
            assert Path(out).exists()

    def test_raises_on_no_valid_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = str(Path(tmpdir) / "out.wav")
            bad = str(Path(tmpdir) / "bad.txt")
            # Write non-WAV content
            Path(bad).write_text("not a wav file")

            with pytest.raises(ValueError, match="No valid WAV frames"):
                concatenate_wavs([bad], out)

    def test_raises_on_all_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = str(Path(tmpdir) / "out.wav")
            with pytest.raises(ValueError, match="No valid WAV frames"):
                concatenate_wavs(["/no/such/file1.wav", "/no/such/file2.wav"], out)

    def test_skips_wrong_sample_rate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            w_good = str(Path(tmpdir) / "good.wav")
            w_bad_sr = str(Path(tmpdir) / "bad_sr.wav")
            out = str(Path(tmpdir) / "out.wav")

            _make_test_wav(w_good, sample_rate=24000, duration_sec=0.5)
            _make_test_wav(w_bad_sr, sample_rate=16000, duration_sec=0.5)

            # Should skip the 16kHz file and only use the 24kHz one
            result_path = concatenate_wavs([w_good, w_bad_sr], out, sample_rate=24000)
            assert Path(out).exists()

    def test_accepts_path_objects(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            w1 = tmppath / "a.wav"
            out = tmppath / "out.wav"

            _make_test_wav(w1, duration_sec=0.5)
            result_path = concatenate_wavs([w1], str(out))

            assert out.exists()

    def test_output_sample_rate_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            w1 = str(Path(tmpdir) / "a.wav")
            out = str(Path(tmpdir) / "out.wav")

            _make_test_wav(w1, sample_rate=24000, duration_sec=0.5)

            concatenate_wavs([w1], out, sample_rate=24000)

            import wave
            with wave.open(out, "rb") as wf:
                assert wf.getframerate() == 24000
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2  # 16-bit


# ---------------------------------------------------------------------------
# concatenate_wavs — robustness with corrupted data
# ---------------------------------------------------------------------------

class TestConcatenateWavsRobustness:
    def test_skips_corrupted_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            w_good = str(Path(tmpdir) / "good.wav")
            w_bad = str(Path(tmpdir) / "bad.wav")
            out = str(Path(tmpdir) / "out.wav")

            _make_test_wav(w_good, duration_sec=0.5)
            # Write garbage to the bad file
            with open(w_bad, "wb") as f:
                f.write(b"\x00" * 100 + b"GARBAGE_DATA_HERE")

            result_path = concatenate_wavs([w_good, w_bad], out)
            assert Path(out).exists()

    def test_empty_list_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = str(Path(tmpdir) / "out.wav")
            with pytest.raises(ValueError, match="No valid WAV frames"):
                concatenate_wavs([], out)


# ---------------------------------------------------------------------------
# Integration — text chunking + audio workflow simulation
# ---------------------------------------------------------------------------

class TestIntegration:
    """Simulate a TTS pipeline: chunk text → synthesize (mock) → concatenate."""

    def test_chunk_then_concatenate_simulation(self):
        from az_voice.utils.text_chunker import split_text_for_tts

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Split long text into chunks
            text = "Hello world. This is a test sentence for the TTS system." * 5 + "."
            chunks = split_text_for_tts(text, max_words=28, target_seconds=12.0)

            assert len(chunks) >= 1

            # Step 2: Simulate generating one WAV per chunk (silence files as mock audio)
            wav_paths = []
            for i, chunk in enumerate(chunks):
                wp = str(Path(tmpdir) / f"chunk_{i}.wav")
                _make_test_wav(wp, duration_sec=0.1)  # Mock: each chunk → short WAV
                wav_paths.append(wp)

            # Step 3: Concatenate all chunks into final output
            out = str(Path(tmpdir) / "final.wav")
            result_path = concatenate_wavs(wav_paths, out)

            assert Path(out).exists()
            import wave
            with wave.open(out, "rb") as wf:
                # Should have one frame per chunk (0.1s each)
                duration = wf.getnframes() / wf.getframerate()
                expected_duration = len(chunks) * 0.1
                assert abs(duration - expected_duration) < 0.05, \
                    f"Expected ~{expected_duration}s, got {duration}s"
