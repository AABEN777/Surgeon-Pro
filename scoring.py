"""
Scoring core — chain-blind.

Nothing here knows what a chain is. It takes a TokenMarket and a SafetyReport
and returns a tier, a conviction score and, crucially, the reasoning behind
both. v1 emitted a bare number; when a score looked wrong there was no way to
tell which input caused it.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import config
import meta as meta_mod
import risk
from chain_base import TokenMarket, SafetyReport


# ── MARKET HOURS ──────────────────────────────────────────────────

def market_session(now: Optional[datetime] = None) -> str:
    """PEAK | NORMAL | DEAD, in UTC."""
    h = (now or datetime.now(timezone.utc)).hour
    lo, hi = config.MARKET_HOURS["peak"]
    if lo <= h <= hi:
        return "PEAK"
    lo, hi = config.MARKET_HOURS["dead"]
    if lo <= h <= hi:
        return "DEAD"
    return "NORMAL"


# ── MOMENTUM & LAUNCH PHASE ───────────────────────────────────────

def momentum_quality(m: TokenMarket) -> str:
    """
    EXPLOSIVE | REAL | WEAK | FAKE

    Price alone lies — a token can be up 300% on four trades. Buy pressure
    and volume-to-liquidity are what separate a move from a print.
    """
    score = 0

    if m.change_1h >= 100:
        score += 2
    elif m.change_1h >= 40:
        score += 1

    if m.change_5m >= 10:
        score += 1
    elif m.change_5m <= -10:
        score -= 1

    ratio = m.buy_ratio_5m
    if ratio is not None and ratio != float("inf"):
        if ratio >= 2.0:
            score += 2
        elif ratio >= 1.3:
            score += 1
        elif ratio < 0.7:
            score -= 1
    elif m.buys_5m >= 5 and m.sells_5m == 0:
        score += 1

    total_tx = m.buys_5m + m.sells_5m
    if total_tx >= 40:
        score += 1
    elif total_tx <= 3:
        score -= 1

    if m.liquidity_usd > 0:
        vol_liq = m.volume_1h / m.liquidity_usd
        if vol_liq >= 1.0:
            score += 1

    if score >= 5:
        return "EXPLOSIVE"
    if score >= 3:
        return "REAL"
    if score >= 1:
        return "WEAK"
    return "FAKE"


def launch_phase(m: TokenMarket) -> str:
    """GOLDEN_WINDOW | SWEET_SPOT | TOO_EARLY | LATE | OLD | UNKNOWN"""
    if not m.age_known:
        return "UNKNOWN"
    a = m.age_hours
    if a < config.THRESHOLDS["first_moon"]["min_age_hours"]:
        return "TOO_EARLY"
    if a <= 2:
        return "GOLDEN_WINDOW"
    if a <= 6:
        return "SWEET_SPOT"
    if a <= 24:
        return "LATE"
    return "OLD"


# ── NARRATIVE ─────────────────────────────────────────────────────

# Boundaries on BOTH ends. A leading-only boundary made "dog" match "Doge",
# so every Elon token scored an animal bonus instead of its penalty.
_NARRATIVE_RE = {
    key: re.compile(r"\b(" + "|".join(re.escape(p) for p in cfg["patterns"]) + r")\b",
                    re.IGNORECASE)
    for key, cfg in config.NARRATIVES.items()
}

_NARRATIVE_ORDER = [k for k in config.NARRATIVE_PRIORITY if k in _NARRATIVE_RE]
_NARRATIVE_ORDER += [k for k in _NARRATIVE_RE if k not in _NARRATIVE_ORDER]


def classify_narrative(name: str, symbol: str = "") -> tuple[str, int]:
    """
    (narrative, points). Word-boundary matched — substring matching turned
    every token containing 'ai' into an AI play, which is how 'Certain' and
    'Captain' scored a momentum bonus in v1.
    """
    text = f"{name} {symbol}".strip()
    for key in _NARRATIVE_ORDER:
        if _NARRATIVE_RE[key].search(text):
            return key, config.NARRATIVES[key]["points"]
    return "NONE", 0


# ── TIER CLASSIFICATION ───────────────────────────────────────────

@dataclass
class TierResult:
    tier: Optional[str] = None
    failures: dict[str, list[str]] = field(default_factory=dict)

    @property
    def matched(self) -> bool:
        return self.tier is not None


def classify_tier(m: TokenMarket, chain: str,
                  session: Optional[str] = None,
                  tiers: Optional[tuple] = None) -> TierResult:
    """
    Which tier, if any, this token qualifies for. Returns the reasons each
    tier was missed so a near-miss is visible rather than silent.
    """
    session = session or market_session()
    adj = config.MARKET_HOURS_ADJUST[session]
    res = TierResult()

    for tier in (tiers or ("first_moon", "second_moon", "boosted")):
        t = config.thresholds_for(chain, tier)
        min_chg = t["min_change_1h"] * adj["min_change_1h_mult"]
        min_vol = t["min_volume_1h"] * adj["min_volume_mult"]
        fails = []

        # Under an hour old there is no separate hourly figure — the 24h
        # number is the token's whole life, so it is the honest fallback.
        vol_1h = m.volume_1h if m.volume_1h > 0 else m.volume_24h
        turnover = (vol_1h / m.liquidity_usd) if m.liquidity_usd > 0 else 0.0

        if m.liquidity_usd < t["min_liquidity"]:
            fails.append(f"liq ${m.liquidity_usd:,.0f} < ${t['min_liquidity']:,}")
        if not (t["min_fdv"] <= m.fdv <= t["max_fdv"]):
            fails.append(f"fdv ${m.fdv:,.0f} outside "
                         f"${t['min_fdv']:,}-${t['max_fdv']:,}")
        if m.age_known:
            if m.age_hours < t["min_age_hours"]:
                fails.append(f"age {m.age_hours:.2f}h < {t['min_age_hours']}h")
            elif m.age_hours > t["max_age_hours"]:
                fails.append(f"age {m.age_hours:.2f}h > {t['max_age_hours']}h")
        if m.change_1h < min_chg:
            fails.append(f"1h {m.change_1h:.1f}% < {min_chg:.1f}%")
        if vol_1h < min_vol:
            fails.append(f"vol1h ${vol_1h:,.0f} < ${min_vol:,.0f}")
        if turnover < t["min_turnover_1h"]:
            fails.append(f"turnover {turnover:.2f}x < {t['min_turnover_1h']}x")
        if m.change_5m < t["min_change_5m"]:
            fails.append(f"5m {m.change_5m:.1f}% < {t['min_change_5m']}% (dumping)")

        if not fails:
            res.tier = tier
            return res
        res.failures[tier] = fails

    return res


# ── CONVICTION ────────────────────────────────────────────────────

@dataclass
class Conviction:
    score: int = 0
    band: str = "SKIP"
    components: list[tuple[str, int]] = field(default_factory=list)
    momentum: str = "FAKE"
    launch: str = "UNKNOWN"
    narrative: str = "NONE"
    meta_term: str = ""
    session: str = "NORMAL"
    social_channels: float = 0.0
    smart_wallets: int = 0
    risk_flags: list = field(default_factory=list)

    def add(self, label: str, points: int):
        if points:
            self.components.append((label, points))
            self.score += points

    def explain(self) -> str:
        """Human-readable breakdown, biggest contributors first."""
        parts = sorted(self.components, key=lambda x: -abs(x[1]))
        return " ".join(f"{l}{p:+d}" for l, p in parts)

    @property
    def trackable(self) -> bool:
        """Worth recording and watching, even if it never reaches Telegram."""
        return self.score >= config.CONVICTION["min_to_track"]

    @property
    def alertable(self) -> bool:
        """Worth interrupting for."""
        return self.score >= config.CONVICTION["min_to_alert"]


def _tiered(value: float, table: list) -> int:
    """First matching (threshold, points) pair, descending."""
    for threshold, pts in table:
        if value >= threshold:
            return pts
    return 0


def conviction_score(m: TokenMarket,
                     safety: SafetyReport,
                     social_channels: float = 0.0,
                     smart_wallets: int = 0,
                     macro: str = "NEUTRAL",
                     session: Optional[str] = None,
                     hot_meta: Optional[dict] = None) -> Conviction:
    """
    0-100 with the arithmetic exposed.

    Safety quality is part of the score, not a separate gate. A token whose
    holder distribution nobody could verify is genuinely less attractive than
    one that has been checked, and the number should say so.
    """
    C = config.CONVICTION
    c = Conviction()
    c.session = session or market_session()
    c.momentum = momentum_quality(m)
    c.launch = launch_phase(m)
    c.social_channels = social_channels
    c.smart_wallets = smart_wallets

    c.add(f"momentum:{c.momentum}", C["momentum"].get(c.momentum, 0))
    c.add(f"launch:{c.launch}", C["launch"].get(c.launch, 0))
    c.add("change1h", _tiered(m.change_1h, C["change_1h"]))

    for threshold, pts in C["change_5m"]:
        if m.change_5m >= threshold:
            c.add("change5m", pts)
            break
    else:
        c.add("change5m", C["change_5m"][-1][1])

    if m.age_known:
        for (lo, hi), pts in C["age_sweet"]:
            if lo <= m.age_hours <= hi:
                c.add("age_sweet_spot", pts)
                break

    c.add("liquidity", _tiered(m.liquidity_usd, C["liquidity"]))

    for n, pts in sorted(C["social"].items(), reverse=True):
        if social_channels >= n:
            c.add(f"social:{social_channels:g}ch", pts)
            break

    for n, pts in sorted(C["smart_money"].items(), reverse=True):
        if smart_wallets >= n:
            c.add(f"smart_money:{smart_wallets}", pts)
            break

    narrative, npts = classify_narrative(m.name, m.symbol)
    c.narrative = narrative
    c.add(f"narrative:{narrative}", npts)

    # Whatever is running today, learned rather than listed.
    if hot_meta:
        mpts, term = meta_mod.score(m.name, m.symbol, hot_meta)
        if mpts:
            c.meta_term = term
            c.add(f"meta:{term}", mpts)

    c.add(f"session:{c.session}", config.MARKET_HOURS_ADJUST[c.session]["conviction"])
    c.add(f"macro:{macro}", C["macro"].get(macro, 0))

    # safety quality
    if not safety.verified:
        c.add("UNVERIFIED", C["unverified"])
    else:
        if safety.partial:
            c.add("safety_partial", C["partial_safety"])
        # A source answered but had nothing to examine — no holder base, no
        # history. That is not the same as being checked and passing.
        if (safety.risk_raw is not None and safety.risk_raw <= 50
                and not safety.rug_score_meaningful):
            c.add("unproven", C["unproven_safety"])

    # untrustworthy market data should never look like momentum
    issues = m.sanity_issues
    if issues:
        c.add(f"suspect_data:{len(issues)}", -20)

    # Scam heuristics. Deliberately scored rather than enforced: the
    # thresholds are tighter than the entry gates, and a token collecting
    # several of these drops below the alert floor on its own arithmetic.
    c.risk_flags = risk.assess(m, safety)
    for flag in c.risk_flags:
        c.add(f"risk:{flag.code}", flag.penalty)

    c.score = max(0, min(100, c.score))
    b = C["bands"]
    if c.score >= b["HIGH"]:
        c.band = "HIGH"
    elif c.score >= b["GOOD"]:
        c.band = "GOOD"
    elif c.score >= b["WATCH"]:
        c.band = "WATCH"
    else:
        c.band = "SKIP"
    return c


# ── FULL EVALUATION ───────────────────────────────────────────────

@dataclass
class Evaluation:
    ca: str
    chain: str
    market: TokenMarket
    safety: SafetyReport
    tier: TierResult
    conviction: Conviction
    rejected_by: Optional[str] = None
    reject_detail: str = ""
    from_watchlist: bool = False
    called_by: list = field(default_factory=list)
    mute_reason: Optional[str] = None

    @property
    def should_track(self) -> bool:
        """Passed every gate — record it and watch how it turns out."""
        return self.rejected_by is None

    @property
    def should_alert(self) -> bool:
        """Passed every gate and cleared the bar for interrupting."""
        if self.rejected_by is not None or self.mute_reason:
            return False
        # Each tier is judged against its own distribution. A single floor
        # muted boosted entirely while passing weaker first_moon signals.
        if self.tier.tier == "social_call":
            # Consensus is the signal, not the score. Safety, scam checks and
            # the tier gate have already run — one channel posting into the
            # void is all this needs to exclude.
            return (self.conviction.social_channels
                    >= config.VELOCITY_MIN_CHANNELS)
        floor = config.CONVICTION["min_to_alert_by_tier"].get(
            self.tier.tier, config.CONVICTION["min_to_alert"])
        return self.conviction.score >= floor

    def summary(self) -> str:
        if self.rejected_by:
            return f"REJECT[{self.rejected_by}] {self.reject_detail}"
        return (f"{self.tier.tier} · {self.conviction.band} "
                f"{self.conviction.score}/100 · {self.conviction.momentum}")


def evaluate(m: TokenMarket, safety: SafetyReport, chain: str,
             social_channels: float = 0.0, smart_wallets: int = 0,
             macro: str = "NEUTRAL",
             hot_meta: Optional[dict] = None,
             tiers: Optional[tuple] = None) -> Evaluation:
    """
    Single decision point: alert or not, and why.

    Order matters — cheap structural rejects first, scoring last, so the
    reason recorded is the first real problem rather than a downstream
    symptom of it.
    """
    session = market_session()
    tier = classify_tier(m, chain, session, tiers)
    conv = conviction_score(m, safety, social_channels, smart_wallets,
                            macro, session, hot_meta)
    ev = Evaluation(ca=m.ca, chain=chain, market=m, safety=safety,
                    tier=tier, conviction=conv)

    if not m.ok:
        ev.rejected_by, ev.reject_detail = "market_data", m.error or "unavailable"
        return ev

    if safety.hard_rejects:
        ev.rejected_by = "safety"
        ev.reject_detail = ", ".join(safety.hard_rejects)
        return ev

    if not safety.verified:
        policy = config.SAFETY["unverified_policy"]
        if policy == "block":
            ev.rejected_by, ev.reject_detail = "unverified", "no safety source"
            return ev
        if policy == "track_only":
            # Recorded and watched so the outcome data keeps building, but it
            # will not interrupt: rugs come from what cannot be checked.
            ev.mute_reason = "unverified"

    if not tier.matched:
        ev.rejected_by = "tier"
        first = tier.failures.get("first_moon", [])
        ev.reject_detail = "; ".join(first[:2]) if first else "no tier matched"
        return ev

    # Any single warning is survivable; several severe ones together is a
    # pattern, and no amount of momentum should outvote it.
    dangers = risk.danger_count(conv.risk_flags)
    if dangers >= config.SCAM["max_danger_flags"]:
        ev.rejected_by = "scam_pattern"
        ev.reject_detail = risk.summarise(
            [f for f in conv.risk_flags if f.severity == "danger"])
        return ev

    # The conviction floor filters noise out of discovery. A channel call has
    # already been filtered by people watching full-time, so it is judged on
    # consensus and safety rather than on resembling a fresh launch.
    if tier.tier != "social_call" and not conv.trackable:
        ev.rejected_by = "conviction"
        ev.reject_detail = f"{conv.score}/100 < {config.CONVICTION['min_to_track']}"
        return ev

    return ev
