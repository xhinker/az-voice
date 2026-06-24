"""Bilingual text chunking for TTS inference.

Splits long English or Chinese text into segments suitable for single TTS calls,
respecting sentence boundaries and estimated speech duration. Adapted from
the voice_models evaluation toolkit.
"""

import re
_CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# --- Constants ---
_TERMINAL_PUNCT_CHARS = ".!?。！？"
_WEAK_PUNCT_CHARS = ",;，；、:："
_CLOSING_QUOTE_CHARS = "\"'\"')）)]》」』"

DEFAULT_MAX_WORDS = 28
DEFAULT_TARGET_SECONDS = 15.0


def _is_cjk_heavy(piece: str) -> bool:
    """Check if text is predominantly CJK (Chinese/Japanese/Korean).

    Criteria: CJK chars >= 8 AND >= 20% of all non-space chars.
    Used to pick the right speech rate for duration estimation.
    """
    non_space_chars = len(piece.replace(" ", ""))
    cjk_chars = len(_CJK_CHAR_RE.findall(piece))
    return cjk_chars >= max(8, int(non_space_chars * 0.20))


def _segment_terminal(piece: str) -> str:
    """Return the appropriate terminal punctuation for the text's language."""
    return "。" if _is_cjk_heavy(piece) else "."


def _close_segment(piece: str) -> str:
    """Make each chunk sound like a complete utterance.

    If text ends with weak punctuation (comma, semicolon), replace it with
    terminal punctuation so the TTS engine treats it as a full sentence.
    """
    normalized = " ".join(piece.strip().split())
    if not normalized:
        return ""

    suffix = ""
    while normalized and normalized[-1] in _CLOSING_QUOTE_CHARS:
        suffix = normalized[-1] + suffix
        normalized = normalized[:-1].rstrip()

    if not normalized:
        return suffix
    if normalized[-1] in _TERMINAL_PUNCT_CHARS:
        return normalized + suffix
    if normalized[-1] in _WEAK_PUNCT_CHARS:
        normalized = normalized[:-1].rstrip()
    return normalized + _segment_terminal(normalized) + suffix


def _estimate_seconds(piece: str) -> float:
    """Estimate speech duration for a text segment.

    CJK-heavy text uses character count (4 chars/sec), Latin uses word count
    (1.8 words/sec). Mixed text falls back to Latin timing.
    """
    normalized = " ".join(piece.strip().split())
    if not normalized:
        return 0.0
    non_space_chars = len(normalized.replace(" ", ""))
    words = len(normalized.split())
    cjk_chars = len(_CJK_CHAR_RE.findall(normalized))

    if _is_cjk_heavy(normalized):
        return (cjk_chars / 4.0) + ((non_space_chars - cjk_chars) / 12.0)
    return max(words / 1.8, non_space_chars / 10.0)


def split_text_for_tts(
    text: str,
    max_words: int = DEFAULT_MAX_WORDS,
    target_seconds: float = DEFAULT_TARGET_SECONDS,
) -> list[str]:
    """Split long text (English + Chinese) into chunks for TTS inference.

    Strategy:
    1. Normalize CJK spacing and split on sentence boundaries (.!?。！？)
    2. Estimate audio duration per piece (different rates for CJK vs Latin)
    3. Merge sentences until target_seconds is reached
    4. If a single sentence exceeds limits, split at nearest punctuation

    Args:
        text: Input text (English, Chinese, or mixed).
        max_words: Hard cap on words per segment.
        target_seconds: Target audio duration per segment in seconds.

    Returns:
        List of text segments, each suitable for a single TTS inference call.
    """
    clean = " ".join(text.strip().split())
    if not clean:
        return []

    sentence_pattern = rf"[^.!?。！？]+(?:[.!?。！？]+[{re.escape(_CLOSING_QUOTE_CHARS)}]*)?"
    sentences = [
        m.group(0).strip()
        for m in re.finditer(sentence_pattern, clean)
        if m.group(0).strip()
    ]

    def split_oversized_piece(piece: str) -> list[str]:
        """Split a single oversized sentence into smaller parts."""
        normalized = " ".join(piece.strip().split())
        if not normalized:
            return []
        non_space = len(normalized.replace(" ", ""))
        cjk_heavy = _is_cjk_heavy(normalized)
        max_chars = max(36, int(target_seconds * 4)) if cjk_heavy else 120

        if _estimate_seconds(normalized) <= target_seconds and non_space <= max_chars:
            return [normalized]

        words = normalized.split()
        if not cjk_heavy and len(words) > max_words:
            group_count = max(1, (len(words) + max_words - 1) // max_words)
            group_size = max(1, (len(words) + group_count - 1) // group_count)
            return [
                " ".join(words[start : start + group_size])
                for start in range(0, len(words), group_size)
            ]

        chars_per_second = 4 if cjk_heavy else 10
        window = max(36, int(target_seconds * chars_per_second)) if cjk_heavy else min(120, max(80, int(target_seconds * chars_per_second)))

        parts: list[str] = []
        start = 0
        text_len = len(normalized)
        while start < text_len:
            end = min(text_len, start + window)
            if end < text_len:
                cut = -1
                scan_start = max(start + int(window * 0.5), start + 1)
                for idx in range(end, scan_start - 1, -1):
                    if normalized[idx - 1] in _TERMINAL_PUNCT_CHARS:
                        cut = idx
                        break
                if cut == -1:
                    for idx in range(end, scan_start - 1, -1):
                        if normalized[idx - 1] in _WEAK_PUNCT_CHARS:
                            cut = idx
                            break
                if cut == -1:
                    for idx in range(end, scan_start - 1, -1):
                        ch = normalized[idx - 1]
                        if ch == "—":
                            cut = idx
                            break
                        # Only split on hyphen if NOT part of a number range (e.g., "3-4")
                        if ch == "-" and not (idx >= 2 and normalized[idx - 2].isdigit() and normalized[idx].isdigit()):
                            cut = idx
                            break
                if cut == -1:
                    cut = end
            else:
                cut = end
            part = normalized[start:cut].strip()
            if part:
                parts.append(part)
            start = cut
        return parts

    segments: list[str] = []
    current = ""

    def flush_current():
        nonlocal current
        if current:
            segments.append(current)
            current = ""

    for sentence in sentences:
        for piece in split_oversized_piece(sentence):
            words = len(piece.split())
            if words > max_words:
                flush_current()
                # Split into max_words-sized chunks, but adjust boundaries to terminal punctuation
                word_list = piece.split()
                start = 0
                while start < len(word_list):
                    end = min(start + max_words, len(word_list))
                    # Look ahead for terminal punctuation to avoid mid-sentence cuts
                    found_term = -1
                    for check in range(end, min(end + max_words, len(word_list))):
                        if any(c in _TERMINAL_PUNCT_CHARS for c in word_list[check]):
                            found_term = check + 1
                            break
                    if found_term > end:
                        end = found_term
                    segments.append(" ".join(word_list[start:end]))
                    start = end
                continue

            candidate = piece if not current else f"{current} {piece}"
            candidate_chars = len(candidate.replace(" ", ""))
            candidate_words = len(candidate.split())
            candidate_char_cap = (
                max(36, int(target_seconds * 4))
                if _is_cjk_heavy(candidate)
                else 120
            )

            if current and (
                _estimate_seconds(candidate) > target_seconds
                or candidate_chars > candidate_char_cap
                or candidate_words > max_words
            ):
                flush_current()
                current = piece
            else:
                current = candidate

    flush_current()
    segments = [closed for segment in segments if (closed := _close_segment(segment))]
    return segments if segments else [_close_segment(clean)]


__all__ = ["split_text_for_tts"]
