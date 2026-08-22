"""
Surgeon v2 — central configuration.

Everything tunable lives here. Chain adapters read from CHAINS,
the scoring core reads from THRESHOLDS / NARRATIVES / SMART_MONEY.

Values marked VERIFY are resolved by running discover_chain_ids.py once.
"""

import os

# ── SECRETS (set as GitHub Actions secrets / env vars) ────────────
HELIUS_API_KEY      = os.getenv("HELIUS_API_KEY", "")
GOPLUS_APP_KEY      = os.getenv("GOPLUS_APP_KEY", "")      # optional, raises rate limit
GOPLUS_APP_SECRET   = os.getenv("GOPLUS_APP_SECRET", "")   # optional
# Sending is opt-in. A missing or mistyped flag must fail closed, not open.
LIVE_ALERTS         = os.getenv("SURGEON_LIVE", "").lower() == "true"
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL        = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY        = os.getenv("SUPABASE_KEY", "")

# ── HTTP ──────────────────────────────────────────────────────────
HTTP_TIMEOUT   = 12
HTTP_RETRIES   = 2
HTTP_BACKOFF   = 1.5
USER_AGENT     = "surgeon/2.0"

# ── CHAIN REGISTRY ────────────────────────────────────────────────
# enabled=False chains are registered but skipped by scanners.
# Turn one on and Surgeon starts covering it. No other code changes.
CHAINS = {
    "solana": {
        "display":         "Solana",
        "kind":            "svm",
        "dexscreener_id":  "solana",
        "geckoterminal_id": "solana",
        "discovery_pages":  6,
        "enabled":         True,
        "explorer":        "https://solscan.io/token/{ca}",
        "chart":           "https://dexscreener.com/solana/{ca}",
        "native":          "SOL",
        "addr_regex":      r"^[1-9A-HJ-NP-Za-km-z]{32,44}$",
    },
    "robinhood": {
        "display":         "Robinhood Chain",
        "kind":            "evm",
        "dexscreener_id":  "robinhood",     # resolved
        "geckoterminal_id": "robinhood",    # resolved
        "discovery_pages":  3,
        "goplus_chain_id": "4663",          # resolved
        "blockscout":      "https://robinhoodchain.blockscout.com",  # official explorer
        "enabled":         True,
        "explorer":        "https://explorer.robinhood.com/token/{ca}",
        "chart":           "https://dexscreener.com/robinhood/{ca}",
        "native":          "ETH",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    "base": {
        "display":         "Base",
        "kind":            "evm",
        "dexscreener_id":  "base",
        "geckoterminal_id": "base",
        "discovery_pages":  2,
        "goplus_chain_id": "8453",
        "blockscout":      "https://base.blockscout.com",
        "enabled":         True,
        "explorer":        "https://basescan.org/token/{ca}",
        "chart":           "https://dexscreener.com/base/{ca}",
        "native":          "ETH",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    "bsc": {
        "display":         "BNB Chain",
        "kind":            "evm",
        "dexscreener_id":  "bsc",
        "geckoterminal_id": "bsc",
        "discovery_pages":  2,
        "goplus_chain_id": "56",
        "blockscout":      None,
        "enabled":         True,
        "explorer":        "https://bscscan.com/token/{ca}",
        "chart":           "https://dexscreener.com/bsc/{ca}",
        "native":          "BNB",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
    "monad": {
        "display":         "Monad",
        "kind":            "evm",
        "dexscreener_id":  "monad",         # resolved via geckoterminal
        "geckoterminal_id": "monad",        # resolved
        "discovery_pages":  2,
        "goplus_chain_id": "143",           # resolved
        "blockscout":      None,
        "enabled":         True,
        "explorer":        "https://monadexplorer.com/token/{ca}",
        "chart":           "https://dexscreener.com/monad/{ca}",
        "native":          "MON",
        "addr_regex":      r"^0x[a-fA-F0-9]{40}$",
    },
}

def enabled_chains():
    return [k for k, v in CHAINS.items() if v.get("enabled")]


# ── ENTRY THRESHOLDS ──────────────────────────────────────────────
# Per-tier gates. Chain overrides go in CHAIN_THRESHOLD_OVERRIDES.
THRESHOLDS = {
    # Volume is gated on the last hour plus turnover, never on 24h totals.
    # For a token minutes old, "24h volume" is lifetime volume — a $50k floor
    # demanded $50k of trade in twelve minutes and rejected genuine runners.
    # 184 first_moon trades won 17.9%; 28 boosted trades won 32.1%. That is
    # evidence older tokens outperform younger ones, which justifies widening
    # boosted — it says nothing about how much momentum to demand from a young
    # one, and raising this gate to 25% blocked 83 of 96 Solana candidates.
    #
    # It is also the wrong lever mechanically: for a twenty-minute-old token,
    # "1h change" spans its whole life, so a high floor rejects anything that
    # launched, dipped and is only now turning. Turnover stays raised, since
    # it measures real activity rather than a price path.
    "first_moon": {
        "min_liquidity":   6_000,
        "min_fdv":         5_000,
        "max_fdv":       150_000,
        "min_age_hours":     0.17,   # 10min — past the instant-rug window
        "max_age_hours":     2.0,
        "min_change_1h":    15.0,
        "min_volume_1h":   4_000,
        "min_turnover_1h":   0.22,
        "min_change_5m":   -10.0,
    },
    "second_moon": {
        "min_liquidity":  20_000,
        "min_fdv":       100_000,
        "max_fdv":     3_000_000,
        "min_age_hours":     0.17,
        "max_age_hours":    12.0,
        "min_change_1h":    10.0,
        "min_volume_1h":  15_000,
        "min_turnover_1h":   0.10,
        "min_change_5m":   -10.0,
    },
    # Catch-all so a token cannot fall between tiers: first_moon stops at 2h
    # and second_moon needs $100k FDV, which left a 3h-old $60k token matching
    # nothing at all.
    # Widened on a 28-trade sample showing 32.1%. On 110 trades it came in at
    # 21.8% with the worst average close in the system (-45), below
    # first_moon's 25.3%, and not one of the fifteen biggest winners was
    # boosted. The original edge was small-sample luck; reverted.
    "boosted": {
        "min_liquidity":  10_000,
        "min_fdv":        20_000,
        "max_fdv":     5_000_000,
        "min_age_hours":     0.17,
        "max_age_hours":    24.0,
        "min_change_1h":     0.0,
        "min_volume_1h":   5_000,
        "min_turnover_1h":   0.05,
        "min_change_5m":   -15.0,
    },
    # Tokens the channels are calling. A different question entirely: not
    # "is this early enough to be worth a look" but "several people who watch
    # this full-time think it is running". A runner heading for $10m is far
    # outside every tier above — boosted stops at $5m — so a token three
    # channels are shouting about would find no tier and vanish silently.
    "social_call": {
        "min_liquidity":  15_000,
        "min_fdv":        20_000,
        "max_fdv":    50_000_000,
        "min_age_hours":     0.17,
        "max_age_hours":   168.0,     # a week
        "min_change_1h":   -20.0,     # consensus matters more than momentum
        "min_volume_1h":  10_000,
        "min_turnover_1h":   0.05,
        "min_change_5m":   -30.0,
    },
}

# Newer chains trade at a fraction of Solana's dollar sizes. REDDIT on
# Robinhood was a real 321%-in-an-hour move on $7.8k liquidity and an $8k
# FDV — invisible to Solana-calibrated floors.
CHAIN_THRESHOLD_OVERRIDES = {
    "robinhood": {
        "first_moon": {"min_liquidity": 3_000, "min_volume_1h": 1_500},
        "boosted":    {"min_liquidity": 5_000, "min_volume_1h": 2_000},
    },
    "monad": {
        "first_moon": {"min_liquidity": 3_000, "min_volume_1h": 1_500},
        "boosted":    {"min_liquidity": 5_000, "min_volume_1h": 2_000},
    },
    # 46 trades, 13% win rate, average peak +4% — Base signals barely go
    # green at all. Raised rather than disabled: the chain is not dead, our
    # bar for it was too low.
    "base": {
        "first_moon": {"min_change_1h": 45.0, "min_volume_1h": 10_000,
                       "min_turnover_1h": 0.35, "min_liquidity": 12_000},
        "boosted":    {"min_change_1h": 15.0, "min_volume_1h": 8_000,
                       "min_turnover_1h": 0.12},
    },
}

def thresholds_for(chain: str, tier: str) -> dict:
    base = dict(THRESHOLDS[tier])
    base.update(CHAIN_THRESHOLD_OVERRIDES.get(chain, {}).get(tier, {}))
    return base


# ── SAFETY GATES ──────────────────────────────────────────────────
SAFETY = {
    "max_top_holder_pct":   20.0,   # reject above
    "max_top10_pct":        60.0,
    "min_lp_locked_pct":    80.0,   # graduated pools only
    # An LP reading of exactly zero is treated as unreadable rather than
    # unlocked when every other holder signal contradicts it.
    "lp_zero_creator_max":   0.5,
    "lp_zero_insider_max":   2.0,
    "lp_zero_holder_min":  500,
    "max_buy_tax_pct":      10.0,   # EVM
    "max_sell_tax_pct":     10.0,   # EVM
    "rugcheck_raw_block":   500,    # Solana: raw score above this = block
    # A low score on a token with no holder base means the checks had nothing
    # to examine, not that the token is safe.
    "rug_score_min_holders": 300,
    # A lock expiring within this window is not protection. Flagged rather
    # than rejected — plenty of real projects run short rolling locks.
    "lp_min_lock_hours":    24.0,
    "reject_on_honeypot":   True,
    "reject_on_mint_auth":  True,
    "reject_on_freeze":     True,
    "reject_creator_rug_history": True,
    # SKYAI on BSC passed with 1 holder and the creator holding 100% of supply,
    # because top_holder_pct was unavailable and nothing else was checked.
    "max_creator_holds_pct": 20.0,
    "min_holder_count":      10,
    "reject_unverified_contract_if_thin": True,   # unverified + <50 holders
    # If safety data can't be fetched, do we still alert?
    # True = alert but clearly label the gap. Never silently show 0%.
    "alert_on_partial":     True,
    # A token no safety source could answer for is UNVERIFIED, not PASS.
    # "flag"  = still alert, label it loudly, heavy conviction penalty
    # "block" = never alert
    # Was "flag". Unflagged tokens rug at 16.0% against 10.9% for flagged
    # ones — the rugs come from tokens where nothing could be seen, not from
    # tokens where something was. A token no safety source could answer for
    # is still tracked and graded, but no longer interrupts.
    "unverified_policy":    "track_only",
}

# ── SCAM HEURISTICS ───────────────────────────────────────────────
# Trader-supplied tells, far tighter than the entry gates. Applied as
# conviction penalties rather than rejects — as rejects they would silence
# the scanner, and a token collecting several of them falls below the alert
# floor on arithmetic anyway.
SCAM = {
    # Flip to False to score exactly as before these were added. Nothing
    # else changes — the checks are additive, not a rewrite.
    "enabled":            True,
    "top_holder_pct":        3.5,   # single wallet above this is a warning
    # Inside this window the penalty is halved: a holder base takes hours to
    # spread, and two of the biggest winners were charged full price for it.
    "top_holder_grace_hours": 1.0,
    "min_volume_to_mcap":    0.80,  # 24h volume under this share of cap
    "bundled_pct":          15.0,   # supply held by launch-bundled wallets
    "min_holders":          50,
    "creator_holds_pct":     2.0,
    # One warning is survivable. Three severe ones together is a pattern.
    "max_danger_flags":      3,
}

# ── MARKET DATA SANITY ────────────────────────────────────────────
# Fresh pairs routinely report garbage: infinite-looking price changes,
# billion-dollar FDV sitting on $16k of liquidity. Treat these as bad data,
# not as signals.
SANITY = {
    "max_fdv_liq_ratio":  500,      # FDV more than 500x liquidity = fake supply
    "max_abs_change_pct": 50_000,   # anything beyond this is a data artefact
    "min_liquidity_usd":  1_000,    # below this nothing is tradeable
    "unknown_age_hours":  999.0,    # sentinel used when pairCreatedAt is absent
}

# ── MARKET HOURS (UTC) ────────────────────────────────────────────
MARKET_HOURS = {
    "peak": (13, 21),   # US open + EU evening overlap
    "dead": (2, 8),
}
MARKET_HOURS_ADJUST = {
    "PEAK":   {"min_change_1h_mult": 0.75, "min_volume_mult": 0.6, "conviction": +5},
    "NORMAL": {"min_change_1h_mult": 1.00, "min_volume_mult": 1.0, "conviction":  0},
    # Penalty removed. Five of the fifteen biggest winners took DEAD-10 —
    # Bullballs (+4,332%), Caesar (+794%), Fatal Boner (+832%), Burpcoin,
    # Onigiricoin. Ten points each, on tokens that launched overnight and ran
    # anyway. The gates still tighten in dead hours; the score no longer
    # taxes a token for the clock it launched on.
    "DEAD":   {"min_change_1h_mult": 2.00, "min_volume_mult": 2.0, "conviction": 0},
}

# ── CONVICTION SCORING ────────────────────────────────────────────
CONVICTION = {
    "momentum":   {"EXPLOSIVE": 15, "REAL": 10, "WEAK": 3, "FAKE": 0},
    "launch":     {"GOLDEN_WINDOW": 15, "SWEET_SPOT": 10, "TOO_EARLY": -10,
                   "LATE": -5, "OLD": -5},
    "change_1h":  [(100, 15), (50, 10), (20, 5)],       # (threshold, points)
    "change_5m":  [(10, 10), (0, 5), (-5, -10)],
    "age_sweet":  [((0.17, 0.5), 10), ((0.5, 1.0), 7)],
    "liquidity":  [(20_000, 10), (15_000, 5)],
    "social":     {3: 20, 2: 12, 1: 5},                  # unique channels
    "smart_money":{2: 20, 1: 12},                        # unique wallets
    # Was -25, which combined with muting punished the same fact twice and
    # pushed these below the tracking floor — discarding the outcome data on
    # the group that produces most of the rugs. Muting decides whether it
    # interrupts; the penalty only ranks it.
    "unverified": -10,
    "partial_safety": -8,
    # Every rug that reached King came from the unflagged group — nothing
    # detected, so nothing to warn about. Flagged tokens rugged zero times
    # and peaked at 115 on average. Silence is not safety, and until now it
    # cost nothing.
    "unproven_safety": -12,
    # A bleeding tape is not a small deduction. The same setup that is worth
    # taking with SOL up 8% is usually worth skipping with SOL down 12%.
    "macro":      {"BULLISH": 6, "NEUTRAL": 0, "CAUTION": -12, "PAUSE": -25},
    # Two different questions. Tracking is cheap and the data is how every
    # weight gets tuned, so track generously. Interrupting is expensive —
    # eleven signals a scan is several hundred a day and the channel gets
    # muted by evening.
    "min_to_track": 30,     # recorded, watched, feeds the outcome data
    "min_to_alert": 48,     # default bar for reaching Telegram

    # One floor across every tier silently muted the best-performing one.
    # Boosted produced 82 signals and sent zero: its gates are the loosest,
    # so its tokens score lower by construction — average 43, best 67 —
    # while winning 32.1% against first_moon's 17.9%.
    #
    # The score measures how much a token resembles a fresh launch, not how
    # likely it is to run. Boosted tokens score badly because they are older
    # and calmer, which is exactly what makes them win.
    "min_to_alert_by_tier": {
        "boosted":     38,
        "first_moon":  52,
        "second_moon": 48,
    },
    # Channel calls are not gated on this score at all. Conviction is
    # calibrated for fresh launches — it docks a 28h-old token for being old
    # and gives it no age bonus, which is right when the claim is "this is
    # early" and wrong when the claim is "four channels are on this". Setting
    # a separate number here was guesswork: the first genuine case landed at
    # 35 against a bar of 38, which says more about the bar than the token.
    #
    # What gates a channel call instead: real consensus, a matched tier, and
    # the same safety and scam checks as everything else. The score is still
    # computed and shown — it just does not decide.
    "bands": {"HIGH": 80, "GOOD": 60, "WATCH": 30},
}

# ── NARRATIVE WEIGHTS ─────────────────────────────────────────────
# Retuned automatically by learn.py from realised win rates.
NARRATIVES = {
    "AI":        {"points":  8, "patterns": ["ai", "gpt", "agent", "robot", "neural",
                                             "compute", "agi", "llm", "model"]},
    "ANIMAL":    {"points":  5, "patterns": [
        # Deliberately long. A dog meta runs as corgi, puppy and terrier, not
        # as the word "dog" — a short list makes category metas invisible.
        "dog", "doggo", "puppy", "pup", "shiba", "inu", "corgi", "husky",
        "terrier", "retriever", "poodle", "pug", "beagle", "dachshund",
        "labrador", "chihuahua", "mutt", "hound", "collie", "spaniel",
        "cat", "kitty", "kitten", "meow", "feline", "tabby", "persian",
        "lion", "tiger", "leopard", "cheetah", "panther", "lynx",
        "pepe", "frog", "toad", "bear", "bull", "whale", "shark", "dolphin",
        "bird", "duck", "goose", "owl", "eagle", "hawk", "penguin", "parrot",
        "wolf", "fox", "ape", "monkey", "gorilla", "chimp", "orangutan",
        "bunny", "rabbit", "hamster", "mouse", "rat", "squirrel", "otter",
        "goat", "sheep", "cow", "pig", "hippo", "rhino", "panda", "sloth",
        "koala", "camel", "llama", "alpaca", "crab", "snail", "turtle",
        "snake", "lizard", "gecko", "axolotl", "capybara", "raccoon",
    ]},
    "POLITICAL": {"points": -15, "patterns": ["trump", "maga", "biden", "political",
                                              "president", "congress", "democrat",
                                              "republican", "election"]},
    "ELON":      {"points": -8, "patterns": ["elon", "musk", "grok", "doge"]},
    "RWA":       {"points":  3, "patterns": ["stock", "gold", "oil", "bond", "equity"]},
}

# Checked in this order — a token matching both ELON and ANIMAL ("Doge") is
# an ELON play, and ELON's 25% historical win rate must win the tie.
NARRATIVE_PRIORITY = ["POLITICAL", "ELON", "AI", "RWA", "ANIMAL"]

# ── META DETECTION ────────────────────────────────────────────────
# The narrative list above is fixed and cannot contain a meta that did not
# exist yesterday. This learns one from whatever is actually performing.
META = {
    "min_change_24h":   80.0,    # a token must be running to vote
    "min_liquidity":  8_000,     # a 900% move on $300 is not a meta
    "window_hours":     24.0,
    "min_tokens":         3,     # distinct tokens carrying a word
    "min_tokens_category": 6,    # categories aggregate, so need more
    "saturate_at":       8,      # strength 1.0 at this many
    "max_points":        12,     # tops up a signal, never carries it
}

# ── SMART MONEY WALLETS ───────────────────────────────────────────
# chain -> [{address, label}]
SMART_MONEY = {
    "solana": [
        {"address": "MfDuWeqSHEqTFVYZ7LoexgAK9dxk7cy4DFJWjWMGVWa",  "label": "SM1"},
        {"address": "BQm74qyqiUMRBkyxgLV5TRSaerTJqPxKB3Spa4tscPTN", "label": "SM2"},
        {"address": "8Hm2QtQnWLtZy4qMQWN9FM965Pan96kHVQeNbAmZxXpt", "label": "SM3"},
        {"address": "BtDaZUqHr2mKH5EYQCztuerHBuBEfQNYdquTDtEZp2Ym", "label": "SM4"},
        {"address": "5emPNcmwvh5CH3Vg5dqEuLrvo5jfQSEtKnDDLm3oSeK3", "label": "SM5"},
        {"address": "EeXvxkcGqMDZeTaVeawzxm9mbzZwqDUMmfG3bF7uzumH", "label": "SM6"},
    ],
    "robinhood": [],
    "base":      [],
    "bsc":       [],
    "monad":     [],
}

# ── SOCIAL CHANNELS ───────────────────────────────────────────────
# (handle, label, weight). Weight is how much a mention counts toward
# consensus.
#
# Every channel counts equally for now. An earlier version discounted nine of
# them to 0.35 on the belief they were paid-promotion outlets — they are not,
# they are ordinary alpha channels whose owners are sometimes paid to post,
# which is true of most of this list. That weight was invented, not measured,
# and an invented penalty is worse than none.
#
# The mechanism stays because roadmap item 4 fills it with each channel's
# measured hit rate against outcomes. Until then, one channel, one vote.
ORGANIC = PROMO = 1.0

TELEGRAM_CHANNELS = [
    ("Blessedmemecalls",       "Blessed",             ORGANIC),
    ("CatfishcallsbyPoe",      "Catfish by Poe",      ORGANIC),
    ("CryptoLord100xCalls",    "CryptoLord",          ORGANIC),
    ("BanksDegenPlays",        "Banks",               ORGANIC),
    ("ghostfacecallerchannel", "Poizer",              ORGANIC),
    ("spidersjournal",         "SpiderCrypto",        ORGANIC),
    ("hellokook",              "Kook",                ORGANIC),
    ("SHITTYCALLZBYPOE",       "Shitty Calls by Poe", ORGANIC),
    ("Gems1000XXCalls",        "Royal Gems",          ORGANIC),
    ("moderncryptoanalyst",    "Modern",              ORGANIC),
    ("nft_brewery",            "Brewery",             ORGANIC),
    ("jsdao",                  "JSDAO",               ORGANIC),
    ("HubzCabal",              "HubzCabal",           ORGANIC),
    ("realsolanahome",         "Solana Home",         ORGANIC),
    ("SaintDovydegen",         "Saint Dovy",          ORGANIC),
    ("Alphadropcall",          "Alpha Drop",          ORGANIC),
    ("crypticsden22",          "Cryptics Den",        ORGANIC),
    ("shahlito",               "Shahlito",            ORGANIC),
    ("ferbsfriendz",           "Ferbs Friendz",       ORGANIC),
    ("solidtradesz",           "Solid Trades",        ORGANIC),
    ("solpumpforce67",         "Sol Pump Force",      ORGANIC),
    ("calledbymaxi",           "Called By Maxi",      ORGANIC),
    ("SonicsAlphacalls",       "Sonics Alpha",        ORGANIC),
    ("newsgraph",              "Newsgraph",           ORGANIC),

    # Added later; same standing as every channel above.
    ("EthansCrypto",           "Ethans Crypto",       PROMO),
    ("DegenPlayhouse",         "Degen Playhouse",     PROMO),
    ("SlavicCalls",            "Slavic Calls",        PROMO),
    ("houseofdegeneracy",      "House of Degeneracy", PROMO),
    ("bullybattalion",         "Bully Battalion",     PROMO),
    ("Diorscabal",             "Diors Cabal",         PROMO),
    ("eezzyjournal",           "Eezzy Journal",       PROMO),
    ("dogendojo",              "Dogen Dojo",          PROMO),
    ("unipcsjournal",          "Unipcs Journal",      PROMO),
]

CHANNEL_WEIGHTS = {label: weight for _, label, weight in TELEGRAM_CHANNELS}
PROMO_CHANNELS = {label for _, label, w in TELEGRAM_CHANNELS if w < ORGANIC}

SOCIAL_WINDOW_SECONDS   = 7200   # 2h velocity window
VELOCITY_MIN_CHANNELS   = 2      # weighted channels for consensus
# Each evaluated call costs a safety lookup, so this is a time budget rather
# than a philosophical limit. Consensus tokens are sorted first, so the cap
# trims the least-supported calls.
SOCIAL_CALL_LIMIT       = 20

# ── POSITION WATCH (signal-only, no execution) ────────────────────
WATCH = {
    "tp1_pct":             50,
    "tp2_pct":            100,
    "tp3_pct":            200,
    # Warning and grading are separate jobs. On the VPS they had to be the
    # same moment because the bot was exiting; signal-only means we can warn
    # early while the trade is still actionable, then grade once the outcome
    # is actually settled — and learn whether early dips recover.
    "stop_warn_pct":      -15,   # notify, keep watching
    "stop_loss_pct":      -35,   # grade it, stop watching
    "stop_grace_minutes":  20,   # no grading inside this window, warning only

    # Trailing arms on any meaningful gain, not just after TP2. wDELLx ran
    # +45%, never reached TP1 at +50%, and gave back everything with nothing
    # firing on the way down.
    # Measured as the fraction of the gain surrendered, not drawdown from
    # peak price. 40% off a +45% peak is break-even; 40% off a +500% peak is
    # still a large win. The same number cannot mean both.
    "trail_arm_pct":         25,   # peak gain needed to arm
    "give_back_ratio":      0.65,  # surrender this much of the gain -> exit
    "give_back_after_tp2":  0.35,  # tighter once TP2 is banked
    "time_stop_hours":      2,   # exit alert if still negative
    "time_exit_hours":      4,   # exit alert if still flat
    "max_hold_hours":       8,
    # Volume fade closed at +78% against a +101% peak; trailing closed at
    # -21% against a +95% peak, on the same average high. Momentum dies
    # before price does, so lean on the leading indicator.
    "volume_fade_ratio":  0.45,
    "volume_fade_min_pnl":  10,
    "dev_sold_fraction":   0.5,   # deployer shedding this much of its bag
    "whale_recheck_hours":   2,
    "whale_recheck_min_pnl": 30,
    "whale_top_holder_pct":  30,
    "graduation_bc_pct":     60,
    "max_open_positions":    25,  # tracking cap
    # Inherited from the autonomous version, where pausing after losses
    # protected capital. Signal-only, it just goes quiet while King is the
    # one deciding what to trade — and two losers at a ~20% win rate is an
    # ordinary afternoon, not a reason to miss the next runner.
    "cooloff_losses":         5,
    "cooloff_minutes":       20,
    # A parked token that has failed the gates this many times is not going
    # to turn. Holding it costs a re-check slot a fresher token could use.
    "max_watchlist_checks":   12,
    # A position cannot lose more than everything, and a reading above this
    # is a broken entry price rather than a moonshot. Seven such rows put
    # the average final PnL at 124 million percent.
    "pnl_floor_pct":       -100.0,
    "pnl_ceiling_pct":   10_000.0,
}

# ── DEDUPE ────────────────────────────────────────────────────────
# Re-alert the same CA only after this long. Alerts are NOT suppressed
# just because the token is already being tracked — that bug cost us
# every second-moon signal in v1.
REALERT_COOLDOWN_MINUTES = 180
