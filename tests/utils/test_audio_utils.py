"""Tests for audio utilities (utils/audio_utils.py)."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
from az_voice.utils.audio_utils import StreamingAudioSmoother, concatenate_wavs, encode_pcm_s16le


# ---------------------------------------------------------------------------
# Helper: create a minimal WAV file for testing
# ---------------------------------------------------------------------------

def _make_test_wav(path, sample_rate=24000, duration_sec=1.0):
    """Create a minimal mono 16-bit PCM WAV file with silence."""
    import wave
    n_frames = int(sample_rate * duration_sec)
    frames = b"\x00\x00" * n_frames

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)


# ---------------------------------------------------------------------------
# encode_pcm_s16le — raw PCM conversion
# ---------------------------------------------------------------------------

class TestEncodePcmS16le:
    def test_is_headerless_raw_audio(self):
        audio = np.zeros(128, dtype=np.float32)

        encoded = encode_pcm_s16le(audio)

        assert len(encoded) == audio.size * 2
        assert not encoded.startswith(b"RIFF")

    def test_clips_and_sanitizes_samples(self):
        audio = np.array(
            [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, np.nan, np.inf, -np.inf],
            dtype=np.float32,
        )

        pcm = np.frombuffer(encode_pcm_s16le(audio), dtype="<i2")

        assert pcm.tolist() == [
            -32767,
            -32767,
            -16383,
            0,
            16383,
            32767,
            32767,
            0,
            32767,
            -32767,
        ]


# ---------------------------------------------------------------------------
# StreamingAudioSmoother — de-click chunk boundaries
# ---------------------------------------------------------------------------

class TestStreamingAudioSmoother:
    def test_holds_tail_until_next_chunk(self):
        smoother = StreamingAudioSmoother(crossfade_samples=2)

        out = smoother.push(np.array([0.0, 0.1, 0.2, 0.3], dtype=np.float32))
        tail = smoother.flush()

        np.testing.assert_allclose(out, [0.0, 0.1])
        np.testing.assert_allclose(tail, [0.2, 0.3])

    def test_crossfades_tail_with_next_chunk(self):
        smoother = StreamingAudioSmoother(crossfade_samples=2)

        first = smoother.push(np.array([0.0, 0.0, 1.0, 1.0], dtype=np.float32))
        second = smoother.push(np.array([-1.0, -1.0, 0.0, 0.0], dtype=np.float32))
        tail = smoother.flush()

        np.testing.assert_allclose(first, [0.0, 0.0])
        np.testing.assert_allclose(second, [1.0, 0.0])
        np.testing.assert_allclose(tail, [0.0, 0.0])

    def test_keeps_continuous_boundaries_unchanged(self):
        smoother = StreamingAudioSmoother(crossfade_samples=2)

        first = smoother.push(np.array([0.0, 0.1, 0.2, 0.3], dtype=np.float32))
        second = smoother.push(np.array([0.31, 0.4, 0.5, 0.6], dtype=np.float32))
        tail = smoother.flush()

        np.testing.assert_allclose(first, [0.0, 0.1])
        np.testing.assert_allclose(second, [0.2, 0.3, 0.31, 0.4])
        np.testing.assert_allclose(tail, [0.5, 0.6])


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
            Path(empty).touch()

            result_path = concatenate_wavs([w1, empty], out)
            assert Path(out).exists()

    def test_raises_on_no_valid_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = str(Path(tmpdir) / "out.wav")
            bad = str(Path(tmpdir) / "bad.txt")
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
                assert wf.getsampwidth() == 2


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
                _make_test_wav(wp, duration_sec=0.1)
                wav_paths.append(wp)

            # Step 3: Concatenate all chunks into final output
            out = str(Path(tmpdir) / "final.wav")
            result_path = concatenate_wavs(wav_paths, out)

            assert Path(out).exists()
            import wave
            with wave.open(out, "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
                expected_duration = len(chunks) * 0.1
                assert abs(duration - expected_duration) < 0.05


__all__ = ["TestConcatenateWavsBasic", "TestConcatenateWavsEdgeCases", "TestConcatenateWavsRobustness", "TestIntegration"]
