"""
Chinese text segmentation with jieba (+ optional POS tagging via jieba.posseg).
Adapted from Word_frequency/core/segmenters.py.
"""

import os
import re

_DICT_LOADED = False
_DICT_PATH = os.path.join(os.path.dirname(__file__), "venue_dict.txt")


def _ensure_dict():
    global _DICT_LOADED
    if not _DICT_LOADED:
        import jieba
        jieba.setLogLevel("ERROR")
        if os.path.exists(_DICT_PATH):
            jieba.load_userdict(_DICT_PATH)
        _DICT_LOADED = True


def _clean_text(text: str) -> str:
    """Remove emoji, URLs, and normalize whitespace."""
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove emoji (Unicode emoji blocks)
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
        r'\U00002702-\U000027B0\U0000FE00-\U0000FE0F'
        r'\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F'
        r'\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+',
        '', text
    )
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def tokenize(text: str) -> list[str]:
    """Segment Chinese text into a list of tokens using jieba."""
    import jieba
    _ensure_dict()
    text = _clean_text(text)
    return list(jieba.cut(text, cut_all=False))


def tokenize_with_pos(text: str) -> list[tuple[str, str]]:
    """Segment text and return (word, POS) pairs using jieba.posseg."""
    import jieba.posseg as pseg
    _ensure_dict()
    text = _clean_text(text)
    return [(w.word, w.flag) for w in pseg.cut(text)]


def split_sentences(text: str) -> list[str]:
    """Split text into sentences by Chinese punctuation and newlines."""
    text = _clean_text(text)
    parts = re.split(r'[。！？\n!?]+', text)
    return [p.strip() for p in parts if p.strip()]
