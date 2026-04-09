"""
Pipeline orchestrator: ties segmenter, stopwords, collocation, network, concordance together.
Provides caching so parameter changes don't re-tokenize.
"""

from nlp.segmenter import tokenize, tokenize_with_pos, split_sentences
from nlp.stopwords import filter_tokens
from nlp.collocation import CollocationAnalyzer
from nlp.network import build_network, to_vis_json
from nlp.concordance import find_cooccurrences, pos_collocates, get_vocabulary


# Module-level cache: venue_name -> pipeline instance
_cache: dict[str, 'YuqingPipeline'] = {}


def get_pipeline(venue_name: str, reviews: list[dict]) -> 'YuqingPipeline':
    """Get or create a cached pipeline for a venue."""
    if venue_name not in _cache:
        _cache[venue_name] = YuqingPipeline(venue_name, reviews)
    return _cache[venue_name]


def clear_cache(venue_name: str = None):
    """Clear cached pipeline(s)."""
    if venue_name:
        _cache.pop(venue_name, None)
    else:
        _cache.clear()


class YuqingPipeline:
    """Full analysis pipeline for one venue's reviews."""

    def __init__(self, venue_name: str, reviews: list[dict]):
        self.venue_name = venue_name
        self.reviews = reviews
        self._tokens: list[list[str]] | None = None
        self._tokens_pos: list[list[tuple[str, str]]] | None = None
        self._sentence_tokens: list[list[str]] | None = None

    @property
    def tokens(self) -> list[list[str]]:
        """Tokenized + filtered documents (cached)."""
        if self._tokens is None:
            self._tokens = []
            for r in self.reviews:
                text = r.get('text', '') or ''
                if len(text.strip()) < 5:
                    continue
                raw = tokenize(text)
                filtered = filter_tokens(raw)
                if filtered:
                    self._tokens.append(filtered)
        return self._tokens

    @property
    def tokens_pos(self) -> list[list[tuple[str, str]]]:
        """Tokenized with POS tags (cached)."""
        if self._tokens_pos is None:
            self._tokens_pos = []
            for r in self.reviews:
                text = r.get('text', '') or ''
                if len(text.strip()) < 5:
                    continue
                raw = tokenize_with_pos(text)
                # Keep POS info but filter stopwords
                from nlp.stopwords import STOPWORDS
                filtered = [(w, p) for w, p in raw
                            if w.strip() and w not in STOPWORDS and len(w) >= 2]
                if filtered:
                    self._tokens_pos.append(filtered)
        return self._tokens_pos

    @property
    def sentence_tokens(self) -> list[list[str]]:
        """Tokenized at sentence level (for sentence-window collocation)."""
        if self._sentence_tokens is None:
            self._sentence_tokens = []
            for r in self.reviews:
                text = r.get('text', '') or ''
                for sent in split_sentences(text):
                    raw = tokenize(sent)
                    filtered = filter_tokens(raw)
                    if filtered:
                        self._sentence_tokens.append(filtered)
        return self._sentence_tokens

    def collocation(self, window: int | str = 5, measure: str = 'llr',
                    min_freq: int = 3, min_score: float = 0.0,
                    top_n: int = 100) -> dict:
        """Run collocation analysis with given parameters."""
        docs = self.sentence_tokens if window == 'sentence' else self.tokens
        analyzer = CollocationAnalyzer(docs, window=window, min_freq=min_freq)
        collocations = analyzer.get_collocations(
            measure=measure, top_n=top_n, min_score=min_score
        )
        return {
            'collocations': collocations,
            'stats': analyzer.get_stats(),
            'venue': self.venue_name,
        }

    def network(self, window: int | str = 5, measure: str = 'llr',
                min_freq: int = 3, min_score: float = 0.0,
                top_n: int = 100) -> dict:
        """Build semantic network from collocation results."""
        docs = self.sentence_tokens if window == 'sentence' else self.tokens
        analyzer = CollocationAnalyzer(docs, window=window, min_freq=min_freq)
        collocations = analyzer.get_collocations(
            measure=measure, top_n=top_n, min_score=min_score
        )

        # Build word frequency dict for node sizing
        word_freq = dict(analyzer.freq)
        G = build_network(collocations, word_freq=word_freq)
        result = to_vis_json(G)
        result['venue'] = self.venue_name
        result['params'] = {
            'window': window, 'measure': measure,
            'min_freq': min_freq, 'min_score': min_score, 'top_n': top_n,
        }
        return result

    def concordance_search(self, term1: str, term2: str = '',
                           window: int = 80) -> list[dict]:
        """Concordance co-occurrence search."""
        return find_cooccurrences(self.reviews, term1, term2, window)

    def pos_collocation(self, keyword: str, window: int = 5) -> dict:
        """POS-based collocation for a keyword."""
        return pos_collocates(self.tokens_pos, keyword, window)

    def vocabulary(self, min_freq: int = 3) -> list[str]:
        """Get corpus vocabulary for autocomplete."""
        return get_vocabulary(self.tokens, min_freq)

    def token_stats(self) -> dict:
        """Return basic tokenization statistics."""
        from collections import Counter
        all_tokens = [t for doc in self.tokens for t in doc]
        freq = Counter(all_tokens)
        return {
            'venue': self.venue_name,
            'total_reviews': len(self.reviews),
            'processed_reviews': len(self.tokens),
            'total_tokens': len(all_tokens),
            'vocab_size': len(freq),
            'top_words': freq.most_common(30),
        }
