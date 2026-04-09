"""
Concordance (KWIC — Key Word in Context) and POS-based collocation analysis.
"""

import re
from collections import Counter, defaultdict


def find_cooccurrences(reviews: list[dict], term1: str, term2: str,
                       window: int = 80) -> list[dict]:
    """
    Find all contexts where term1 and term2 co-occur within window characters.
    If term2 is empty, find all occurrences of term1 (single-term mode).

    Args:
        reviews: List of review dicts with 'text' and 'rating' keys.
        term1: First search term (required).
        term2: Second search term (optional, empty for single-term mode).
        window: Character context before/after each term occurrence.

    Returns:
        List of match dicts with context, positions, and metadata.
    """
    results = []

    for review in reviews:
        text = review.get('text', '') or ''
        if not text.strip():
            continue
        rating = review.get('rating', 0)

        if not term2:
            # Single-term mode
            matches = _find_single(text, term1, window)
        else:
            matches = _find_pair(text, term1, term2, window)

        for m in matches:
            m['rating'] = rating
        results.extend(matches)

    return results


def _find_single(text: str, term: str, window: int) -> list[dict]:
    """Find all occurrences of a single term with context."""
    results = []
    text_len = len(text)
    for m in re.finditer(re.escape(term), text):
        ctx_start = max(0, m.start() - window)
        ctx_end = min(text_len, m.end() + window)
        context = text[ctx_start:ctx_end]
        t_pos = [[mm.start(), mm.end()] for mm in re.finditer(re.escape(term), context)]
        results.append({
            'context': context,
            'term1_positions': t_pos,
            'term2_positions': [],
            'has_prefix': ctx_start > 0,
            'has_suffix': ctx_end < text_len,
        })
    return results


def _find_pair(text: str, term1: str, term2: str, window: int) -> list[dict]:
    """Find co-occurrences of two terms within window characters."""
    text_len = len(text)
    spans = []

    def collect(anchor, other):
        for m in re.finditer(re.escape(anchor), text):
            ctx_start = max(0, m.start() - window)
            ctx_end = min(text_len, m.end() + window)
            if re.search(re.escape(other), text[ctx_start:ctx_end]):
                spans.append([ctx_start, ctx_end])

    collect(term1, term2)
    collect(term2, term1)

    # Sort and merge overlapping spans
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    results = []
    for ctx_start, ctx_end in merged:
        context = text[ctx_start:ctx_end]
        t1_pos = [[m.start(), m.end()] for m in re.finditer(re.escape(term1), context)]
        t2_pos = [[m.start(), m.end()] for m in re.finditer(re.escape(term2), context)]
        results.append({
            'context': context,
            'term1_positions': t1_pos,
            'term2_positions': t2_pos,
            'has_prefix': ctx_start > 0,
            'has_suffix': ctx_end < text_len,
        })
    return results


def pos_collocates(tokenized_pos_docs: list[list[tuple[str, str]]],
                   keyword: str, window: int = 5) -> dict:
    """
    Find collocates of a keyword grouped by POS tag.

    Args:
        tokenized_pos_docs: List of documents, each a list of (word, POS) tuples.
        keyword: Target word.
        window: Context window size (±window).

    Returns:
        Dict mapping POS categories to sorted lists of (word, count) tuples.
        Categories: 'n' (nouns), 'v' (verbs), 'a' (adjectives), 'other'.
    """
    # POS tag prefix mapping (jieba POS tags)
    POS_GROUPS = {
        'n': '名詞',   # n, nr, ns, nt, nz, ng...
        'v': '動詞',   # v, vn, vd, vg...
        'a': '形容詞', # a, ad, ag, an...
    }

    collocate_counts: dict[str, Counter] = defaultdict(Counter)

    for doc in tokenized_pos_docs:
        words = [w for w, _ in doc]
        poses = [p for _, p in doc]

        for i, w in enumerate(words):
            if w != keyword:
                continue
            start = max(0, i - window)
            end = min(len(words), i + window + 1)
            for j in range(start, end):
                if j == i:
                    continue
                collocate_word = words[j]
                pos = poses[j]

                # Map to group by first character of POS tag
                group = 'other'
                for prefix in POS_GROUPS:
                    if pos.startswith(prefix):
                        group = prefix
                        break

                collocate_counts[group][collocate_word] += 1

    # Sort each group by frequency
    result = {}
    for group in ['n', 'v', 'a', 'other']:
        counts = collocate_counts.get(group, Counter())
        result[group] = {
            'label': POS_GROUPS.get(group, '其他'),
            'collocates': counts.most_common(20),
        }

    return result


def get_vocabulary(tokenized_docs: list[list[str]], min_freq: int = 3) -> list[str]:
    """Return vocabulary sorted by frequency (for autocomplete)."""
    freq = Counter()
    for doc in tokenized_docs:
        freq.update(doc)
    return [w for w, c in freq.most_common() if c >= min_freq]
