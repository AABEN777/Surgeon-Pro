#!/usr/bin/env python3
"""
Resolve the identifiers marked VERIFY in config.CHAINS.

Run once, paste the results into config.py, never think about it again.
Adding a future chain? Run it again with that chain's name.

    python3 discover_chain_ids.py
"""

import json
import sys

from chain_base import http_get

DEX_BASE = "https://api.dexscreener.com"
GOPLUS_CHAINS = "https://api.gopluslabs.io/api/v1/supported_chains"
GT_NETWORKS = "https://api.geckoterminal.com/api/v2/networks"

WANTED = ["solana", "robinhood", "base", "bsc", "monad"]

# Known-good CAs help confirm a chainId string is real. Optional.
PROBES = {
    "solana": "So11111111111111111111111111111111111111112",
}


def dexscreener_chain_ids() -> set[str]:
    """Harvest every chainId DexScreener is currently returning."""
    ids = set()
    for path in ("/token-profiles/latest/v1",
                 "/token-boosts/latest/v1",
                 "/token-boosts/top/v1"):
        data = http_get(DEX_BASE + path)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("chainId"):
                    ids.add(item["chainId"])
    return ids


def goplus_chains() -> list[dict]:
    data = http_get(GOPLUS_CHAINS)
    if not data or data.get("code") != 1:
        return []
    return data.get("result") or []


def geckoterminal_networks() -> list[tuple[str, str]]:
    """Every network id GeckoTerminal exposes, paginated."""
    out = []
    for page in range(1, 4):   # 250 networks fit in 3 pages
        data = http_get(f"{GT_NETWORKS}?page={page}")
        rows = (data or {}).get("data") or []
        if not rows:
            break
        for n in rows:
            out.append((n.get("id", ""), (n.get("attributes") or {}).get("name", "")))
    return out


def main() -> int:
    print("=" * 60)
    print("SURGEON — chain identifier discovery")
    print("=" * 60)

    print("\n[1] DexScreener chainIds seen in live discovery feeds")
    print("-" * 60)
    ids = dexscreener_chain_ids()
    if not ids:
        print("  !! no data — DexScreener unreachable")
    else:
        for cid in sorted(ids):
            mark = "  <-- wanted" if cid in WANTED else ""
            print(f"  {cid}{mark}")
        missing = [w for w in WANTED if w not in ids]
        if missing:
            print(f"\n  not seen this run: {', '.join(missing)}")
            print("  (a chain only shows up here if it has promoted tokens")
            print("   right now — absence is not proof it is unsupported)")

    print("\n[2] GoPlus supported chains")
    print("-" * 60)
    chains = goplus_chains()
    if not chains:
        print("  !! no data — GoPlus unreachable")
    else:
        for c in sorted(chains, key=lambda x: str(x.get("name", ""))):
            name = str(c.get("name", "")).lower()
            cid = c.get("id")
            hit = any(w in name for w in ("robinhood", "monad", "base", "bsc",
                                          "bnb", "solana"))
            print(f"  {cid:<12} {c.get('name')}{'   <-- wanted' if hit else ''}")

    print("\n[3] GeckoTerminal networks (new-pool discovery source)")
    print("-" * 60)
    nets = geckoterminal_networks()
    if not nets:
        print("  !! no data — GeckoTerminal unreachable")
    else:
        print(f"  {len(nets)} networks available. Matches for our chains:")
        for want in WANTED:
            hits = [f"{i} ({n})" for i, n in nets
                    if want in i.lower() or want in n.lower()]
            print(f"    {want:<12} {', '.join(hits) if hits else 'NO MATCH'}")

    print("\n[4] Paste into config.CHAINS")
    print("-" * 60)
    lookup = {str(c.get("name", "")).lower(): c.get("id") for c in chains}
    for want in WANTED:
        gp = next((v for k, v in lookup.items() if want in k), None)
        ds = want if want in ids else "VERIFY"
        print(f'  "{want}": dexscreener_id={ds!r}, goplus_chain_id={gp!r}')

    print("\nBlockscout instances must be checked by hand — look for")
    print("an official explorer at blockscout.com/chains or the chain docs.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
