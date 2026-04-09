"""
Collocation analysis engine.
Computes co-occurrence frequencies and multiple association measures:
PMI, t-score, chi-squared, log-likelihood ratio (LLR), Dice coefficient.
"""

import math
from collections import Counter
from itertools import combinations


class CollocationAnalyzer:
    """Analyze lexical co-occurrence from tokenized documents."""

    def __init__(self, tokenized_docs: list[list[str]], window: int | str = 5,
                 min_freq: int = 3):
        """
        Args:
            tokenized_docs: List of documents, each a list of tokens.
            window: Integer for fixed ±window, or 'sentence' for sentence-level.
            min_freq: Minimum co-occurrence frequency to keep a pair.
        """
        self.window = window
        self.min_freq = min_freq

        # Build frequency tables
        self.freq: Counter = Counter()
        self.cooccur: Counter = Counter()
        self.N = 0  # total tokens

        for doc in tokenized_docs:
            self._count_doc(doc)

        # Prune low-frequency pairs
        self.cooccur = Counter(
            {pair: c for pair, c in self.cooccur.items() if c >= min_freq}
        )

    def _count_doc(self, tokens: list[str]):
        """Count unigrams and co-occurrences for one document."""
        self.N += len(tokens)
        self.freq.update(tokens)

        if self.window == 'sentence':
            self._count_pairs_within(tokens)
        else:
            w = int(self.window)
            for i, tok in enumerate(tokens):
                # Only look forward to avoid double-counting
                end = min(len(tokens), i + w + 1)
                for j in range(i + 1, end):
                    pair = tuple(sorted((tok, tokens[j])))
                    self.cooccur[pair] += 1

    def _count_pairs_within(self, tokens: list[str]):
        """Count all unique pairs within a token window (sentence-level)."""
        unique = list(set(tokens))
        for w1, w2 in combinations(unique, 2):
            pair = tuple(sorted((w1, w2)))
            self.cooccur[pair] += 1

    # ── Association measures ──────────────────────────────────────────────

    def _pmi(self, w1: str, w2: str, freq12: int) -> float:
        """Pointwise Mutual Information: log2(P(w1,w2) / (P(w1)*P(w2)))"""
        if self.freq[w1] == 0 or self.freq[w2] == 0 or freq12 == 0:
            return 0.0
        p12 = freq12 / self.N
        p1 = self.freq[w1] / self.N
        p2 = self.freq[w2] / self.N
        return math.log2(p12 / (p1 * p2)) if p1 * p2 > 0 else 0.0

    def _tscore(self, w1: str, w2: str, freq12: int) -> float:
        """t-score: (O - E) / sqrt(O)"""
        if freq12 == 0:
            return 0.0
        expected = (self.freq[w1] * self.freq[w2]) / self.N
        return (freq12 - expected) / math.sqrt(freq12)

    def _chi_squared(self, w1: str, w2: str, freq12: int) -> float:
        """Chi-squared from 2x2 contingency table."""
        O11 = freq12
        O12 = self.freq[w1] - freq12
        O21 = self.freq[w2] - freq12
        O22 = self.N - self.freq[w1] - self.freq[w2] + freq12

        # Prevent negative cells from estimation errors
        O12 = max(O12, 0)
        O21 = max(O21, 0)
        O22 = max(O22, 0)

        n = O11 + O12 + O21 + O22
        if n == 0:
            return 0.0

        R1 = O11 + O12
        R2 = O21 + O22
        C1 = O11 + O21
        C2 = O12 + O22

        denom = R1 * R2 * C1 * C2
        if denom == 0:
            return 0.0

        return (n * (O11 * O22 - O12 * O21) ** 2) / denom

    def _llr(self, w1: str, w2: str, freq12: int) -> float:
        """Log-likelihood ratio (G² statistic). Best for sparse data."""
        O11 = freq12
        O12 = self.freq[w1] - freq12
        O21 = self.freq[w2] - freq12
        O22 = self.N - self.freq[w1] - self.freq[w2] + freq12

        O12 = max(O12, 0)
        O21 = max(O21, 0)
        O22 = max(O22, 0)

        def _ll(o, e):
            if o == 0 or e <= 0:
                return 0.0
            return o * math.log(o / e)

        n = O11 + O12 + O21 + O22
        if n == 0:
            return 0.0

        R1 = O11 + O12
        R2 = O21 + O22
        C1 = O11 + O21
        C2 = O12 + O22

        E11 = (R1 * C1) / n if n else 0
        E12 = (R1 * C2) / n if n else 0
        E21 = (R2 * C1) / n if n else 0
        E22 = (R2 * C2) / n if n else 0

        return 2 * (_ll(O11, E11) + _ll(O12, E12) +
                     _ll(O21, E21) + _ll(O22, E22))

    def _dice(self, w1: str, w2: str, freq12: int) -> float:
        """Dice coefficient: 2*f(w1,w2) / (f(w1) + f(w2))"""
        denom = self.freq[w1] + self.freq[w2]
        return (2 * freq12) / denom if denom > 0 else 0.0

    MEASURES = {
        'pmi': '_pmi',
        'tscore': '_tscore',
        'chi_squared': '_chi_squared',
        'llr': '_llr',
        'dice': '_dice',
    }

    def _score(self, measure: str, w1: str, w2: str, freq12: int) -> float:
        method = self.MEASURES.get(measure)
        if not method:
            raise ValueError(f"Unknown measure: {measure}. Choose from {list(self.MEASURES)}")
        return getattr(self, method)(w1, w2, freq12)

    # ── Public API ────────────────────────────────────────────────────────

    def get_collocations(self, measure: str = 'llr', top_n: int = 100,
                         min_score: float = 0.0) -> list[dict]:
        """Return top collocations sorted by the given measure."""
        results = []
        for (w1, w2), freq in self.cooccur.items():
            score = self._score(measure, w1, w2, freq)
            if score >= min_score:
                results.append({
                    'w1': w1, 'w2': w2, 'freq': freq,
                    'score': round(score, 4), 'measure': measure
                })
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]

    def get_collocates_of(self, word: str, measure: str = 'llr',
                          top_n: int = 30) -> list[dict]:
        """Return collocates of a specific word."""
        results = []
        for (w1, w2), freq in self.cooccur.items():
            if w1 == word or w2 == word:
                other = w2 if w1 == word else w1
                score = self._score(measure, w1, w2, freq)
                results.append({
                    'word': other, 'freq': freq,
                    'score': round(score, 4), 'measure': measure
                })
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]

    def get_stats(self) -> dict:
        """Return corpus statistics."""
        return {
            'total_tokens': self.N,
            'vocab_size': len(self.freq),
            'unique_pairs': len(self.cooccur),
            'window': self.window,
            'min_freq': self.min_freq,
        }
