"""
Scam heuristics.

These come from King's own trading experience rather than from anything the
APIs advertise, and the thresholds are far tighter than Surgeon's entry
gates — top holder at 3.5% against a 20% reject, for instance. Enforced as
rejects they would silence the scanner almost entirely.

So they are warnings that cost conviction. The signal still fires; it arrives
carrying its rap sheet, and a token collecting several of these ends up below
the alert floor on arithmetic rather than by decree.
"""

from __future__ import annotations

from dataclasses import dataclass

import config


@dataclass
class RiskFlag:
    code: str
    detail: str
    penalty: int
    severity: str = "warn"      # warn | danger

    def __str__(self) -> str:
        return f"{self.code} ({self.detail})"


# ── individual checks ─────────────────────────────────────────────

def _top_holder(safety, market=None) -> RiskFlag | None:
    """
    A single wallet holding real size can exit into your bid.

    Scaled by age as well as size. On a token twenty minutes old,
    concentration is what an early runner looks like — Buying Power took -14
    here and ran +3,128%, Caesar took -14 and ran +794%. A holder base takes
    hours to spread, so charging full price for that in the first hour
    penalises the defining feature of the winners.
    """
    pct = safety.top_holder_pct
    if pct is None or pct <= config.SCAM["top_holder_pct"]:
        return None

    if pct >= 20:
        points, severity = -22, "danger"
    elif pct >= 10:
        points, severity = -14, "warn"
    else:
        points, severity = -6, "warn"

    age = getattr(market, "age_hours", None) if market else None
    known = getattr(market, "age_known", False) if market else False
    if known and age is not None and age < config.SCAM["top_holder_grace_hours"]:
        # Halved, not waived: 40% in one wallet is a countdown at any age.
        points = int(round(points / 2))
        if severity == "warn":
            return RiskFlag("TOP_HOLDER",
                            f"{pct:.1f}% in one wallet, {age * 60:.0f}m old",
                            points, severity)
    return RiskFlag("TOP_HOLDER", f"{pct:.1f}% in one wallet", points, severity)


def _thin_volume(market) -> RiskFlag | None:
    """
    Volume well below market cap means the valuation is not being tested.

    A real market turns over; a painted one shows a large cap on trades that
    never happened. Uses market cap where reported, FDV otherwise.
    """
    cap = market.market_cap or market.fdv
    if cap <= 0 or market.volume_24h <= 0:
        return None
    ratio = market.volume_24h / cap
    if ratio >= config.SCAM["min_volume_to_mcap"]:
        return None
    if ratio < 0.15:
        return RiskFlag("THIN_VOLUME",
                        f"24h volume {ratio:.0%} of cap", -18, "danger")
    return RiskFlag("THIN_VOLUME", f"24h volume {ratio:.0%} of cap", -10)


def _bundled(safety) -> RiskFlag | None:
    """
    Supply held by wallets funded together and bought at launch.

    RugCheck tags these as insiders; Surgeon previously filtered them out of
    the concentration figure and then discarded the fact, which quietly
    removed the strongest scam tell in the response.
    """
    pct = safety.insider_pct
    if pct is None or pct <= config.SCAM["bundled_pct"]:
        return None
    if pct >= 30:
        return RiskFlag("BUNDLED", f"{pct:.0f}% bundled at launch", -30, "danger")
    if pct >= 20:
        return RiskFlag("BUNDLED", f"{pct:.0f}% bundled at launch", -22, "danger")
    return RiskFlag("BUNDLED", f"{pct:.0f}% bundled at launch", -14)


def _lock_expiring(safety) -> RiskFlag | None:
    """
    Liquidity locked until this afternoon is not locked in any useful sense.

    Scaled by how soon: a lock with an hour left is a countdown, one with a
    day left is a schedule. Burned LP and locks with no expiry return nothing.
    """
    h = safety.lp_unlock_hours
    if h is None:
        return None
    if h <= 0:
        return RiskFlag("LP_EXPIRED", "lock already expired", -25, "danger")
    if h <= 2:
        return RiskFlag("LP_UNLOCKING", f"unlocks in {h * 60:.0f}m", -20, "danger")
    if h <= 12:
        return RiskFlag("LP_UNLOCKING", f"unlocks in {h:.0f}h", -12)
    if h <= config.SAFETY["lp_min_lock_hours"]:
        return RiskFlag("LP_UNLOCKING", f"unlocks in {h:.0f}h", -6)
    return None


def _thin_holders(safety) -> RiskFlag | None:
    n = safety.holder_count
    if n is None or n >= config.SCAM["min_holders"]:
        return None
    return RiskFlag("FEW_HOLDERS", f"{n} holders", -12)


def _creator_heavy(safety) -> RiskFlag | None:
    pct = safety.creator_holds_pct
    if pct is None or pct <= config.SCAM["creator_holds_pct"]:
        return None
    return RiskFlag("CREATOR_HOLDS", f"deployer holds {pct:.1f}%", -16, "danger")


def _unverified_safety(safety) -> RiskFlag | None:
    """Being unable to check is itself a risk, and should read as one."""
    if safety.verified:
        return None
    return RiskFlag("UNCHECKED", "no safety source answered", -10, "danger")


CHECKS = (
    ("safety_market", _top_holder),
    ("market", _thin_volume),
    ("safety", _bundled),
    ("safety", _lock_expiring),
    ("safety", _thin_holders),
    ("safety", _creator_heavy),
    ("safety", _unverified_safety),
)


def assess(market, safety) -> list[RiskFlag]:
    """Every warning this token earns, worst first."""
    if not config.SCAM.get("enabled", True):
        return []
    flags: list[RiskFlag] = []
    for kind, check in CHECKS:
        if kind == "market":
            flag = check(market)
        elif kind == "safety_market":
            flag = check(safety, market)
        else:
            flag = check(safety)
        if flag:
            flags.append(flag)
    flags.sort(key=lambda f: f.penalty)
    return flags


def total_penalty(flags: list[RiskFlag]) -> int:
    return sum(f.penalty for f in flags)


def danger_count(flags: list[RiskFlag]) -> int:
    return sum(1 for f in flags if f.severity == "danger")


def summarise(flags: list[RiskFlag]) -> str:
    if not flags:
        return "no scam flags"
    return " · ".join(str(f) for f in flags)
