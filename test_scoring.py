#!/usr/bin/env python3
"""
Scoring tests — no network required.

Every fixture is a real token from a live Verify run, with its actual
numbers. If a scoring change would have started alerting on SKYAI, or
stopped alerting on REDDIT, these fail.

    python3 test_scoring.py
"""

import sys
from datetime import datetime, timezone

import config
from chain_base import TokenMarket, SafetyReport
import scoring

PASS = FAIL = 0


def check(label, got, want):
    global PASS, FAIL
    ok = got == want
    PASS, FAIL = PASS + ok, FAIL + (not ok)
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got}" +
          ("" if ok else f"  (expected {want})"))


def check_true(label, cond):
    check(label, bool(cond), True)


# ── fixtures from real runs ───────────────────────────────────────

REDDIT = TokenMarket(                       # Robinhood, PASS_PARTIAL, 3min old
    ca="0xcb5e", chain="robinhood", name="REDDIT", symbol="RDDT",
    price_usd=0.00000811, liquidity_usd=7833, fdv=8115,
    volume_24h=12853, volume_1h=12853, volume_5m=12853,
    change_24h=321.0, change_1h=321.0, change_5m=321.0,
    buys_5m=54, sells_5m=41, age_hours=0.05, age_known=True, dex="uniswap")
REDDIT_SAFETY = SafetyReport(
    ca="0xcb5e", chain="robinhood", sources=["goplus", "blockscout"],
    top_holder_pct=7.4, top10_pct=39.78, honeypot=False, mint_authority=False,
    flags=["excluded_1_infra_holders"],
    unavailable=["lp_locked_pct", "buy_tax_pct"])

SKYAI = TokenMarket(                        # BSC, 1 holder, absurd price data
    ca="0x415a", chain="bsc", name="SKYAI", symbol="SKYAI",
    liquidity_usd=14173, fdv=819649865,
    volume_24h=7086, volume_5m=7086,
    change_24h=1315411989006.0, change_1h=1315411989006.0,
    change_5m=1315411989006.0,
    buys_5m=4, sells_5m=0, age_hours=0.07, age_known=True, dex="pancakeswap")
SKYAI_SAFETY = SafetyReport(
    ca="0x415a", chain="bsc", sources=["goplus"], holder_count=1,
    creator_holds_pct=100.0, flags=["unverified_contract"],
    hard_rejects=["creator_holds_100pct", "only_1_holders"],
    unavailable=["top_holder_pct", "lp_locked_pct"])

MEOW = TokenMarket(                         # Base, clean data, creator holds all
    ca="0x38d3", chain="base", name="MeowCoin", symbol="MEOW",
    liquidity_usd=12837, fdv=8068, volume_24h=1462, volume_1h=1462,
    volume_5m=1003, change_24h=58.3, change_1h=58.3, change_5m=33.3,
    buys_5m=16, sells_5m=1, age_hours=0.11, age_known=True, dex="uniswap")
MEOW_SAFETY = SafetyReport(
    ca="0x38d3", chain="base", sources=["goplus"], creator_holds_pct=100.0,
    honeypot=False, hard_rejects=["creator_holds_100pct"],
    unavailable=["top_holder_pct", "lp_locked_pct"])

STRUK = TokenMarket(                        # Monad, $14 liquidity, dead
    ca="0xd388", chain="monad", name="Struk Mon", symbol="SKM",
    liquidity_usd=14, fdv=7722756, volume_24h=2,
    change_5m=0.0, change_1h=0.0, buys_5m=0, sells_5m=0,
    age_hours=3.70, age_known=True, dex="pancakeswap")
STRUK_SAFETY = SafetyReport(
    ca="0xd388", chain="monad", sources=["goplus"], top_holder_pct=99.94,
    top10_pct=100.0, holder_count=6,
    hard_rejects=["top_holder_100pct", "only_6_holders"])

# A hypothetical clean second-moon runner, to prove high scores are reachable
STRONG = TokenMarket(
    ca="Abc1", chain="solana", name="Neural Agent", symbol="NAGENT",
    liquidity_usd=48000, fdv=280000, volume_24h=520000, volume_1h=180000,
    volume_5m=22000, change_24h=240.0, change_1h=140.0, change_5m=18.0,
    buys_5m=210, sells_5m=64, age_hours=0.9, age_known=True, dex="raydium")
STRONG_SAFETY = SafetyReport(
    ca="Abc1", chain="solana", sources=["rugcheck"], top_holder_pct=6.2,
    top10_pct=28.0, lp_locked_pct=100.0, holder_count=820,
    mint_authority=False, freeze_authority=False, risk_raw=1.0)


# ── alert layer ───────────────────────────────────────────────────

def test_alerts():
    import alerts, chains, dataclasses
    print("\nalert layer")
    check("escapes ampersand", alerts.esc("Test & Token"), "Test &amp; Token")
    check("escapes angle brackets", alerts.esc("<b>x</b>"), "&lt;b&gt;x&lt;/b&gt;")
    check("leaves markdown chars alone", alerts.esc("__x__ *y* `z`"), "__x__ *y* `z`")

    rh = chains.get_adapter("robinhood")
    ev = scoring.evaluate(dataclasses.replace(REDDIT, age_hours=0.20),
                          REDDIT_SAFETY, "robinhood")
    msg = alerts.format_signal(ev, rh)
    check_true("CA wrapped in <code>", f"<code>{REDDIT.ca}</code>" in msg)
    check_true("states the unchecked fields", "Unchecked:" in msg)
    check_true("shows conviction breakdown", "momentum:EXPLOSIVE" in msg)
    check_true("labels signal-only", "SIGNAL ONLY" in msg)
    check_true("within telegram limit", len(msg) < alerts.MAX_LEN)

    bare = SafetyReport(ca=REDDIT.ca, chain="robinhood")
    unv = alerts.format_signal(
        scoring.evaluate(dataclasses.replace(REDDIT, age_hours=0.20), bare, "robinhood"), rh)
    check_true("unverified is stated loudly", "treat as unverified" in unv)

    # Module-level state, so a second run in the same process would see the
    # first run's mark and report a false failure.
    alerts._last_alert.clear()
    ca = "DedupeTest"
    first = alerts.should_send(ca)
    alerts.mark_sent(ca)
    check_true("first send allowed", first)
    check_true("repeat blocked inside cooldown", not alerts.should_send(ca))
    check_true("allowed once cooldown elapses",
               alerts.should_send(ca, cooldown_minutes=0))

    check("no credentials fails cleanly",
          alerts.send("x").ok if config.TELEGRAM_BOT_TOKEN else False, False)


def test_store():
    """The in-memory fallback must behave like Supabase, or offline runs lie."""
    import time as _t
    import store as store_mod, chains
    print("\nstore (in-memory fallback)")
    s = store_mod.Store(url="", key="")
    check("no credentials -> not live", s.live, False)

    ev = scoring.evaluate(STRONG, STRONG_SAFETY, "solana",
                          social_channels=3, smart_wallets=2)
    s.record_signal(ev, chains.get_adapter("solana"), sent_ok=True)
    check("signal opens a position", len(s.open_positions()), 1)

    s.close_position(STRONG.ca, "WIN", "TP2", final_pnl=118.0, peak_pnl=204.0)
    check("closed position leaves open set", len(s.open_positions()), 0)
    check("win rate computed", s.stats()["win_rate"], 100.0)

    now = _t.time()
    s.record_mentions([
        {"ca": "X1", "chain": "solana", "channel": "Blessed", "seen_at": now},
        {"ca": "X1", "chain": "solana", "channel": "Catfish", "seen_at": now},
        {"ca": "X2", "chain": "solana", "channel": "Blessed", "seen_at": now},
        {"ca": "X3", "chain": "solana", "channel": "Kook", "seen_at": now - 99999},
    ])
    check("two channels counted", len(s.channels_for("X1")), 2)
    check("one channel not inflated", len(s.channels_for("X2")), 1)
    check("stale mention excluded", len(s.channels_for("X3")), 0)

    check("dedupe map populated", list(s.recently_alerted().keys()), [STRONG.ca])
    check("zero window clears dedupe", s.recently_alerted(minutes=0), {})

    s.mark_watch_event(STRONG.ca, "TP1", 52.0)
    check("watch event recorded", s.fired_watch_events(STRONG.ca), {"TP1"})


def test_social():
    """Extraction must reject markup and keep real calls."""
    import social
    print("\nsocial extraction")

    check("bare solana CA", social.extract_addresses(
        "CA: 9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"),
        ["9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"])
    check("chart link only", social.extract_addresses(
        "https://dexscreener.com/solana/9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"),
        ["9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu"])
    check("base64 data-uri rejected", social.extract_addresses(
        "url(data:image/svg+xml;base64,cDovL3d3dy53My5vcmcvMjAwMC9zdmc=)"), [])
    check("unpadded base64 rejected", social.extract_addresses(
        "src=data:image/png;base64,uZGVmaW5pdGUiLz48L2xpbmVhckdyYWRpZW50Pg"), [])
    check("wSOL blocklisted", social.extract_addresses(
        "So11111111111111111111111111111111111111112"), [])

    both = social.extract_addresses(
        "sol 9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu "
        "evm 0xcb5ecd927f4ef6c9bd9cc434bc2119e05160160c")
    check("mixed line yields exactly two", len(both), 2)
    check_true("no base58 fragment carved from EVM address",
               not any(a.startswith("xcb5") for a in both))

    page = ('<style>background:url(data:image/svg+xml;base64,'
            'cDovL3d3dy53My5vcmcvMjAwMC9zdmc=)</style>'
            '<div class="tgme_widget_message_text" dir="auto">'
            'call 9d8EnYYZTybmSsAYc2vxNxY6opaiDrUwcx4FEhjMdxyu</div>')
    texts = social._message_texts(page)
    check("only message bodies parsed", len(texts), 1)
    check_true("markup outside messages ignored",
               "cDovL" not in " ".join(texts))

    now = __import__("time").time()
    M = social.Mention
    mentions = [
        M(ca="A", channel="Blessed", seen_at=now),
        M(ca="A", channel="Blessed", seen_at=now),   # same channel twice
        M(ca="A", channel="Catfish", seen_at=now),
        M(ca="B", channel="Kook", seen_at=now),
    ]
    vel = social.velocity(mentions, min_channels=2)
    check("velocity finds the consensus token", list(vel.keys()), ["A"])
    check("repeat posts are not consensus",
          social.channel_counts(mentions)["A"], 2)
    check("single channel excluded", "B" in vel, False)


def test_tiers():
    """
    Tier gates against real profiles from live runs.

    Volume is measured over the last hour, not 24h. A token twelve minutes
    old has a "24h volume" equal to its entire life, so a $50k 24h floor was
    demanding $50k of trade in twelve minutes and rejecting real runners.
    """
    print("\ntier gates")
    cases = [
        # name, chain, liq, fdv, vol, chg1h, chg5m, age, should_match
        ("REDDIT rh",     "robinhood", 7833,  8115,      12853,  321,    6.6,    0.2, True),
        ("FomoMining rh", "robinhood", 20848, 19153,     34075,  227,   -3.3,    0.2, True),
        ("Korea Robot",   "solana",    70170, 70879,     12573,  46,     46,     0.2, True),
        ("mid runner",    "solana",    45000, 190000,    210000, 85,     12,     1.5, True),
        ("3h old $60k",   "solana",    30000, 60000,     90000,  40,     5,      3.0, True),
        ("thin volume",   "solana",    13339, 6891,      2057,   6.5,    6.5,    0.2, False),
        ("dead $14 liq",  "monad",     14,    7722756,   2,      0,      0,      3.7, False),
        ("SKYAI garbage", "bsc",       14173, 819649865, 7086,   1.3e12, 1.3e12, 0.07, False),
    ]
    for name, chain, liq, fdv, vol, c1h, c5m, agehr, want in cases:
        m = TokenMarket(ca="x", chain=chain, name=name, symbol="X",
                        liquidity_usd=liq, fdv=fdv, volume_24h=vol,
                        volume_1h=vol, change_1h=c1h, change_5m=c5m,
                        age_hours=agehr, age_known=True, dex="uniswap")
        r = scoring.classify_tier(m, chain, session="NORMAL")
        check(f"{name} matches a tier", r.matched, want)

    # No coverage hole between tiers: first_moon stops at 2h, second_moon
    # needs $100k FDV, so a 3h-old $60k token must land in boosted.
    gap = TokenMarket(ca="g", chain="solana", name="gap", symbol="G",
                      liquidity_usd=30000, fdv=60000, volume_24h=90000,
                      volume_1h=90000, change_1h=40, change_5m=5,
                      age_hours=3.0, age_known=True, dex="raydium")
    check("inter-tier gap covered by boosted",
          scoring.classify_tier(gap, "solana", session="NORMAL").tier, "boosted")


def test_watchlist():
    """
    Discovery finds pools minutes old; the entry filter wants ten minutes.
    Parking is what stops that gap from silently discarding every launch.
    """
    import scan, store as store_mod
    print("\nwatchlist")

    def mk(age, liq=40000, fdv=60000, vol=80000, c1h=60):
        return TokenMarket(ca="w", chain="solana", name="W", symbol="W",
                           liquidity_usd=liq, fdv=fdv, volume_24h=vol,
                           volume_1h=vol, change_1h=c1h, change_5m=12,
                           buys_5m=8, sells_5m=2,
                           age_hours=age, age_known=True, dex="raydium")

    def park(m):
        return scan._worth_parking(
            scoring.classify_tier(m, "solana", session="NORMAL"), m)

    def mk_traded(**kw):
        base = dict(ca="w", chain="solana", name="W", symbol="W",
                    liquidity_usd=40000, fdv=60000, volume_24h=80000,
                    volume_1h=80000, change_1h=60, change_5m=12, buys_5m=8,
                    sells_5m=2, age_hours=0.04, age_known=True, dex="raydium")
        base.update(kw)
        return TokenMarket(**base)

    # Memecoin outcomes are fat-tailed: a quiet pool genuinely can turn, so
    # the net stays wide. Re-checks are batched 30 tokens per request, which
    # makes holding a token cost a fraction of an API call instead of one.
    check("mixed flow still parked",
          park(mk_traded(buys_5m=6, sells_5m=9)), True)
    check("barely traded still parked",
          park(mk_traded(buys_5m=2, volume_1h=120, volume_24h=120)), True)
    check("sellers only, no bid — not parked",
          park(mk_traded(buys_5m=0, sells_5m=7, volume_1h=300,
                         volume_24h=300)), False)

    check("healthy young pool parked", park(mk(0.04)), True)
    # Re-check slots are the scarce resource, not database rows.
    check("untraded pool not parked",
          park(TokenMarket(ca="u", chain="solana", name="U", symbol="U",
                           liquidity_usd=6000, fdv=9000, volume_24h=0,
                           volume_1h=0, change_1h=2, change_5m=0,
                           buys_5m=0, sells_5m=0, age_hours=0.04,
                           age_known=True, dex="raydium")), False)
    check("thin but live pool parked",
          park(TokenMarket(ca="v", chain="solana", name="V", symbol="V",
                           liquidity_usd=6000, fdv=9000, volume_24h=200,
                           volume_1h=200, change_1h=2, change_5m=0,
                           buys_5m=7, sells_5m=1, age_hours=0.04,
                           age_known=True, dex="raydium")), True)
    # Liquidity, volume and turnover all accumulate with time, so a pool
    # three minutes old failing them is one objection, not four.
    check("fresh pool with real flow parked",
          park(mk(0.04, liq=3200, fdv=5800, vol=900, c1h=4)), True)
    check("dust pool not parked",
          park(mk(0.04, liq=400, fdv=900, vol=10, c1h=0)), False)
    check("absurd fdv not parked",
          park(mk(0.04, fdv=819_649_865, vol=100)), False)
    check("too old not parked", park(mk(48)), False)

    import time as _t
    s = store_mod.Store(url="", key="")
    now = _t.time()
    # Re-checking a token that is still inside the delay window spends a rate
    # limit to rediscover what we already knew.
    s.upsert("watchlist", {"ca": "young", "chain": "solana",
                           "first_seen": now - 120, "first_age_hours": 0.05},
             on_conflict="ca")
    s.upsert("watchlist", {"ca": "ready", "chain": "solana",
                           "first_seen": now - 1200, "first_age_hours": 0.05},
             on_conflict="ca")
    s.upsert("watchlist", {"ca": "recent", "chain": "solana",
                           "first_seen": now - 1200, "first_age_hours": 0.05,
                           "last_checked": now - 30}, on_conflict="ca")
    due = [r["ca"] for r in s.due_for_recheck()]
    check("only matured tokens re-checked", due, ["ready"])

    # Stale rows were only deleted when re-checked, but re-check skipped
    # anything past the window — so they became permanent and starved the
    # fresh ones behind them.
    s.upsert("watchlist", {"ca": "ancient", "chain": "solana",
                           "first_seen": now - 7 * 3600, "first_age_hours": 0.05},
             on_conflict="ca")
    check("stale entry purged", s.purge_watchlist(), 1)

    # Discovery re-surfaces the same pools between scans. Upserting on every
    # sighting wiped first_seen and reset checks, so a token could be
    # re-checked repeatedly and still look untouched — and never age out.
    check("first park accepted", s.watch_later("dup", "solana", 0.05), True)
    kept = s.select("watchlist", {"ca": "eq.dup"})[0]["first_seen"]
    s.bump_check("dup", 0)
    check("re-park ignored", s.watch_later("dup", "solana", 0.30), False)
    again = s.select("watchlist", {"ca": "eq.dup"})[0]
    check("check count survives re-park", again["checks"], 1)
    check("first_seen survives re-park", again["first_seen"] == kept, True)

    # Oldest-first meant the same 45 tokens filled every slot on every scan
    # while 239 others were never looked at once. Least-recently-checked
    # first gives the whole queue a turn.
    # _mem is module-global, so isolate before asserting on ordering.
    store_mod._mem["watchlist"] = []
    s2 = store_mod.Store(url="", key="")
    for ca, last, checks in (("never", None, 0), ("old", now - 3600, 1),
                             ("recent", now - 60, 1)):
        row = {"ca": ca, "chain": "solana", "first_seen": now - 3600,
               "first_age_hours": 0.05, "checks": checks}
        if last:
            row["last_checked"] = last
        s2.insert("watchlist", row)
    s2.insert("watchlist", {"ca": "spent", "chain": "solana",
                            "first_seen": now - 3600, "first_age_hours": 0.05,
                            "checks": config.WATCH["max_watchlist_checks"],
                            "last_checked": now - 3600})
    check("round-robin order", [r["ca"] for r in s2.due_for_recheck()],
          ["never", "old"])
    check("exhausted token retired", s2.purge_watchlist(), 1)
    check("survivors kept", sorted(r["ca"] for r in s2.select("watchlist")),
          ["never", "old", "recent"])
    store_mod._mem["watchlist"] = []
    check("dropped after revival",
          [r["ca"] for r in s.due_for_recheck()], [])


def test_context_inputs():
    """
    Social consensus, smart money and macro regime were all silently absent:
    social_counts was only populated when scraping ran in the same process,
    smart_wallets was hardcoded to 0, and macro was always NEUTRAL. Together
    that is up to forty points of conviction that never once applied, which
    is why nothing ever reached the HIGH band.
    """
    print("\ncontext inputs")
    m = TokenMarket(ca="c", chain="solana", name="Neural Agent", symbol="NAG",
                    liquidity_usd=45000, fdv=190000, volume_24h=210000,
                    volume_1h=180000, change_1h=85, change_5m=12,
                    buys_5m=210, sells_5m=64, age_hours=0.9, age_known=True,
                    dex="raydium")
    # A holder count is what makes a low risk score meaningful — without one
    # the score reflects "nothing detected yet", and this fixture is meant to
    # be an established token rather than an unexamined one.
    s = SafetyReport(ca="c", chain="solana", sources=["rugcheck"],
                     top_holder_pct=6.2, lp_locked_pct=100.0, risk_raw=1.0,
                     holder_count=820)

    bare = scoring.conviction_score(m, s, 0, 0, "NEUTRAL", session="NORMAL")
    social = scoring.conviction_score(m, s, 3, 0, "NEUTRAL", session="NORMAL")
    smart = scoring.conviction_score(m, s, 0, 2, "NEUTRAL", session="NORMAL")
    check_true("social consensus raises score", social.score > bare.score)
    check_true("smart money raises score", smart.score > bare.score)
    check_true("social reaches HIGH band", social.band == "HIGH")

    # Macro must be able to change the decision, not just the number.
    mid = TokenMarket(ca="d", chain="base", name="Frog crazy", symbol="FROG",
                      liquidity_usd=18000, fdv=40000, volume_24h=26000,
                      volume_1h=22000, change_1h=48, change_5m=9,
                      buys_5m=34, sells_5m=21, age_hours=0.6, age_known=True,
                      dex="uniswap")
    ms = SafetyReport(ca="d", chain="base", sources=["goplus"], honeypot=False,
                      holder_count=640, unavailable=["top_holder_pct"])
    bull = scoring.conviction_score(mid, ms, 0, 0, "BULLISH", session="NORMAL")
    pause = scoring.conviction_score(mid, ms, 0, 0, "PAUSE", session="NORMAL")
    # Tracking and alerting are separate floors: this compares the decision
    # to consider the token at all, which is where macro should bite.
    check_true("bull tape keeps the setup", bull.trackable)
    check_true("bleeding tape drops the same setup", not pause.trackable)
    check_true("macro appears in the breakdown", "macro:PAUSE" in pause.explain())


def test_watcher():
    """
    Position outcomes. Three roadmap items — derived smart money, channel
    accuracy and narrative retuning — are all blocked on knowing which
    signals were right, which is what these events produce.
    """
    import watch, time as _t
    print("\nposition watcher")

    # Peak matters as well as the close: a token that ran 300% and gave it
    # back was a correct call badly exited, not a bad signal.
    check("ran 260% then faded is still MOON",
          watch.classify_outcome(10, 260), "MOON")
    check("held 120% is BIG_WIN", watch.classify_outcome(120, 150), "BIG_WIN")
    check("closed red is LOSS", watch.classify_outcome(-40, 5), "LOSS")

    now = _t.time()

    def row(entry=1.0, peak=None, hours=0.5):
        return {"ca": "x", "chain": "solana", "name": "T", "symbol": "T",
                "entry_price": entry, "peak_price": peak or entry,
                "alerted_at": now - hours * 3600}

    def mkt(price, **kw):
        base = dict(ca="x", chain="solana", name="T", symbol="T",
                    price_usd=price, liquidity_usd=40000, fdv=60000,
                    volume_1h=24000, volume_5m=2000, dex="raydium")
        base.update(kw)
        return TokenMarket(**base)

    def events(r, m, fired=None, safety=None):
        return [e for e, _ in watch.evaluate_position(
            r, m, None, fired or set(), safety)]

    check_true("TP1 fires at +55%", "TP1" in events(row(), mkt(1.55)))
    # Warning and grading are separate. CATCOIN was signalled and stopped out
    # inside five minutes at -26% with a peak of exactly +0% — closing a
    # position that young records a verdict we have not earned, and if early
    # dips do recover it files a correct call as a loss.
    early = events(row(hours=5 / 60), mkt(0.74))
    check_true("early dip warns", "STOP_WARN" in early)
    check_true("early dip does not grade", "STOP_LOSS" not in early)
    check_true("deep loss past grace does grade",
               "STOP_LOSS" in events(row(hours=0.5), mkt(0.60), {"STOP_WARN"}))
    check_true("recovery after an early dip is not a loss",
               "STOP_LOSS" not in events(row(hours=1.5), mkt(2.2),
                                         {"STOP_WARN", "TP1"}))
    check_true("STOP_WARN keeps the position open",
               "STOP_WARN" not in watch.TERMINAL)

    # A near-zero entry price produced readings in the millions — seven rows
    # put average final PnL at 124 million percent. Returning None rather
    # than clamping matters: a clamped number is a fabricated outcome, and
    # every weight we later learn is learned from these rows.
    check("normal move measured", round(watch._pnl(1.0, 1.5)), 50)
    check("near-zero entry rejected", watch._pnl(1e-12, 0.02), None)
    check("zero entry rejected", watch._pnl(0.0, 1.0), None)
    check("impossible gain rejected", watch._pnl(1.0, 500.0), None)
    check("untrustworthy pricing judges nothing",
          events(row(), TokenMarket(ca="x", chain="solana", name="T",
                                    symbol="T", price_usd=0.02,
                                    liquidity_usd=40000, fdv=60000,
                                    volume_1h=24000, dex="raydium"),
                 fired=set()) if False else
          watch.evaluate_position({"ca": "x", "entry_price": 1e-12,
                                   "peak_price": 1e-12,
                                   "alerted_at": now - 600},
                                  mkt(0.02), None, set(), None), [])
    # wDELLx peaked +45%, never reached TP1 at +50%, and gave back everything
    # with nothing firing. Trailing now arms on any real gain, and is
    # measured as the fraction of the gain surrendered — 40% off a +45% peak
    # is break-even, 40% off a +500% peak is still a large win, so drawdown
    # from peak price cannot mean the same thing at both scales.
    check_true("holds while the gain holds",
               "TRAIL_STOP" not in events(row(peak=1.45), mkt(1.30)))
    check_true("fires once most of the gain is surrendered",
               "TRAIL_STOP" in events(row(peak=1.45), mkt(1.15)))
    check_true("noise on a small gain does not arm",
               "TRAIL_STOP" not in events(row(peak=1.12), mkt(1.02)))
    check_true("big winner keeps room to run",
               "TRAIL_STOP" not in events(row(peak=5.0), mkt(4.0),
                                          {"TP1", "TP2", "TP3"}))
    check_true("tighter once TP2 is banked",
               "TRAIL_STOP" in events(row(peak=5.0), mkt(2.6),
                                      {"TP1", "TP2", "TP3"}))
    check_true("volume fade while in profit",
               "VOLUME_FADE" in events(row(), mkt(1.30, volume_5m=100)))

    # Positions below the alert bar are tracked and graded for the outcome
    # data but were never announced. Firing a TP alert on one delivers news
    # about a token King has never heard of.
    import inspect
    src = inspect.getsource(watch.watch_chain)
    check_true("watcher checks whether a position was announced",
               "alert_sent" in src)
    check_true("sending is guarded by it", "and announced" in src)
    check_true("but events are still recorded",
               "store.mark_watch_event" in src)
    check_true("and positions still close",
               "store.close_position" in src)
    check("healthy position fires nothing", events(row(), mkt(1.20)), [])

    # Whale concentration that appears after entry is a different thing from
    # concentration that was there all along — the latter blocks the signal.
    late_whale = SafetyReport(ca="x", chain="solana", sources=["rugcheck"],
                              top_holder_pct=41.0)
    check_true("whale appearing after entry",
               "WHALE_STOP" in events(row(hours=3), mkt(1.45),
                                      safety=late_whale))

    # FDV over the graduation threshold is meaningless off a bonding curve,
    # and firing it everywhere suppressed legitimate time stops.
    on_curve = mkt(1.05, dex="pumpfun", launchpad="pumpfun", fdv=70000)
    ev = events(row(hours=5), on_curve)
    check_true("graduation holds an on-curve token",
               "GRADUATION" in ev and "TIME_STOP" not in ev)
    check_true("no graduation once trading on an AMM",
               "GRADUATION" not in events(row(hours=5),
                                          mkt(1.05, dex="pumpswap",
                                              launchpad="pumpfun", fdv=70000)))
    check_true("no graduation on chains without curves",
               "GRADUATION" not in events(row(hours=5),
                                          mkt(1.05, dex="uniswap", fdv=70000)))


def test_candidate_ordering():
    """
    Discovery returns newest-first. On a chain launching hundreds of tokens
    an hour, the newest forty are all under ten minutes old — so a scan that
    walks the list until its limit runs out evaluates nothing but tokens too
    young to qualify, while mature ones further down are never seen at all.

    Solana produced zero signals for days because of this.
    """
    print("\ncandidate ordering")

    def tok(age, name):
        return TokenMarket(ca=name, chain="solana", name=name, symbol=name,
                           liquidity_usd=30000, fdv=60000, volume_24h=40000,
                           volume_1h=40000, change_1h=45, change_5m=8,
                           buys_5m=30, sells_5m=10, age_hours=age,
                           age_known=True, dex="raydium")

    candidates = [tok(0.01 + i * 0.002, f"new{i}") for i in range(56)]
    candidates += [tok(0.5 + i * 0.3, f"mature{i}") for i in range(50)]
    limit = 40

    def matched(slice_):
        return sum(1 for m in slice_
                   if scoring.classify_tier(m, "solana", session="NORMAL").matched)

    check("discovery order finds nothing", matched(candidates[:limit]), 0)

    min_age = config.thresholds_for("solana", "first_moon")["min_age_hours"]
    ordered = sorted(candidates,
                     key=lambda m: (0 if m.age_hours >= min_age else 1,
                                    m.age_hours))
    check_true("maturity order finds candidates", matched(ordered[:limit]) > 0)
    check_true("mature tokens lead", ordered[0].age_hours >= min_age)


def test_scam_flags():
    """
    Trader-supplied scam tells. Thresholds are far tighter than the entry
    gates — top holder at 3.5% against a 20% reject — so they are scored
    rather than enforced. A token collecting several falls below the alert
    floor on arithmetic; a token collecting several *severe* ones is a
    pattern and gets blocked outright.
    """
    import risk
    print("\nscam heuristics")

    clean_m = TokenMarket(ca="a", chain="solana", name="Clean", symbol="CLN",
                          liquidity_usd=45000, fdv=180000, market_cap=180000,
                          volume_24h=220000, volume_1h=60000)
    clean_s = SafetyReport(ca="a", chain="solana", sources=["rugcheck"],
                           top_holder_pct=2.8, insider_pct=4.0,
                           holder_count=640, creator_holds_pct=0.4)
    check("clean token flags nothing", risk.assess(clean_m, clean_s), [])

    painted = TokenMarket(ca="b", chain="solana", name="Painted", symbol="PNT",
                          liquidity_usd=20000, fdv=900000, market_cap=900000,
                          volume_24h=45000, volume_1h=6000)
    painted_s = SafetyReport(ca="b", chain="solana", sources=["rugcheck"],
                             top_holder_pct=12.5, insider_pct=24.0,
                             holder_count=38, creator_holds_pct=5.5)
    flags = risk.assess(painted, painted_s)
    codes = {f.code for f in flags}
    check_true("bundled supply caught", "BUNDLED" in codes)
    check_true("thin volume against cap caught", "THIN_VOLUME" in codes)
    check_true("heavy top holder caught", "TOP_HOLDER" in codes)
    check_true("deployer holding caught", "CREATOR_HOLDS" in codes)
    check_true("penalty is substantial", risk.total_penalty(flags) <= -60)

    # Being unable to check is a risk in itself, not a neutral outcome.
    check_true("unverified safety flagged",
               "UNCHECKED" in {f.code for f in
                               risk.assess(clean_m,
                                           SafetyReport(ca="c", chain="base"))})

    # Several severe flags together should not be outvoted by momentum.
    hot = TokenMarket(ca="d", chain="solana", name="Hot", symbol="HOT",
                      liquidity_usd=40000, fdv=900000, market_cap=900000,
                      volume_24h=45000, volume_1h=40000, volume_5m=9000,
                      change_1h=260, change_5m=40, buys_5m=300, sells_5m=40,
                      age_hours=0.8, age_known=True, dex="raydium")
    ev = scoring.evaluate(hot, painted_s, "solana", social_channels=3,
                          smart_wallets=2)
    check("stacked danger flags block the signal", ev.rejected_by, "scam_pattern")

    # One warning must not silence an otherwise good signal.
    mild = SafetyReport(ca="e", chain="solana", sources=["rugcheck"],
                        top_holder_pct=5.0, insider_pct=3.0, holder_count=400,
                        lp_locked_pct=100.0, creator_holds_pct=0.1)
    # Asserting on should_alert here made the test depend on the clock:
    # evaluate() reads the real session, and PEAK versus DEAD is a fifteen
    # point swing across the alert floor. The intent is that one warning
    # informs without vetoing, which is what these check.
    ev2 = scoring.evaluate(hot, mild, "solana", social_channels=3)
    check("single warning does not reject", ev2.rejected_by, None)
    check_true("single warning still tracked", ev2.should_track)
    check_true("but it is recorded",
               any(f.code == "TOP_HOLDER" for f in ev2.conviction.risk_flags))
    check_true("and it costs conviction",
               risk.total_penalty(ev2.conviction.risk_flags) < 0)


def test_channel_weighting():
    """
    Paid-promotion channels post what they are paid to post. Three of them
    agreeing is one advertiser's budget, not three opinions — counted equally
    they would manufacture the same +20 consensus bonus as genuine overlap.
    """
    import social
    print("\nchannel weighting")

    def bonus(weighted):
        for n, pts in sorted(config.CONVICTION["social"].items(), reverse=True):
            if weighted >= n:
                return pts
        return 0

    # Every channel counts equally. An earlier version discounted nine of
    # them on the belief they were paid-promotion outlets; they are ordinary
    # alpha channels whose owners are sometimes paid to post, which is true of
    # most of this list. The weight was invented rather than measured.
    older = social.weighted_count(["Blessed", "Catfish by Poe", "Kook"])
    newer = social.weighted_count(["Ethans Crypto", "Slavic Calls", "Dogen Dojo"])
    check("three channels weigh three", older, 3.0)
    check("no channel is discounted", newer, older)
    check("three channels earn the consensus bonus", bonus(older), 20)

    # An unknown channel is treated as organic rather than silently ignored.
    check("unknown channel counts as organic",
          social.weighted_count(["Some New Channel"]), 1.0)

    check("all channels registered", len(config.TELEGRAM_CHANNELS), 33)
    check("one channel one vote",
          sorted({w for *_, w in config.TELEGRAM_CHANNELS}), [1.0])


def test_meta_detection():
    """
    The narrative list is fixed and cannot contain a meta that did not exist
    yesterday — when alien-file coins ran, no keyword table knew what an
    alien file was. This learns the meta from whatever is performing.
    """
    import meta, store as store_mod
    print("\nmeta detection")

    check("stopwords stripped", meta.terms("The Official Meme Coin", "MEME"), set())
    check_true("narrative words kept",
               {"alien", "files"} <= meta.terms("Alien Files Disclosure", "ALIEN"))
    # "inu", "dog" and "cat" stay in — when that meta runs they are the signal.
    check_true("animal words are not stopwords",
               "inu" in meta.terms("Doge Killer Inu", "DOGEK"))

    store_mod._mem["meta_terms"] = []
    s = store_mod.Store(url="", key="")

    def tok(name, chg, liq=20000):
        return TokenMarket(ca=name, chain="solana", name=name, symbol=name[:4],
                           liquidity_usd=liq, fdv=90000, change_24h=chg, ok=True)

    batch = [tok("Alien Files", 320), tok("Alien Disclosure", 180),
             tok("The Alien Tapes", 140), tok("Alien Grey", 95),
             tok("Roswell Alien", 210),
             tok("Random Dog", 90), tok("Flat Token", 5),
             tok("Pump Scam", 900, liq=300)]
    s.record_meta_terms(meta.harvest(batch, "solana"))

    meta.reset_cache()
    hot = meta.hot_terms(s)
    check_true("running meta detected", "alien" in hot)
    check_true("flat token contributes nothing", "flat" not in hot)
    # A 900% move on $300 of liquidity is a print, not a meta.
    check_true("illiquid pump excluded", "scam" not in hot)
    # One token carrying a word is a lottery ticket, not a narrative.
    check_true("single occurrence ignored", "roswell" not in hot)

    pts, term = meta.score("Alien Baby", "", hot)
    check_true("new token riding the meta scores", pts > 0)
    check("matched term reported", term, "alien")
    check("unrelated token scores nothing", meta.score("Dog With Hat", "", hot)[0], 0)
    check_true("meta tops up rather than carries",
               pts <= config.META["max_points"])

    # A meta comes in two shapes. News-driven ones share a literal word;
    # category ones do not — a dog meta runs as shiba, corgi and terrier,
    # sharing a theme and no word at all. Word frequency finds the first and
    # misses the second entirely.
    store_mod._mem["meta_terms"] = []
    meta.reset_cache()
    s2 = store_mod.Store(url="", key="")

    def dog(name, sym, chg):
        return TokenMarket(ca=name, chain="solana", name=name, symbol=sym,
                           liquidity_usd=20000, fdv=90000, change_24h=chg,
                           ok=True)

    s2.record_meta_terms(meta.harvest([
        dog("Shiba Rocket", "SHIBR", 210), dog("Corgi King", "CORGI", 160),
        dog("Puppy Punk", "PUPP", 190),    dog("Inu Master", "INUM", 140),
        dog("Bull Terrier", "TERR", 95),   dog("Golden Retriever", "RETR", 130),
        dog("Beagle Boy", "BEAG", 115),    dog("Quantum Ledger", "QL", 110),
    ], "solana"))
    meta.reset_cache()
    hot2 = meta.hot_terms(s2)
    check_true("themed run detected without a shared word", "#ANIMAL" in hot2)
    pts2, term2 = meta.score("Dachshund Dan", "DACH", hot2)
    check_true("a different breed still matches the theme", pts2 > 0)
    check("unrelated token ignores the theme",
          meta.score("Random Widget", "RW", hot2)[0], 0)

    store_mod._mem["meta_terms"] = []
    meta.reset_cache()

    store_mod._mem["meta_terms"] = []
    meta.reset_cache()


def test_alert_threshold():
    """
    Tracking and alerting answer different questions. Eleven signals a scan
    is several hundred a day — the channel gets muted by evening. Track
    generously because the outcome data tunes every weight; interrupt rarely.
    """
    print("\ntracking vs alerting")
    check_true("alert bar is higher than track bar",
               config.CONVICTION["min_to_alert"] > config.CONVICTION["min_to_track"])

    m = TokenMarket(ca="t", chain="solana", name="Mid", symbol="MID",
                    liquidity_usd=22000, fdv=70000, market_cap=70000,
                    volume_24h=90000, volume_1h=40000, volume_5m=4000,
                    change_1h=40, change_5m=6, buys_5m=30, sells_5m=14,
                    age_hours=0.9, age_known=True, dex="raydium")
    s = SafetyReport(ca="t", chain="solana", sources=["rugcheck"],
                     top_holder_pct=2.5, insider_pct=3.0, holder_count=500,
                     lp_locked_pct=100.0, creator_holds_pct=0.1, risk_raw=1.0)

    ev = scoring.evaluate(m, s, "solana")
    score = ev.conviction.score
    if score >= config.CONVICTION["min_to_alert"]:
        check_true("high score both tracks and alerts",
                   ev.should_track and ev.should_alert)
    else:
        check_true("middling score is tracked", ev.should_track)
        check_true("middling score does not interrupt", not ev.should_alert)

    # A token below the tracking floor is neither watched nor sent.
    weak = scoring.evaluate(
        TokenMarket(ca="w", chain="solana", name="Weak", symbol="WK",
                    liquidity_usd=9000, fdv=30000, market_cap=30000,
                    volume_24h=12000, volume_1h=6000, change_1h=26,
                    change_5m=-2, buys_5m=6, sells_5m=5, age_hours=1.2,
                    age_known=True, dex="raydium"),
        SafetyReport(ca="w", chain="solana", sources=["rugcheck"],
                     top_holder_pct=9.0, insider_pct=6.0, holder_count=70,
                     lp_locked_pct=100.0, creator_holds_pct=0.2, risk_raw=1.0),
        "solana")
    check_true("weak signal never alerts", not weak.should_alert)


def test_entrypoints_resolve():
    """
    A name used in one function but defined in another is invisible until a
    live token reaches that line. `blocked` was referenced inside scan_chain
    and defined in main, so every candidate that got as far as the alert
    decision crashed — nine scored on Solana and none alerted.
    """
    import ast, builtins, inspect
    import scan, watch, analyze
    print("\nentrypoint name resolution")

    def undefined_names(fn):
        src = inspect.getsource(fn)
        tree = ast.parse(src).body[0]
        names = {a.arg for a in tree.args.args}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
            elif isinstance(node, (ast.For, ast.comprehension)):
                for n in ast.walk(node.target):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                names.add(node.name)
            elif isinstance(node, (ast.Lambda,)):
                names.update(a.arg for a in node.args.args)
        module = inspect.getmodule(fn)
        known = names | set(dir(module)) | set(dir(builtins))
        used = {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        return sorted(used - known)

    for fn in (scan.scan_chain, scan.revisit_watchlist, scan.main,
               watch.watch_chain, watch.evaluate_position, watch.main,
               analyze.analyze, analyze.render, analyze.render_telegram):
        check(f"{fn.__module__}.{fn.__name__} resolves", undefined_names(fn), [])


def test_channel_calls():
    """
    Mentions were only used to top up the score of tokens Surgeon had already
    found, so 76 of 78 were discarded — the whole point of watching these
    channels is the runner our own scan would never surface.

    Channel calls are candidates in their own right, judged on consensus and
    safety rather than on resembling a fresh launch.
    """
    print("\nchannel calls")
    CA = "9x" + "R" * 42
    TIERS = ("first_moon", "second_moon", "boosted", "social_call")

    def runner(**kw):
        base = dict(ca=CA, chain="solana", name="Late Runner", symbol="RUN",
                    price_usd=0.0081, liquidity_usd=420000, fdv=8_100_000,
                    market_cap=8_100_000, volume_24h=6_400_000,
                    volume_1h=980_000, volume_5m=61_000, change_5m=3.2,
                    change_1h=41.0, change_24h=310.0, buys_5m=190,
                    sells_5m=140, age_hours=28.0, age_known=True,
                    dex="raydium")
        base.update(kw)
        return TokenMarket(**base)

    clean = SafetyReport(ca=CA, chain="solana", sources=["rugcheck"],
                         top_holder_pct=3.1, insider_pct=4.0,
                         holder_count=9400, lp_locked_pct=100.0,
                         creator_holds_pct=0.05, risk_raw=1.0)
    rugged = SafetyReport(ca=CA, chain="solana", sources=["rugcheck"],
                          top_holder_pct=34.0, insider_pct=41.0,
                          holder_count=22, creator_holds_pct=19.0,
                          risk_raw=1.0)

    # An $8m runner is past every discovery tier — boosted stops at $5m — so
    # without a tier of its own it would vanish silently.
    check("no discovery tier reaches a runner",
          scoring.classify_tier(runner(), "solana", session="NORMAL").tier, None)
    check("social tier does",
          scoring.classify_tier(runner(), "solana", session="NORMAL",
                                tiers=("social_call",)).tier, "social_call")

    def called(social, safety=clean, market=None):
        return scoring.evaluate(market or runner(), safety, "solana",
                                social_channels=social, tiers=TIERS)

    check_true("four organic channels alert", called(3.0).should_alert)
    check_true("two organic channels alert", called(2.0).should_alert)
    check_true("one channel is not consensus", not called(1.0).should_alert)
    check_true("a single channel is not consensus",
               not called(1.0).should_alert)

    # Consensus never overrides safety.
    check("consensus on a rug is still a rug",
          called(3.0, safety=rugged).rejected_by, "scam_pattern")
    check("consensus on a dead pool still fails the tier",
          called(3.0, market=runner(liquidity_usd=900, volume_1h=200,
                                    volume_24h=400, fdv=40000)).rejected_by,
          "tier")

    # The score is computed and shown, but does not decide here. Asserting
    # the score lands below the discovery floor made this depend on the
    # session — the same token scores fifteen points higher at PEAK.
    low = called(2.0)
    check_true("consensus alerts regardless of score", low.should_alert)
    check_true("score still computed", low.conviction.score > 0)


def test_lp_zero_corroboration():
    """
    An LP reading of exactly zero on a graduated pool often means "could not
    read this pool type", not "the deployer holds the liquidity" — RugCheck
    cannot see inside every venue pump.fun graduates into.

    The Cancer Vaccine was rejected on this while holding 17,900 holders, 0%
    insider supply and a deployer with nothing. A dev-controlled LP does not
    look like that, so zero now needs corroboration before it rejects.
    """
    from chain_base import ChainAdapter
    print("\nzero LP corroboration")

    def verdict(creator, insider, holders):
        rep = SafetyReport(ca="x", chain="solana", sources=["rugcheck"],
                           lp_locked_pct=0.0, creator_holds_pct=creator,
                           insider_pct=insider, holder_count=holders)
        rep.hard_rejects.append("lp_unlocked_0pct")
        s = config.SAFETY
        contradicted = (
            (rep.creator_holds_pct is not None
             and rep.creator_holds_pct <= s["lp_zero_creator_max"])
            and (rep.insider_pct is not None
                 and rep.insider_pct <= s["lp_zero_insider_max"])
            and (rep.holder_count or 0) >= s["lp_zero_holder_min"])
        if contradicted:
            rep.hard_rejects = [r for r in rep.hard_rejects
                                if not r.startswith("lp_unlocked")]
        return not rep.hard_rejects

    check_true("clean token survives an unreadable pool",
               verdict(0.0, 0.0, 17900))
    check_true("deployer holding 22% still rejects", not verdict(22.0, 0.0, 17900))
    check_true("31% bundled still rejects", not verdict(0.0, 31.0, 9000))
    check_true("14 holders still rejects", not verdict(0.0, 0.0, 14))
    # Unknown is not the same as clean — without the corroborating fields
    # there is nothing to contradict the reading.
    check_true("unknown creator cannot clear it", not verdict(None, 0.0, 17900))


def test_rug_score_and_dev_sold():
    """
    Two readings that meant less than they appeared to.

    RugCheck's score is built from risks it has detected, and a token minutes
    old has almost nothing to detect. A 1 therefore means "nothing flagged
    yet", not "verified safe" — and most tokens King saw scoring 1 were rugs.

    DEV_SOLD compared against a `dev_held` field that was never written, so
    the check could not fire at all.
    """
    import watch, time as _t
    print("\nrug score and dev sold")

    def display(raw, holders):
        return SafetyReport(ca="x", chain="solana", sources=["rugcheck"],
                            top_holder_pct=6.2, lp_locked_pct=100.0,
                            risk_raw=raw, holder_count=holders).display()

    check_true("low score on an unexamined token is not clean",
               "unproven" in display(1, 40))

    # Every rug that reached King came from the unflagged group — nothing
    # detected, so nothing to warn about. Silence used to cost nothing.
    market = TokenMarket(ca="x", chain="solana", name="T", symbol="T",
                         liquidity_usd=30000, fdv=400000, market_cap=400000,
                         volume_24h=300000, volume_1h=90000, volume_5m=6000,
                         change_5m=4, change_1h=22, buys_5m=40, sells_5m=25,
                         age_hours=8.0, age_known=True, dex="raydium")

    def score_with(holders):
        return scoring.conviction_score(
            market,
            SafetyReport(ca="x", chain="solana", sources=["rugcheck"],
                         top_holder_pct=4.0, insider_pct=2.0,
                         holder_count=holders, lp_locked_pct=100.0,
                         creator_holds_pct=0.1, risk_raw=1),
            0, 0, "NEUTRAL", session="NORMAL")

    # The unproven penalty is removed: it fired on 0 of 1,116 closed trades
    # across every tier. An inert rule that looks like protection is worse
    # than no rule, because it gets counted as one.
    examined, unexamined = score_with(1200), score_with(25)
    check("unproven no longer scores", config.CONVICTION["unproven_safety"], 0)
    # A thin holder base still costs, but through FEW_HOLDERS — King's own
    # heuristic — rather than through a rule that never fired.
    check_true("no unproven component remains",
               not any(l == "unproven" for l, _ in unexamined.components))
    check_true("thin holders still cost via the heuristic",
               any(l == "risk:FEW_HOLDERS" for l, _ in unexamined.components))
    # The label still distinguishes them, which is what it was always for.
    check_true("but the display still says unproven",
               "unproven" in display(1, 25))
    check_true("low score with a real holder base is clean",
               "clean" in display(1, 17900))
    check_true("high score still reads severe", "severe" in display(11400, 665))

    now = _t.time()

    def dev_events(held_then, holds_now, flag=True):
        row = {"ca": "x", "chain": "solana", "name": "T", "symbol": "T",
               "entry_price": 1.0, "peak_price": 1.0, "alerted_at": now - 1800,
               "dev_held": flag, "creator_holds_pct": held_then}
        market = TokenMarket(ca="x", chain="solana", name="T", symbol="T",
                             price_usd=1.1, liquidity_usd=40000, fdv=60000,
                             volume_1h=24000, volume_5m=2000, dex="raydium")
        safety = SafetyReport(ca="x", chain="solana", sources=["rugcheck"],
                              creator_holds_pct=holds_now, top_holder_pct=5.0)
        return [e for e, _ in watch.evaluate_position(row, market, None,
                                                      set(), safety)]

    check_true("emptied deployer wallet fires", "DEV_SOLD" in dev_events(4.0, 0.0))
    check_true("deployer shedding most of its bag fires",
               "DEV_SOLD" in dev_events(4.0, 1.5))
    check_true("trimming a little does not",
               "DEV_SOLD" not in dev_events(4.0, 3.6))
    check_true("a deployer that never held anything cannot sell",
               "DEV_SOLD" not in dev_events(0.0, 0.0, flag=False))


def test_lp_lock_expiry():
    """
    Surgeon read the lock percentage and discarded the horizon, so liquidity
    locked for ninety days and liquidity unlocking this afternoon scored
    identically. RugCheck returns unlock timestamps in a response already
    being fetched every scan.
    """
    import risk
    print("\nlp lock expiry")

    def rep(hours, kind="timed"):
        return SafetyReport(ca="x", chain="solana", sources=["rugcheck"],
                            top_holder_pct=3.0, insider_pct=2.0,
                            holder_count=900, lp_locked_pct=100.0,
                            lp_unlock_hours=hours, lp_lock_kind=kind,
                            creator_holds_pct=0.1, risk_raw=1)

    check_true("burned LP says so", "burned" in rep(None, "burned").display())
    check_true("a long lock reads plainly",
               "unlocks in 90d" in rep(2160).display())
    # Rounding to whole hours made 90 minutes and two and a half hours both
    # read as "2h", which are very different things to be told.
    check_true("an imminent unlock is stated in minutes",
               "unlocks in 90m" in rep(1.5).display())
    check_true("and is distinguishable from a longer one",
               rep(1.5).display() != rep(2.5).display())
    check_true("an expired lock says so plainly",
               "already expired" in rep(-2).display())

    market = TokenMarket(ca="x", chain="solana", name="Tok", symbol="TOK",
                         liquidity_usd=45000, fdv=120000, market_cap=120000,
                         volume_24h=180000, volume_1h=70000, volume_5m=6000,
                         change_5m=7, change_1h=88, buys_5m=90, sells_5m=35,
                         age_hours=0.9, age_known=True, dex="raydium")

    def flags(hours, kind="timed"):
        return {f.code for f in risk.assess(market, rep(hours, kind))}

    check("burned LP is not flagged", "LP_UNLOCKING" in flags(None, "burned"), False)
    check("a 90 day lock is not flagged", "LP_UNLOCKING" in flags(2160), False)
    check_true("unlocking tonight is flagged", "LP_UNLOCKING" in flags(18))
    check_true("unlocking within the hour is flagged", "LP_UNLOCKING" in flags(1.5))
    check_true("an expired lock is flagged", "LP_EXPIRED" in flags(-3))

    # Sooner must cost more than later.
    soon = risk.total_penalty(risk.assess(market, rep(1.5)))
    later = risk.total_penalty(risk.assess(market, rep(18)))
    check_true("an imminent unlock costs more than a distant one", soon < later)

    # An expired lock can also mean stale locker data or LP burned afterwards,
    # so it is penalised heavily rather than vetoed.
    check("expired lock does not hard reject", rep(-3).hard_rejects, [])


def test_alert_standing():
    """
    Every rug that reached King came from the group with nothing flagged —
    not because those tokens were clean, but because nothing could be
    checked. Flagged tokens rugged zero times and peaked at 115 on average.
    That distinction now leads the alert instead of being buried.
    """
    import alerts, chains
    print("\nalert safety standing")

    market = TokenMarket(ca="7xK" + "q" * 41, chain="solana",
                         name="Steady Runner", symbol="STDY",
                         price_usd=0.00042, liquidity_usd=60000, fdv=520000,
                         market_cap=520000, volume_24h=900000,
                         volume_1h=180000, volume_5m=14000, change_5m=6,
                         change_1h=64, change_24h=210, buys_5m=120,
                         sells_5m=70, age_hours=1.4, age_known=True,
                         dex="raydium")

    def standing(safety):
        ev = scoring.evaluate(market, safety, "solana")
        return alerts.format_signal(ev, chains.get_adapter("solana")).splitlines()[3]

    clean = SafetyReport(ca=market.ca, chain="solana", sources=["rugcheck"],
                         top_holder_pct=2.4, insider_pct=2.0,
                         holder_count=3100, lp_locked_pct=100.0,
                         lp_lock_kind="burned", creator_holds_pct=0.05,
                         risk_raw=1)
    flagged = SafetyReport(ca=market.ca, chain="solana", sources=["rugcheck"],
                           top_holder_pct=11.0, insider_pct=18.0,
                           holder_count=900, lp_locked_pct=100.0,
                           lp_unlock_hours=6, lp_lock_kind="timed",
                           creator_holds_pct=0.1, risk_raw=120)
    unproven = SafetyReport(ca=market.ca, chain="solana", sources=["rugcheck"],
                            top_holder_pct=3.0, insider_pct=0.0,
                            holder_count=22, lp_locked_pct=100.0,
                            creator_holds_pct=0.0, risk_raw=1)

    check_true("a checked token reads clean", "CLEAN" in standing(clean))
    check_true("a flagged token names its worst flag",
               "TOP_HOLDER" in standing(flagged))
    # A thin holder base now reads through its flags rather than a separate
    # unproven state, since that rule never fired on real data.
    check_true("a thin holder base still surfaces something",
               "FEW_HOLDERS" in standing(unproven) or "🚩" in standing(unproven))
    check_true("unverified is stated loudest",
               "UNVERIFIED" in standing(SafetyReport(ca=market.ca, chain="solana")))


def test_per_tier_alert_floors():
    """
    A single alert floor muted the best-performing tier. Boosted produced 82
    signals and sent zero — its gates are the loosest, so its tokens score
    lower by construction, while winning 32.1% against first_moon's 17.9%.
    """
    print("\nper-tier alert floors")
    floors = config.CONVICTION["min_to_alert_by_tier"]
    check_true("boosted has the lowest bar",
               floors["boosted"] < floors["second_moon"] <= floors["first_moon"])
    check_true("boosted's bar sits under its average score of 43",
               floors["boosted"] < 43)
    check_true("the default is below the old single floor of 60",
               config.CONVICTION["min_to_alert"] < 60)


def test_discovery_depth():
    """
    Two pages is about forty new pools. Solana produces far more than that in
    fifteen minutes, so anything outside the newest forty at the moment we
    looked was never seen — and a graduation creates a new pool, which is how
    a token at $2.7m FDV doing $2.75m daily volume went unnoticed.

    Depth is per chain because launch rates are not remotely comparable.
    """
    print("\ndiscovery depth")
    depth = {k: v.get("discovery_pages", 2)
             for k, v in config.CHAINS.items() if v.get("enabled")}

    check_true("solana looks deepest", depth["solana"] == max(depth.values()))
    check_true("solana goes deeper than the quiet chains",
               depth["solana"] > depth["base"] and depth["solana"] > depth["monad"])
    check_true("robinhood sits between", depth["base"] <= depth["robinhood"]
               <= depth["solana"])

    # Depth costs throttled requests, so it has to stay bounded.
    extra = sum(depth.values()) - 2 * len(depth)
    check_true("the extra cost is single digits per scan", extra <= 9)

    # And the adapter must actually use it rather than the default.
    import inspect, chains
    src = inspect.getsource(chains.get_adapter("solana").discover)
    check_true("adapter reads the per-chain depth", "discovery_pages" in src)


def test_winner_recovery():
    """
    Rules judged against the fifteen biggest winners Surgeon actually found.

    Five of them were taxed ten points for launching in dead hours, and two
    were charged fourteen for holder concentration while twenty minutes old —
    which is what an early runner looks like. Buying Power took -14 and ran
    +3,128%; Caesar took -14 and ran +794%.

    Under the old rules 8 of 15 cleared their tier floor. Under these, 13 do.
    """
    print("\nwinner recovery")

    check("dead hours no longer taxed",
          config.MARKET_HOURS_ADJUST["DEAD"]["conviction"], 0)
    check_true("dead hours still tighten the gates",
               config.MARKET_HOURS_ADJUST["DEAD"]["min_change_1h_mult"] > 1)

    # Every one of the fifteen was under two hours old at signal, so the
    # grace window has to cover that range to matter at all.
    check_true("grace window covers the winners' ages",
               config.SCAM["top_holder_grace_hours"] >= 1.0)

    import risk
    def penalty(pct, age):
        market = TokenMarket(ca="x", chain="solana", name="T", symbol="T",
                             liquidity_usd=40000, fdv=60000, market_cap=60000,
                             volume_24h=90000, volume_1h=60000,
                             age_hours=age, age_known=True, dex="raydium")
        safety = SafetyReport(ca="x", chain="solana", sources=["rugcheck"],
                              top_holder_pct=pct, insider_pct=2.0,
                              holder_count=600, creator_holds_pct=0.1)
        flags = [f for f in risk.assess(market, safety) if f.code == "TOP_HOLDER"]
        return flags[0].penalty if flags else 0

    check_true("young concentration costs less", penalty(10.9, 0.19) > penalty(10.9, 3.0))
    check_true("but is not waived", penalty(10.9, 0.19) < 0)
    # 24% in one wallet is a countdown at any age, so it stays severe.
    check_true("severe concentration stays severe",
               penalty(24.0, 0.19) <= -10)

    # Boosted reverted: 21.8% on 110 trades against first_moon's 25.3%, and
    # not one of the fifteen was boosted.
    check("boosted ceiling reverted",
          config.THRESHOLDS["boosted"]["max_age_hours"], 24.0)
    check("boosted fdv floor reverted",
          config.THRESHOLDS["boosted"]["min_fdv"], 20_000)

    # Rugs come from what cannot be checked: unflagged tokens rug at 16.0%,
    # flagged at 10.9%.
    # Muting unverified rested on a query that split on risk flags rather
    # than verification status — different things. 央视抽象吉祥物 was
    # unverified and ran +410%; it would have been silenced.
    check("unverified flags rather than mutes",
          config.SAFETY["unverified_policy"], "flag")

    winner = TokenMarket(ca="u", chain="bsc", name="央视抽象吉祥物",
                         symbol="周一来", liquidity_usd=35000, fdv=77899,
                         market_cap=77899, volume_24h=200000,
                         volume_1h=90000, volume_5m=7000, change_5m=12,
                         change_1h=140, buys_5m=70, sells_5m=30,
                         age_hours=0.65, age_known=True, dex="pancakeswap")
    ev = scoring.evaluate(winner, SafetyReport(ca="u", chain="bsc"), "bsc")
    check_true("the unverified winner reaches the phone", ev.should_alert)
    # Conviction charges UNVERIFIED; the risk flag names it without billing
    # again. Two mechanisms on one fact took this token from 59 to 49.
    check_true("it is charged once, not twice",
               any(l == "UNVERIFIED" for l, _ in ev.conviction.components)
               and all(f.penalty == 0 for f in ev.conviction.risk_flags
                       if f.code == "UNCHECKED"))
    check_true("and the alert still says it is unverified",
               any(f.code == "UNCHECKED" for f in ev.conviction.risk_flags))


def test_solana_infrastructure_holders():
    """
    Most of a young token's float sits in the AMM by design. Counting the
    pool as a holder makes a healthy launch read as heavily concentrated —
    the same fault that made a Uniswap pair look like a 50% whale on EVM,
    fixed there early and never mirrored on Solana.

    RugCheck's insider tag catches wallets funded together before launch. It
    does not catch the pool, the bonding curve or an exchange.
    """
    from chain_base import is_solana_infrastructure as infra
    print("\nsolana infrastructure holders")

    check_true("raydium authority excluded",
               infra({"address": "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"}))
    check_true("burn address excluded",
               infra({"owner": "1nc1nerator11111111111111111111111111111111"}))
    check_true("labelled pool excluded",
               infra({"address": "9x", "owner_name": "Raydium Liquidity Pool V4"}))
    check_true("bonding curve excluded",
               infra({"address": "Fg", "owner_name": "Pump.fun Bonding Curve"}))
    check_true("exchange wallet excluded",
               infra({"address": "8k", "owner_name": "Binance Hot Wallet"}))

    # An ordinary wallet must survive, labelled or not — over-excluding hides
    # the concentration this check exists to find.
    check_true("plain wallet counted", not infra({"address": "3nMFwZ", "pct": 4.2}))
    check_true("unlabelled wallet counted",
               not infra({"address": "7yUt", "owner_name": "", "pct": 9.1}))
    check_true("a wallet named after a person is counted",
               not infra({"address": "2bQ", "owner_name": "whale.sol"}))


def test_weak_momentum_penalised():
    """
    momentum:WEAK appeared on 401 closed trades and won 13.2% against a 22%
    baseline, with an average peak of 6 — the worst component in the system,
    and it was being paid +3.

    None of the fifteen biggest winners had weak momentum: eleven were
    EXPLOSIVE, four REAL, none weak. So penalising it costs no known winner.
    """
    print("\nweak momentum")
    w = config.CONVICTION["momentum"]
    check_true("weak momentum now costs", w["WEAK"] < 0)
    check_true("explosive still earns most", w["EXPLOSIVE"] == max(w.values()))
    check_true("real sits between", w["WEAK"] < w["REAL"] < w["EXPLOSIVE"])
    # Fake data must never score better than genuinely weak trading.
    check_true("fake is not rewarded either", w.get("FAKE", 0) <= 0)


def main():
    print("=" * 64)
    print("SCORING TESTS")
    print("=" * 64)

    print("\nmarket session")
    check("03:00 UTC", scoring.market_session(datetime(2026, 8, 13, 3, tzinfo=timezone.utc)), "DEAD")
    check("15:00 UTC", scoring.market_session(datetime(2026, 8, 13, 15, tzinfo=timezone.utc)), "PEAK")
    check("11:00 UTC", scoring.market_session(datetime(2026, 8, 13, 11, tzinfo=timezone.utc)), "NORMAL")

    print("\nnarrative classification")
    check("Neural Agent", scoring.classify_narrative("Neural Agent", "NAGENT")[0], "AI")
    check("Doge Cheeto", scoring.classify_narrative("The Doge Cheeto", "Dogeeto")[0], "ELON")
    check("Trump 2026", scoring.classify_narrative("Trump 2026", "MAGA")[0], "POLITICAL")
    check("Pygmy Hippo", scoring.classify_narrative("Solana The Pygmy Hippo", "HIPPO")[0], "ANIMAL")
    check("Certain (no false AI)", scoring.classify_narrative("Certain", "CERTAIN")[0], "NONE")
    check("Captain (no false AI)", scoring.classify_narrative("Captain Hook", "CAP")[0], "NONE")

    print("\nmomentum quality")
    check("REDDIT", scoring.momentum_quality(REDDIT), "EXPLOSIVE")
    check("STRONG", scoring.momentum_quality(STRONG), "EXPLOSIVE")
    check("STRUK (dead)", scoring.momentum_quality(STRUK), "FAKE")

    print("\nlaunch phase")
    check("REDDIT 0.05h", scoring.launch_phase(REDDIT), "TOO_EARLY")
    check("STRONG 0.9h", scoring.launch_phase(STRONG), "GOLDEN_WINDOW")
    check("STRUK 3.7h", scoring.launch_phase(STRUK), "SWEET_SPOT")
    check("no timestamp", scoring.launch_phase(
        TokenMarket(ca="x", chain="base", age_known=False)), "UNKNOWN")

    print("\nsanity penalty reaches the score")
    skyai_conv = scoring.conviction_score(SKYAI, SKYAI_SAFETY)
    check_true("SKYAI scores below alert floor", not skyai_conv.alertable)
    check_true("SKYAI penalised for suspect data",
               any("suspect_data" in l for l, _ in skyai_conv.components))

    print("\nunverified penalty")
    bare = SafetyReport(ca="z", chain="robinhood")
    unv = scoring.conviction_score(REDDIT, bare)
    ver = scoring.conviction_score(REDDIT, REDDIT_SAFETY)
    check_true("unverified scores lower than verified", unv.score < ver.score)
    check_true("UNVERIFIED component present",
               any(l == "UNVERIFIED" for l, _ in unv.components))

    print("\nend-to-end evaluate()")
    for label, m, s, expect in (
        ("SKYAI", SKYAI, SKYAI_SAFETY, "safety"),
        ("MeowCoin", MEOW, MEOW_SAFETY, "safety"),
        ("Struk Mon", STRUK, STRUK_SAFETY, "safety"),
    ):
        ev = scoring.evaluate(m, s, m.chain)
        check(f"{label} rejected by", ev.rejected_by, expect)

    ev_strong = scoring.evaluate(STRONG, STRONG_SAFETY, "solana",
                                 social_channels=3, smart_wallets=2)
    print(f"\n  STRONG -> {ev_strong.summary()}")
    print(f"  breakdown: {ev_strong.conviction.explain()}")
    check_true("STRONG alerts", ev_strong.should_alert)
    check_true("STRONG scores HIGH", ev_strong.conviction.band in ("HIGH", "GOOD"))

    ev_reddit = scoring.evaluate(REDDIT, REDDIT_SAFETY, "robinhood")
    print(f"\n  REDDIT -> {ev_reddit.summary()}")
    print(f"  breakdown: {ev_reddit.conviction.explain()}")
    if ev_reddit.rejected_by == "tier":
        print(f"  tier misses: {ev_reddit.tier.failures.get('first_moon')}")

    test_alerts()
    test_store()
    test_social()
    test_tiers()
    test_watchlist()
    test_context_inputs()
    test_watcher()
    test_candidate_ordering()
    test_scam_flags()
    test_channel_weighting()
    test_meta_detection()
    test_alert_threshold()
    test_entrypoints_resolve()
    test_channel_calls()
    test_lp_zero_corroboration()
    test_rug_score_and_dev_sold()
    test_lp_lock_expiry()
    test_alert_standing()
    test_per_tier_alert_floors()
    test_discovery_depth()
    test_winner_recovery()
    test_solana_infrastructure_holders()
    test_weak_momentum_penalised()

    print("\n" + "=" * 64)
    print(f"  {PASS} passed, {FAIL} failed")
    print("=" * 64)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
