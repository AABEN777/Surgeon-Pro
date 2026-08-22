"""
Chain registry.

Nothing outside this package should import a chain module directly.
Use get_adapter("base") or iterate active_adapters().
"""

from __future__ import annotations

import re
from functools import lru_cache

import config
from chain_base import (          # re-exported for the rest of the app
    ChainAdapter, TokenMarket, SafetyReport, CreatorActivity,
    http_get, safe_float, safe_int,
)
from chain_solana import SolanaAdapter
from chain_evm import EvmAdapter


@lru_cache(maxsize=None)
def get_adapter(key: str) -> ChainAdapter:
    if key not in config.CHAINS:
        raise KeyError(f"unknown chain '{key}' — add it to config.CHAINS")
    kind = config.CHAINS[key]["kind"]
    if kind == "svm":
        return SolanaAdapter()
    if kind == "evm":
        return EvmAdapter(key)
    raise ValueError(f"unsupported chain kind '{kind}' for '{key}'")


def active_adapters() -> list[ChainAdapter]:
    return [get_adapter(k) for k in config.enabled_chains()]


def detect_chains(address: str) -> list[str]:
    """
    Which enabled chains could this address belong to?

    Solana base58 and EVM hex never collide, so a 0x address narrows to the
    EVM set and a base58 address resolves to exactly one chain. For the EVM
    case the caller resolves the tie by asking DexScreener which chain
    actually has a pair — see resolve_chain().
    """
    addr = (address or "").strip()
    out = []
    for key in config.enabled_chains():
        if re.match(config.CHAINS[key]["addr_regex"], addr):
            out.append(key)
    return out


def resolve_chain(address: str) -> tuple[str | None, TokenMarket | None]:
    """
    Find the chain where this CA actually trades.

    Returns (chain_key, market) or (None, None). Picks the deepest pool when
    the same address is deployed on several EVM chains.
    """
    candidates = detect_chains(address)
    if not candidates:
        return None, None
    if len(candidates) == 1:
        mkt = get_adapter(candidates[0]).market(address)
        return (candidates[0], mkt) if mkt.ok else (None, None)

    best_key, best_mkt = None, None
    for key in candidates:
        mkt = get_adapter(key).market(address)
        if not mkt.ok:
            continue
        if best_mkt is None or mkt.liquidity_usd > best_mkt.liquidity_usd:
            best_key, best_mkt = key, mkt
    return best_key, best_mkt


__all__ = [
    "get_adapter", "active_adapters", "detect_chains", "resolve_chain",
    "ChainAdapter", "TokenMarket", "SafetyReport", "CreatorActivity",
    "http_get", "safe_float", "safe_int",
]
