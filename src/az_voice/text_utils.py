"""Text preprocessing utilities for English and Chinese.

Planned functions:
  - expand_abbreviations_en(text)     : "dr." → "doctor", "e.g." → "for example"
  - convert_numbers_to_words_en(text): "42" → "forty-two"
  - fullwidth_to_halfwidth(text)      : "１２３ＡＢＣ" → "123ABC"
  - remove_extra_whitespace(text, replace_with=" ")
  - clean_punctuation(text, *, remove_all=False, keep_chinese_brackets=True)
  - normalize_text(text, *, lang=None, expand_abbreviations=True, ...)
  - prepare_for_tts(text, *, lang=None, convert_numbers=True) — one-liner for TTS-ready text
"""

# TODO: implement preprocessing functions


__all__ = []
