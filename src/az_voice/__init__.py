"""AZ Voice — Text preprocessing, TTS, and ASR toolkit for English and Chinese."""

__version__ = "0.1.0"

from az_voice.utils import split_text_for_tts, concatenate_wavs

# TODO: import TTS clients when implemented
# from az_voice.tts import TTSClient, TTSClientVoxCPM

# TODO: import ASR clients when implemented
# from az_voice.asr import WhisperClient, FunASRClient

__all__ = [
    "split_text_for_tts",
    "concatenate_wavs",
]
