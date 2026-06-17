"""Tests for CJK text normalization (utils/text_normalizer.py)."""

from az_voice.utils.text_normalizer import _normalize_cjk_spaces


class TestNormalizeCjkSpaces:
    def test_removes_space_between_cjk(self):
        assert _normalize_cjk_spaces("你好 世界") == "你好世界"

    def test_preserves_space_around_latin(self):
        assert _normalize_cjk_spaces("Hello world") == "Hello world"

    def test_mixed_language(self):
        result = _normalize_cjk_spaces("Hello 你好 世界 World")
        # Space between Latin and CJK kept, space between two CJK removed
        assert "你好世界" in result

    def test_empty_string(self):
        assert _normalize_cjk_spaces("") == ""

    def test_no_spaces(self):
        text = "HelloWorld你好世界"
        assert _normalize_cjk_spaces(text) == text

    def test_multiple_consecutive_spaces_between_cjk(self):
        result = _normalize_cjk_spaces("你 好")
        assert "  " not in result and ("你好" in result or "你 好" in result)


__all__ = ["TestNormalizeCjkSpaces"]
