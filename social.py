"""
Social velocity.

Scrapes the public preview of each monitored Telegram channel, extracts
contract addresses, and treats the same CA appearing across several channels
inside a short window as conviction.

The extraction is deliberately paranoid. v1 regexed raw page HTML and stored
base64 fragments from inline SVG data-URIs as contract addresses — strings
like 'cDovL3d3dy53My5vcmcv' are valid base58 and sailed straight through a
naive check. Only message text is parsed here, never markup.
"""

from __future__ import annotations

import re
import html
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import config
from chain_base import http_get
import chains

log = logging.getLogger("surgeon.social")

TG_PREVIEW = "https://t.me/s/{channel}"

# Message bodies only — attributes, scripts and data-URIs are never scanned.
_MSG_BLOCK = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)

_SOL_RE = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])"
                     r"([1-9A-HJ-NP-Za-km-z]{32,44})"
                     r"(?![1-9A-HJ-NP-Za-km-z])")
_EVM_RE = re.compile(r"(?<![0-9a-fA-Fx])(0x[a-fA-F0-9]{40})(?![0-9a-fA-F])")

# Addresses that are never a tradeable memecoin.
BLOCKLIST = {
    "So11111111111111111111111111111111111111112",   # wSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL token program
    "11111111111111111111111111111111",              # system program
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


@dataclass
class Mention:
    ca: str
    channel: str
    chain: Optional[str] = None
    seen_at: float = field(default_factory=time.time)


def _message_texts(page_html: str) -> list[str]:
    """Plain text of each message. Markup never reaches the extractor."""
    out = []
    for block in _MSG_BLOCK.findall(page_html or ""):
        text = _BR.sub("\n", block)
        text = _TAG.sub(" ", text)
        out.append(html.unescape(text))
    return out


def extract_addresses(text: str) -> list[str]:
    """
    Contract addresses from one message body.

    Base58 runs are only accepted when bounded by non-base58 characters, so
    a long token inside a URL path or an encoded blob does not fragment into
    something that merely looks like an address.
    """
    text = text or ""
    found, seen = [], set()

    def accept(match: str, haystack: str) -> bool:
        if match in seen or match in BLOCKLIST:
            return False
        idx = haystack.find(match)
        before = haystack[idx - 1] if idx > 0 else " "
        after = haystack[idx + len(match)] if idx + len(match) < len(haystack) else " "

        # base64 markers — '=' padding or '+' from an encoded payload
        if before in "=+" or after in "=+":
            return False
        # explicit data-URI context
        if "base64" in haystack[max(0, idx - 24):idx].lower():
            return False
        # A leading '/' is fine: channels often post nothing but a chart link,
        # and rejecting those would drop genuine calls.
        return True

    # EVM first, then blank those spans out. '0' and 'x' are not base58
    # characters, so an unmasked EVM address looks to the base58 scanner like
    # a clean 32-char token sitting between two valid boundaries.
    masked = text
    for m in _EVM_RE.findall(text):
        if accept(m, text):
            seen.add(m)
            found.append(m)
        masked = masked.replace(m, " " * len(m))

    for m in _SOL_RE.findall(masked):
        if accept(m, masked):
            seen.add(m)
            found.append(m)

    return found


def scrape_channel(channel: str, label: str = "") -> list[Mention]:
    """
    Read one channel's public preview.

    Telegram serves HTML. An earlier version routed this through the JSON
    fetcher, so every channel raised a decode error, burned its retries and
    silently returned nothing — the mentions table sat empty for days while
    the scraper appeared to run.
    """
    page = _raw_get(TG_PREVIEW.format(channel=channel))
    if not page:
        log.warning("@%s — no page returned", channel)
        return []

    texts = _message_texts(page)
    if not texts:
        # A page that loads but yields no messages means the markup changed
        # or Telegram is serving something else to this address.
        marker = "tgme_widget_message" in page
        log.warning("@%s — %d bytes, no messages parsed (widget markup %s)",
                    channel, len(page),
                    "present" if marker else "ABSENT — page may be a block")
        return []

    mentions, now = [], time.time()
    for text in texts:
        for ca in extract_addresses(text):
            mentions.append(Mention(ca=ca, channel=label or channel, seen_at=now))
    return mentions


def _raw_get(url: str, retries: int = 1) -> str:
    """Plain HTML fetch. Browser-ish headers: bare clients get thin pages."""
    import requests
    headers = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=15, headers=headers)
            if r.status_code == 200:
                return r.text
            log.warning("%s -> HTTP %s", url, r.status_code)
            return ""
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
                continue
            log.warning("fetch %s failed: %s", url, e)
    return ""


def scrape_all(channels=None, limit: Optional[int] = None,
               workers: int = 6) -> list[Mention]:
    """
    Every monitored channel, fetched concurrently.

    Sequentially this took twenty seconds a channel — eleven minutes for
    thirty-three, which barely fits between fifteen-minute crons. The work is
    almost entirely waiting on the network, so a small pool collapses it
    without asking more of Telegram at any instant than a browser would.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    channels = channels or config.TELEGRAM_CHANNELS
    if limit:
        channels = channels[:limit]

    all_mentions, seen = [], set()
    reached = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(scrape_channel, entry[0], entry[1]): entry[0]
            for entry in channels
        }
        for fut in as_completed(futures):
            handle = futures[fut]
            try:
                found = fut.result()
            except Exception as e:
                log.warning("channel @%s failed: %s", handle, e)
                continue
            if found:
                reached += 1
            for mn in found:
                key = (mn.ca, mn.channel)
                if key not in seen:
                    seen.add(key)
                    all_mentions.append(mn)

    log.info("scraped %d/%d channels successfully, %d mentions",
             reached, len(channels), len(all_mentions))
    if not reached and channels:
        log.error("every channel returned nothing — Telegram is likely "
                  "refusing this address range, not a parsing fault")
    return all_mentions


def resolve_chains(mentions: list[Mention],
                   max_lookups: int = 12) -> list[Mention]:
    """
    Attach a chain to each mention, in bulk.

    The earlier version asked each EVM chain in turn which one held a token —
    four requests per address, most 404ing, each falling through to a
    throttled GeckoTerminal call. That was 328 of the social job's 335
    seconds, against five spent actually scraping.

    DexScreener's token endpoint takes thirty addresses at once and returns
    pairs from every chain, so one request resolves thirty tokens. The chain
    is simply whichever pair holds the deepest liquidity.
    """
    from chain_base import http_get, safe_float, DEX_BASE

    # Solana addresses are unambiguous and cost nothing.
    unresolved = []
    for mn in mentions:
        candidates = chains.detect_chains(mn.ca)
        if len(candidates) == 1:
            mn.chain = candidates[0]
        elif candidates:
            unresolved.append(mn)

    if not unresolved:
        return mentions

    by_addr = {}
    for mn in unresolved:
        by_addr.setdefault(mn.ca.lower(), []).append(mn)

    wanted = {c: c for c in {m.ca for m in unresolved}}
    enabled = {config.CHAINS[k]["dexscreener_id"]: k
               for k in config.enabled_chains()}

    addresses = list({m.ca for m in unresolved})
    resolved = 0
    for i in range(0, len(addresses), 30):
        chunk = addresses[i:i + 30]
        data = http_get(f"{DEX_BASE}/latest/dex/tokens/{','.join(chunk)}")
        if not data:
            continue

        deepest: dict[str, tuple[float, str]] = {}
        for pair in (data.get("pairs") or []):
            chain_key = enabled.get(pair.get("chainId"))
            if not chain_key:
                continue
            addr = ((pair.get("baseToken") or {}).get("address") or "").lower()
            liq = safe_float((pair.get("liquidity") or {}).get("usd"))
            if addr in by_addr and liq > deepest.get(addr, (0, ""))[0]:
                deepest[addr] = (liq, chain_key)

        for addr, (_, chain_key) in deepest.items():
            for mn in by_addr.get(addr, []):
                mn.chain = chain_key
                resolved += 1

    log.info("chain resolution: %d of %d evm addresses resolved in %d request(s)",
             resolved, len(addresses), (len(addresses) + 29) // 30)
    return mentions


def weighted_count(channels) -> float:
    """
    Consensus strength, not headcount.

    Paid-promotion channels post what they are paid to post, so three of them
    agreeing is one advertiser's budget rather than three opinions. Weights
    live in config.CHANNEL_WEIGHTS; anything unknown counts as organic.
    """
    return round(sum(config.CHANNEL_WEIGHTS.get(c, 1.0) for c in channels), 2)


def velocity(mentions: list[Mention],
             min_channels: Optional[int] = None) -> dict[str, list[str]]:
    """
    {ca: [channels]} for tokens called by enough distinct channels.

    Counts unique channels, not messages — one channel posting a CA six times
    is one channel with an opinion, not consensus.
    """
    threshold = min_channels or config.VELOCITY_MIN_CHANNELS
    by_ca: dict[str, set[str]] = {}
    for mn in mentions:
        by_ca.setdefault(mn.ca, set()).add(mn.channel)
    return {ca: sorted(chs) for ca, chs in by_ca.items()
            if weighted_count(chs) >= threshold}


def channel_counts(mentions: list[Mention]) -> dict[str, float]:
    """{ca: weighted consensus} — feeds the conviction score."""
    by_ca: dict[str, set[str]] = {}
    for mn in mentions:
        by_ca.setdefault(mn.ca, set()).add(mn.channel)
    return {ca: weighted_count(chs) for ca, chs in by_ca.items()}
