"""
Surgeon-Pro — central configuration.

Built on the proven Surgeon architecture with improved exit logic
and refined scoring based on 1,400+ closed trades.
"""

import os

# ── SECRETS (set as GitHub Actions secrets / env vars) ────────────
HELIUS_API_KEY      = os.getenv("HELIUS_API_KEY", "")
GOPLUS_APP_KEY      = os.getenv("GOPLUS_APP_KEY", "")
GOPLUS_APP_SECRET   = os.getenv("GOPLUS_APP_SECRET", "")
LIVE_ALERTS         = os.getenv("SURGEON_LIVE", "").lower() == "true"
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
SUPABASE_URL        = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY        = os.getenv("SUPABASE_KEY", "")

# ── HTTP ──────────────────────────────────────────────────────────
HTTP_TIMEOUT   = 12
HTTP_RETRIES   = 2
HTTP_BACKOFF   = 1.5
USER_AGENT     = "surgeon-pro/1.0"

# ── CHAIN REGISTRY ────────────────────────────────────────────────
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
        "dexscreener_id":  "robinhood",
        "geckoterminal_id": "robinhood",
        "discovery_pages":  3,
        "goplus_chain_id": "4663",
        "blockscout":      "https://robinhoodchain.blockscout.com",
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
        "dexscreener_id":  "monad",
        "geckoterminal_id": "monad",
        "discovery_pages":  2,
        "goplus_chain_id": "143",
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
THRESHOLDS = {
    "first_moon": {
        "min_liquidity":   6_000,
        "min_fdv":         5_000,
        "max_fdv":       150_000,
        "min_age_hours":     0.17,
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
    "social_call": {
        "min_liquidity":  15_000,
        "min_fdv":        20_000,
        "max_fdv":    50_000_000,
        "min_age_hours":     0.17,
        "max_age_hours":   168.0,
        "min_change_1h":   -20.0,
        "min_volume_1h":  10_000,
        "min_turnover_1h":   0.05,
        "min_change_5m":   -30.0,
    },
}

CHAIN_THRESHOLD_OVERRIDES = {
    "robinhood": {
        "first_moon": {"min_liquidity": 3_000, "min_volume_1h": 1_500},
        "boosted":    {"min_liquidity": 5_000, "min_volume_1h": 2_000},
    },
    "monad": {
        "first_moon": {"min_liquidity": 3_000, "min_volume_1h": 1_500},
        "boosted":    {"min_liquidity": 5_000, "min_volume_1h": 2_000},
    },
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
    "max_top_holder_pct":   20.0,
    "max_top10_pct":        60.0,
    "min_lp_locked_pct":    80.0,
    "lp_zero_creator_max":   0.5,
    "lp_zero_insider_max":   2.0,
    "lp_zero_holder_min":  500,
    "max_buy_tax_pct":      10.0,
    "max_sell_tax_pct":     10.0,
    "rugcheck_raw_block":   500,
    "rug_score_min_holders": 300,
    "lp_min_lock_hours":    24.0,
    "reject_on_honeypot":   True,
    "reject_on_mint_auth":  True,
    "reject_on_freeze":     True,
    "reject_creator_rug_history": True,
    "max_creator_holds_pct": 20.0,
    "min_holder_count":      10,
    "reject_unverified_contract_if_thin": True,
    "alert_on_partial":     True,
    "unverified_policy":    "flag",
}

# ── SCAM HEURISTICS ───────────────────────────────────────────────
SCAM = {
    "enabled":            True,
    "top_holder_pct":        3.5,
    "top_holder_grace_hours": 1.0,
    "min_volume_to_mcap":    0.80,
    "bundled_pct":          15.0,
    "min_holders":          50,
    "creator_holds_pct":     2.0,
    "max_danger_flags":      3,
}

# ── MARKET DATA SANITY ────────────────────────────────────────────
SANITY = {
    "max_fdv_liq_ratio":  500,
    "max_abs_change_pct": 50_000,
    "min_liquidity_usd":  1_000,
    "unknown_age_hours":  999.0,
}

# ── MARKET HOURS (UTC) ────────────────────────────────────────────
MARKET_HOURS = {
    "peak": (13, 21),
    "dead": (2, 8),
}
MARKET_HOURS_ADJUST = {
    "PEAK":   {"min_change_1h_mult": 0.75, "min_volume_mult": 0.6, "conviction": +5},
    "NORMAL": {"min_change_1h_mult": 1.00, "min_volume_mult": 1.0, "conviction":  0},
    "DEAD":   {"min_change_1h_mult": 2.00, "min_volume_mult": 2.0, "conviction": 0},
}

# ── CONVICTION SCORING ────────────────────────────────────────────
CONVICTION = {
    # Pro: EXPLOSIVE is the strongest quality signal in the data
    "momentum":   {"EXPLOSIVE": 23, "REAL": 11, "WEAK": -12, "FAKE": -15},
    "launch":     {"GOLDEN_WINDOW": 15, "SWEET_SPOT": 10, "TOO_EARLY": -10,
                   "LATE": -5, "OLD": -5},
    "change_1h":  [(100, 15), (50, 10), (20, 5)],
    "change_5m":  [(10, 10), (0, 5), (-5, -10)],
    "age_sweet":  [((0.17, 0.5), 10), ((0.5, 1.0), 7)],
    "liquidity":  [(20_000, 10), (15_000, 5)],
    "social":     {3: 20, 2: 12, 1: 5},
    "smart_money":{2: 24, 1: 14},          # Pro: higher weight
    "unverified": -18,
    "partial_safety": -8,
    "unproven_safety": 0,
    "macro":      {"BULLISH": 6, "NEUTRAL": 0, "CAUTION": -12, "PAUSE": -25},
    "min_to_track": 30,
    "min_to_alert": 48,
    "min_to_alert_by_tier": {
        "boosted":     38,
        "first_moon":  52,
        "second_moon": 48,
    },
    "bands": {"HIGH": 80, "GOOD": 60, "WATCH": 30},
}

# ── NARRATIVE WEIGHTS ─────────────────────────────────────────────
NARRATIVES = {
    "AI":        {"points":  8, "patterns": ["ai", "gpt", "agent", "robot", "neural",
                                             "compute", "agi", "llm", "model"]},
    "ANIMAL":    {"points":  5, "patterns": [
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

NARRATIVE_PRIORITY = ["POLITICAL", "ELON", "AI", "RWA", "ANIMAL"]

# ── META DETECTION ────────────────────────────────────────────────
META = {
    "min_change_24h":   80.0,
    "min_liquidity":  8_000,
    "window_hours":     24.0,
    "min_tokens":         3,
    "min_tokens_category": 6,
    "saturate_at":       8,
    "max_points":        12,
}

# ── SMART MONEY WALLETS ───────────────────────────────────────────
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

SOCIAL_WINDOW_SECONDS   = 7200
VELOCITY_MIN_CHANNELS   = 2
SOCIAL_CALL_LIMIT       = 20

# ── POSITION WATCH (Surgeon-Pro Exit Overhaul) ────────────────────
WATCH = {
    # Stronger take-profit levels
    "tp1_pct":             70,
    "tp2_pct":            140,
    "tp3_pct":            250,

    "stop_warn_pct":      -15,
    "stop_loss_pct":      -35,
    "stop_grace_minutes":  20,

    # Much wider trailing + hard floor
    "trail_arm_pct":         60,     # was 25
    "give_back_ratio":      0.48,    # was 0.65
    "give_back_after_big":  0.32,    # tighter only after ≥200% peak
    "give_back_after_tp2":  0.38,

    "time_stop_hours":      2.5,
    "time_exit_hours":      5,
    "max_hold_hours":      10,

    # Stronger Volume Fade (primary profitable exit)
    "volume_fade_ratio":   0.38,
    "volume_fade_min_pnl":  45,

    "dev_sold_fraction":   0.5,
    "whale_recheck_hours":   2,
    "whale_recheck_min_pnl": 30,
    "whale_top_holder_pct":  30,
    "graduation_bc_pct":     60,
    "max_open_positions":    25,
    "cooloff_losses":         5,
    "cooloff_minutes":       20,
    "max_watchlist_checks":   12,
    "pnl_floor_pct":       -100.0,
    "pnl_ceiling_pct":   10_000.0,

    # New protective floor
    "hard_floor_after_peak": 25,
}

# ── DEDUPE ────────────────────────────────────────────────────────
REALERT_COOLDOWN_MINUTES = 180
