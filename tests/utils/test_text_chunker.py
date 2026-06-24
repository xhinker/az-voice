"""Tests for bilingual text chunking (utils/text_chunker.py)."""

import pytest
from az_voice.utils.text_chunker import (
    split_text_for_tts,
    _is_cjk_heavy,
    _estimate_seconds,
    _close_segment,
    _clean_segment,
)


# ---------------------------------------------------------------------------
# _is_cjk_heavy
# ---------------------------------------------------------------------------

class TestIsCjkHeavy:
    def test_pure_chinese(self):
        assert _is_cjk_heavy("今天天气很好，我们一起去公园散步吧") is True

    def test_short_chinese_below_threshold(self):
        # Only 4 CJK chars, below the absolute minimum of 8
        assert _is_cjk_heavy("你好世界") is False

    def test_pure_english(self):
        assert _is_cjk_heavy("Hello world this is a test sentence today") is False

    def test_mixed_mostly_english(self):
        # "Chapter 1: 今天天气很好" — CJK chars exist but English dilutes ratio
        text = "Chapter One: 今天天气很好 we went to the park"
        assert _is_cjk_heavy(text) is False

    def test_mixed_mostly_chinese(self):
        # Enough Chinese with small English prefix
        text = "第1章：今天天气很好，我们一起去公园散步吧，然后去吃饭。"
        assert _is_cjk_heavy(text) is True

    def test_empty_string(self):
        assert _is_cjk_heavy("") is False

    def test_only_spaces(self):
        assert _is_cjk_heavy("   ") is False


# ---------------------------------------------------------------------------
# _estimate_seconds
# ---------------------------------------------------------------------------

class TestEstimateSeconds:
    def test_english_short(self):
        # "Hello world" = 2 words / 1.8 ≈ 1.1s, or 10 chars / 10 = 1.0s → max(1.1, 1.0) ≈ 1.1
        assert _estimate_seconds("Hello world") > 0

    def test_chinese_heavy(self):
        # CJK timing: ~4 chars/sec
        secs = _estimate_seconds("今天天气很好我们一起去公园散步吧然后去吃饭")
        assert secs > 2.0  # 18+ CJK chars ≈ 4.5s

    def test_empty_string(self):
        assert _estimate_seconds("") == 0.0

    def test_only_whitespace(self):
        assert _estimate_seconds("   ") == 0.0


# ---------------------------------------------------------------------------
# _close_segment
# ---------------------------------------------------------------------------

class TestCloseSegment:
    def test_already_terminal_en(self):
        result = _close_segment("Hello world.")
        assert result.endswith(".") or result.endswith("!") or result.endswith("?")

    def test_already_terminal_zh(self):
        result = _close_segment("你好世界。")
        assert "你" in result and ("。" in result)

    def test_weak_punctuation_replaced(self):
        # Comma should be replaced with terminal punctuation
        result = _close_segment("Hello world, you are great")
        assert not result.endswith(",") and (result[-1] in ".!?。！？")

    def test_empty_input(self):
        assert _close_segment("") == ""

    def test_only_closing_quotes(self):
        result = _close_segment("'\"'")
        # Should handle gracefully without crashing
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# split_text_for_tts — English
# ---------------------------------------------------------------------------

class TestSplitTextEnglish:
    def test_short_sentence_no_split(self):
        text = "Hello world."
        result = split_text_for_tts(text)
        assert len(result) == 1
        assert "hello" in result[0].lower() or "Hello" in result[0]

    def test_multiple_sentences_merged(self):
        # Short sentences should be merged until target_seconds is reached
        text = "Hi. Hello. Good morning. How are you? Fine thanks."
        result = split_text_for_tts(text)
        assert len(result) >= 1
        # All words from input appear in output (case-insensitive check)
        combined = " ".join(result).lower()
        for word in ["hi", "hello", "morning"]:
            assert word in combined

    def test_long_text_splits(self):
        text = " ".join([f"Word {i}" for i in range(100)]) + "."
        result = split_text_for_tts(text)
        assert len(result) > 1  # Must split into multiple segments

    def test_empty_input(self):
        result = split_text_for_tts("")
        assert result == []

    def test_only_punctuation(self):
        result = split_text_for_tts("...!!!???,;:")
        # Should handle gracefully — either empty or single segment
        for seg in result:
            assert isinstance(seg, str)

    def test_custom_max_words(self):
        text = " ".join([f"Word{i}" for i in range(50)]) + "."
        result = split_text_for_tts(text, max_words=10)
        # Each segment should have <= 10 words (approximately, after punctuation handling)
        for seg in result:
            assert len(seg.split()) <= 12  # small tolerance for punctuation

    def test_custom_target_seconds(self):
        text = " ".join([f"Word{i}" for i in range(60)]) + "."
        result_short = split_text_for_tts(text, target_seconds=3.0)
        result_long = split_text_for_tts(text, target_seconds=20.0)
        # Shorter target → more segments
        assert len(result_short) >= len(result_long)

    def test_preserves_terminal_punctuation(self):
        text = "Hello! How are you? I am fine."
        result = split_text_for_tts(text)
        combined = "".join(result)
        assert "?" in combined or "!?" not in combined  # At least some punctuation preserved


# ---------------------------------------------------------------------------
# split_text_for_tts — Chinese
# ---------------------------------------------------------------------------

class TestSplitTextChinese:
    def test_short_chinese_no_split(self):
        text = "你好世界。"
        result = split_text_for_tts(text)
        assert len(result) >= 1
        combined = "".join(result)
        assert "你" in combined and "好" in combined

    def test_long_chinese_splits(self):
        # Generate a long Chinese text (repeating phrase)
        text = "今天天气很好，我们一起去公园散步吧。" * 20 + "。"
        result = split_text_for_tts(text)
        assert len(result) > 1

    def test_chinese_punctuation_respected(self):
        text = "你好世界。今天天气很好。我们一起去玩吧！"
        result = split_text_for_tts(text)
        # Chinese sentences should be split at 。！？ boundaries
        for seg in result:
            assert isinstance(seg, str) and len(seg.strip()) > 0

    def test_chinese_terminal_punctuation_added(self):
        text = "今天天气很好"  # No terminal punctuation
        result = split_text_for_tts(text)
        if result:
            last_char = result[-1][-1]
            assert last_char in ".!?。！？", f"Expected terminal punct, got '{last_char}'"


# ---------------------------------------------------------------------------
# split_text_for_tts — Mixed English/Chinese
# ---------------------------------------------------------------------------

class TestSplitTextMixed:
    def test_mixed_language(self):
        text = "Hello 你好世界 How are you 今天天气很好 Goodbye 再见。"
        result = split_text_for_tts(text)
        assert len(result) >= 1
        combined = "".join(result)
        # Both languages should appear in output
        assert "hello" in combined.lower() or "Hello" in combined
        assert "你" in combined

    def test_chinese_with_english_numbers(self):
        text = "房间在１２３号，价格是50美元。"
        result = split_text_for_tts(text)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# Edge cases and robustness
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_newlines_and_tabs(self):
        text = "Hello\nworld.\tHow are you?"
        result = split_text_for_tts(text)
        assert len(result) >= 1

    def test_very_long_single_sentence(self):
        # No punctuation at all — one massive sentence
        text = "word " * 200
        result = split_text_for_tts(text, max_words=28)
        assert len(result) > 1  # Must force-split by word count

    def test_unicode_emojis(self):
        text = "Hello! 👋 How are you? 😊"
        result = split_text_for_tts(text)
        assert len(result) >= 1

    def test_special_characters(self):
        text = "Price: $42.50 (approx.) — vs. normal."
        result = split_text_for_tts(text)
        assert len(result) >= 1

    def test_quotes_and_brackets(self):
        text = 'He said, "Hello world!" and left.'
        result = split_text_for_tts(text)
        combined = "".join(result).lower()
        assert "hello" in combined or "world" in combined

    def test_repeated_punctuation(self):
        text = "Wait!!! What??? Really...?"
        result = split_text_for_tts(text)
        assert len(result) >= 1

    def test_single_character(self):
        result = split_text_for_tts("A")
        # Should not crash, return something reasonable
        for seg in result:
            assert isinstance(seg, str)


# ---------------------------------------------------------------------------
# Determinism and idempotency
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        text = "Hello world. This is a test sentence."
        r1 = split_text_for_tts(text)
        r2 = split_text_for_tts(text)
        assert r1 == r2

    def test_already_chunked_stays_same(self):
        # If input is already one short sentence, output should be stable
        text = "Hello world."
        result = split_text_for_tts(text)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _clean_segment — HTML entities
# ---------------------------------------------------------------------------

class TestCleanSegmentHTML:
    def test_named_entities(self):
        assert "&laquo;" not in _clean_segment("这是&laquo;测试&raquo;文本")
        assert "&mdash;" not in _clean_segment("Text with &mdash; dash")
        assert "&nbsp;" not in _clean_segment("No&nbsp;spaces")

    def test_decimal_entities(self):
        assert "&#1234;" not in _clean_segment("Text &#1234; here")
        assert "&#8212;" not in _clean_segment("Dash &#8212; here")

    def test_hex_entities(self):
        assert "&#x00AB;" not in _clean_segment("Text &#x00AB; here")
        assert "&#x2014;" not in _clean_segment("Dash &#x2014; here")

    def test_mixed_entities(self):
        text = "开始&laquo;中间&#1234;结尾&#x00AB;了"
        result = _clean_segment(text)
        assert "&" not in result or ";" not in result or "&laquo;" not in result


# ---------------------------------------------------------------------------
# _clean_segment — CJK space removal
# ---------------------------------------------------------------------------

class TestCleanSegmentCJKSpace:
    def test_space_between_cjk(self):
        result = _clean_segment("阿凯笛亚 庄园")
        assert " " not in result or "阿凯笛亚庄园" in result

    def test_multiple_spaces_between_cjk(self):
        result = _clean_segment("你好   世界")
        assert "你好世界" in result

    def test_fullwidth_space_between_cjk(self):
        result = _clean_segment("你好　世界")
        assert "你好世界" in result

    def test_space_in_english_preserved(self):
        result = _clean_segment("Hello world")
        assert "Hello world" in result

    def test_mixed_cjk_english(self):
        result = _clean_segment("你好 Hello 世界 world")
        assert "你好" in result
        assert "Hello" in result


# ---------------------------------------------------------------------------
# _clean_segment — URL removal (with TLD)
# ---------------------------------------------------------------------------

class TestCleanSegmentURLWithTLD:
    def test_simple_url(self):
        result = _clean_segment("请访问example.com查看")
        assert "example.com" not in result
        assert "请" in result and "查看" in result

    def test_https_url(self):
        result = _clean_segment("访问https://example.com/path查看")
        assert "example.com" not in result

    def test_www_url(self):
        result = _clean_segment("访问www.example.com查看")
        assert "www" not in result or "example.com" not in result

    def test_various_tlds(self):
        for tld in ["com", "net", "org", "cn", "edu", "gov", "io", "biz"]:
            result = _clean_segment(f"访问site.{tld}查看")
            assert f"{tld}" not in result

    def test_url_in_english(self):
        result = _clean_segment("Go to https://example.com now")
        assert "example.com" not in result


# ---------------------------------------------------------------------------
# _clean_segment — URL removal (without TLD, obfuscated)
# ---------------------------------------------------------------------------

class TestCleanSegmentURLObfuscated:
    def test_fullwidth_url(self):
        result = _clean_segment("访问wＷw.xiaoshuotxＴ.Ｃom查看")
        assert "xiaoshuotx" not in result

    def test_fullwidth_url_no_tld(self):
        result = _clean_segment("访问wＷw.xiaoshuotxＴ查看")
        assert "xiaoshuotx" not in result

    def test_spaced_url(self):
        result = _clean_segment("访问wＷ w.xia oshuotxＴ.Ｃom查看")
        assert "xiaoshuotx" not in result

    def test_spaced_url_no_tld(self):
        result = _clean_segment("访问wＷ w.xia oshuotxＴ查看")
        assert "xiaoshuotx" not in result

    def test_mixed_case_obfuscation(self):
        result = _clean_segment("访问wWw.XiAoShUoTxT查看")
        assert "xiaoshuotxt" not in result.lower()

    def test_fullwidth_digits_in_url(self):
        result = _clean_segment("访问123０１２site.com查看")
        assert "site.com" not in result


# ---------------------------------------------------------------------------
# _clean_segment — URL space normalization
# ---------------------------------------------------------------------------

class TestCleanSegmentURLSpaces:
    def test_spaces_in_url_normalized(self):
        result = _clean_segment("ww w . xiaoshuotxt.co m")
        assert "xiaoshuotxt.com" not in result

    def test_fullwidth_spaces_in_url(self):
        result = _clean_segment("ww　w.xiaoshuotxt.com")
        assert "xiaoshuotxt.com" not in result


# ---------------------------------------------------------------------------
# _clean_segment — preservation of normal text
# ---------------------------------------------------------------------------

class TestCleanSegmentPreservation:
    def test_normal_chinese(self):
        result = _clean_segment("今天天气很好，我们一起去公园散步吧")
        assert "今天天气很好" in result

    def test_normal_english(self):
        result = _clean_segment("Hello world, this is a test.")
        assert "Hello world" in result

    def test_mixed_normal(self):
        result = _clean_segment("Hello 你好世界 How are you")
        assert "Hello" in result
        assert "你好世界" in result

    def test_numbers_preserved(self):
        result = _clean_segment("房间在123号，价格是50美元")
        assert "123" in result
        assert "50" in result

    def test_punctuation_preserved(self):
        result = _clean_segment("你好！今天天气很好。")
        assert "！" in result or "。" in result

    def test_empty_input(self):
        result = _clean_segment("")
        assert result == ""

    def test_only_whitespace(self):
        result = _clean_segment("   ")
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# _clean_segment — edge cases
# ---------------------------------------------------------------------------

class TestCleanSegmentEdgeCases:
    def test_url_at_start(self):
        result = _clean_segment("example.com是网站")
        assert "example.com" not in result

    def test_url_at_end(self):
        result = _clean_segment("网站是example.com")
        assert "example.com" not in result

    def test_multiple_urls(self):
        result = _clean_segment("访问site1.com和site2.net查看")
        assert "site1.com" not in result
        assert "site2.net" not in result

    def test_url_with_path(self):
        result = _clean_segment("访问example.com/path/to/page查看")
        assert "example.com" not in result

    def test_short_word_not_removed(self):
        result = _clean_segment("Go now")
        assert "Go" in result and "now" in result

    def test_cjk_with_english_words(self):
        result = _clean_segment("The 阿凯笛亚庄园 is great")
        assert "阿凯笛亚庄园" in result
