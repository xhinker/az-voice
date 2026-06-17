"""CJK text normalization utilities."""

import re

_CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _normalize_cjk_spaces(text: str) -> str:
    """Remove spaces only when they are between adjacent CJK characters.

    Keeps spaces around Latin text intact. Useful for mixed-language input.
    Example: "你好 世界" → "你好世界", but "Hello 世界" stays as is.
    """
    if not text or " " not in text:
        return text
    chars: list[str] = []
    for i, ch in enumerate(text):
        if ch == " " and 0 < i < len(text) - 1:
            if _CJK_CHAR_RE.match(text[i - 1]) and _CJK_CHAR_RE.match(text[i + 1]):
                continue
        chars.append(ch)
    return "".join(chars)


__all__ = ["_normalize_cjk_spaces"]
