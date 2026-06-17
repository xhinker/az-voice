"""TTS (Text-to-Speech) interface supporting multiple backends.

Planned classes:
  - TTSClient                    : OpenAI-compatible API client
                                   Works with any /v1/audio/speech endpoint
                                   (VoxCPM2 via vLLM-Omni, Higgs Audio v3 via SGLang-Omni, Boson AI cloud)
  - TTSClientVoxCPMNative        : Native voxcpm Python wrapper (no server needed)
                                    Voice design, cloning, streaming

Planned factory:
  - create_tts_client(backend="openai_api", **kwargs) → client instance
"""

# TODO: implement TTS clients


__all__ = []
