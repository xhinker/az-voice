"""VRAM memory management utilities for TTS pipelines."""

from typing import Optional


def clear_vram() -> None:
    """Clear temporary objects from VRAM after inference.

    Calls torch.cuda.empty_cache() to free unused cached memory.
    Safe to call even when CUDA is not available.
    """
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def cleanup_model(model=None, clear_vram_memory=True) -> None:
    """Unload model and optionally free all VRAM memory.

    Args:
        model: The model object to delete (if provided).
        clear_vram_memory: Whether to call torch.cuda.empty_cache() after deletion.
    """
    if model is not None:
        del model
        print("Model unloaded.")

    if clear_vram_memory:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                print("VRAM cleared.")
        except ImportError:
            pass
