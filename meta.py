"""
Meta detection.

The narrative list in config is fixed — AI, ANIMAL, POLITICAL, ELON, RWA —
and no fixed list can contain a meta that did not exist yesterday. When
alien-file coins ran, nothing in a keyword table knew what an alien file was.

This works the other way round: watch what is actually performing, find the
words those tokens share, and reward new tokens carrying the same word while
they are still small. Every scan already fetches a hundred tokens per chain
with their 24h change and discards it — that is a daily census of what is
working, going unused.
"""

from __future__ import annotations

import re
import time
import logging
from collections import Counter

import config

log = logging.getLogger("surgeon.meta")

_WORD = re.compile(r"[a-z0-9]+")

# Words that carry no narrative. Deliberately short: "inu", "cat" and "dog"
# stay in, because when the dog meta runs those words are the whole signal.
STOPWORDS = {
    "coin", "token", "the", "a", "an", "of", "on", "in", "to", "and", "for",
    "is", "it", "my", "we", "you", "this", "that", "with", "by", "at",
    "official", "community", "meme", "memecoin", "crypto", "finance",
    "protocol", "network", "labs", "dao", "io", "xyz", "fun", "app",
    "sol", "solana", "eth", "bnb", "base", "usd", "usdt", "usdc", "wrapped",
    "test", "new", "real", "true", "best", "top", "first", "next", "just",
    "com", "www", "http", "https", "pump", "bonk",
}

_cache: tuple[float, dict[str, float]] | None = None
_CACHE_TTL = 900


def terms(name: str, symbol: str = "") -> set[str]:
    """
    Narrative-bearing words in a token name.

    Single characters and pure numbers are dropped; everything else that
    survives the stopword list is a candidate meta term.
    """
    text = f"{name} {symbol}".lower()
    out = set()
    for w in _WORD.findall(text):
        if len(w) < 3 or w in STOPWORDS or w.isdigit():
            continue
        out.add(w)
    return out


def harvest(markets: list, chain: str) -> list[dict]:
    """
    Terms worth recording from one scan's worth of market snapshots.

    Only tokens genuinely performing count. A word appearing on a hundred
    flat launches says nothing; a word appearing on six tokens that all
    doubled is the meta.
    """
    now = time.time()
    rows = []
    for m in markets:
        if not getattr(m, "ok", False):
            continue
        if m.change_24h < config.META["min_change_24h"]:
            continue
        if m.liquidity_usd < config.META["min_liquidity"]:
            continue      # a 900% move on $300 of liquidity is not a meta
        for term in terms(m.name, m.symbol) | categories(m.name, m.symbol):
            rows.append({"term": term, "chain": chain,
                         "change_24h": round(m.change_24h, 2),
                         "seen_at": now})
    return rows


def categories(name: str, symbol: str = "") -> set[str]:
    """
    Which fixed narrative categories a token belongs to.

    A meta comes in two shapes. News-driven ones share literal words —
    every alien-file token says "alien". Category ones do not: a dog meta
    runs as shiba, corgi, puppy and inu, sharing a theme and no word at all.
    Word frequency finds the first kind and misses the second entirely, so
    categories are counted alongside individual words.
    """
    import scoring
    cat, _ = scoring.classify_narrative(name, symbol)
    return {f"#{cat}"} if cat != "NONE" else set()


def hot_terms(store, window_hours: float | None = None) -> dict[str, float]:
    """
    {term: strength} for whatever is currently running.

    Strength rises with how many distinct tokens carried the word, not with
    how loudly any one of them moved — one token up 4000% is a lottery
    ticket, six tokens up 150% each is a meta.
    """
    global _cache
    if _cache and (time.time() - _cache[0]) < _CACHE_TTL:
        return _cache[1]

    window = window_hours or config.META["window_hours"]
    cutoff = time.time() - window * 3600
    rows = store.select("meta_terms", {
        "select": "term,change_24h",
        "seen_at": f"gte.{cutoff}",
        "limit": "5000",
    })

    counts = Counter(r["term"] for r in rows if r.get("term"))
    strengths: dict[str, float] = {}
    for term, n in counts.items():
        # Categories aggregate many tokens by nature, so they need a higher
        # bar before counting as a live meta.
        floor = (config.META["min_tokens_category"] if term.startswith("#")
                 else config.META["min_tokens"])
        if n < floor:
            continue
        # Saturating: the tenth token carrying a word adds less than the third.
        strengths[term] = round(min(1.0, n / config.META["saturate_at"]), 3)

    _cache = (time.time(), strengths)
    if strengths:
        top = sorted(strengths.items(), key=lambda x: -x[1])[:6]
        log.info("meta running: %s",
                 ", ".join(f"{t}({s:.2f})" for t, s in top))
    return strengths


def score(name: str, symbol: str, hot: dict[str, float]) -> tuple[int, str]:
    """
    (points, matched term) for a token riding the current meta.

    Scaled by the strongest term it carries, capped so a meta match tops up
    a signal rather than carrying it.
    """
    if not hot:
        return 0, ""
    candidates = terms(name, symbol) | categories(name, symbol)
    matches = [(hot[t], t) for t in candidates if t in hot]
    if not matches:
        return 0, ""
    strength, term = max(matches)
    return int(round(config.META["max_points"] * strength)), term


def reset_cache():
    global _cache
    _cache = None
