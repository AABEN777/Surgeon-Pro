"""
Smart money and macro regime — the two conviction inputs that were never wired.

Smart money asks: have wallets with a track record bought this token recently?
Macro asks: is the tape strong enough that any of this should be trusted?

Both degrade to neutral rather than failing. A missing Helius key means zero
smart-money bonus, not a crashed scan.
"""

from __future__ import annotations

import time
import logging
from typing import Optional

import config
from chain_base import http_get, safe_float

log = logging.getLogger("surgeon.smartmoney")

HELIUS_TX = "https://api.helius.xyz/v0/addresses/{addr}/transactions"

# Recent buys per chain, refreshed once per scan.
_cache: dict[str, tuple[float, dict[str, int]]] = {}
_CACHE_TTL = 240


# ── SMART MONEY ───────────────────────────────────────────────────

def _wallets_for(chain: str, store=None) -> list[dict]:
    """
    Config wallets plus anything added to the smart_wallets table.

    The table exists so a wallet can be added from a phone without a
    redeploy — the whole point of finding one worth following is acting on
    it that day, not next release.
    """
    wallets = list(config.SMART_MONEY.get(chain, []))
    if store is not None and getattr(store, "live", False):
        try:
            rows = store.select("smart_wallets", {
                "select": "address,label",
                "chain": f"eq.{chain}",
                "active": "eq.true",
                "limit": "50",
            })
            known = {w["address"] for w in wallets}
            for r in rows:
                addr = r.get("address")
                if addr and addr not in known:
                    wallets.append({"address": addr,
                                    "label": r.get("label") or "db"})
        except Exception as e:
            log.warning("smart_wallets lookup failed: %s", e)
    return wallets


def _solana_recent_buys(wallet: str, window_seconds: int) -> set[str]:
    """Mints this wallet acquired inside the window."""
    if not config.HELIUS_API_KEY:
        return set()
    txs = http_get(HELIUS_TX.format(addr=wallet),
                   params={"api-key": config.HELIUS_API_KEY, "limit": 40},
                   timeout=15)
    if not isinstance(txs, list):
        return set()

    cutoff = time.time() - window_seconds
    bought: set[str] = set()
    for tx in txs:
        if float(tx.get("timestamp") or 0) < cutoff:
            continue
        if tx.get("type") != "SWAP":
            continue
        for tr in (tx.get("tokenTransfers") or []):
            mint = tr.get("mint")
            # Tokens arriving at the tracked wallet = a buy.
            if mint and tr.get("toUserAccount") == wallet:
                if safe_float(tr.get("tokenAmount")) > 0:
                    bought.add(mint)
    return bought


def recent_buys(chain: str, store=None,
                window_seconds: int = 7200) -> dict[str, int]:
    """
    {ca: number of distinct tracked wallets that bought it recently}

    Cached per scan — six wallets is six requests, and re-running that for
    every candidate token would be absurd.
    """
    hit = _cache.get(chain)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]

    wallets = _wallets_for(chain, store)
    counts: dict[str, int] = {}

    if wallets and config.CHAINS[chain]["kind"] == "svm":
        for w in wallets:
            try:
                for mint in _solana_recent_buys(w["address"], window_seconds):
                    counts[mint] = counts.get(mint, 0) + 1
            except Exception as e:
                log.warning("wallet %s failed: %s", w["address"][:10], e)
    # EVM wallet tracking needs a per-chain indexer; none configured yet, so
    # this returns empty rather than pretending to have checked.

    _cache[chain] = (time.time(), counts)
    if counts:
        log.info("[%s] smart money active on %d tokens", chain, len(counts))
    return counts


# ── MACRO REGIME ──────────────────────────────────────────────────

SOL_MINT = "So11111111111111111111111111111111111111112"
_macro_cache: tuple[float, str] | None = None
_MACRO_TTL = 900


def macro_regime() -> str:
    """
    BULLISH | NEUTRAL | CAUTION | PAUSE, read off SOL's 24h move.

    Memecoin risk appetite tracks SOL closely enough to use as a proxy, and
    it costs one request. Everything scored the same regardless of the tape
    before this existed — a 60/100 in a bleeding market and a 60/100 in a
    strong one were treated as the same signal, which they are not.
    """
    global _macro_cache
    if _macro_cache and (time.time() - _macro_cache[0]) < _MACRO_TTL:
        return _macro_cache[1]

    regime = "NEUTRAL"
    data = http_get(f"https://api.dexscreener.com/latest/dex/tokens/{SOL_MINT}")
    pairs = [p for p in ((data or {}).get("pairs") or [])
             if p.get("chainId") == "solana"]
    if pairs:
        deepest = max(pairs, key=lambda p: safe_float(
            (p.get("liquidity") or {}).get("usd")))
        chg = safe_float((deepest.get("priceChange") or {}).get("h24"))
        if chg >= 6:
            regime = "BULLISH"
        elif chg <= -12:
            regime = "PAUSE"
        elif chg <= -5:
            regime = "CAUTION"
        log.info("macro: SOL %+.1f%% 24h -> %s", chg, regime)
    else:
        log.warning("macro: could not read SOL, defaulting to NEUTRAL")

    _macro_cache = (time.time(), regime)
    return regime
