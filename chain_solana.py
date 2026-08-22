"""
Solana adapter — DexScreener (market) + RugCheck (safety) + Helius (creator).

Carries over every v1 rule: top-holder cap, LP lock on graduated pools only,
danger flags, raw-score block. Difference from v1: when RugCheck times out we
record the gap in `unavailable` instead of letting the field default to zero.
"""

from __future__ import annotations

import time
from typing import Optional

import config
from chain_base import (
    is_solana_infrastructure,
    ChainAdapter, SafetyReport, CreatorActivity,
    http_get, safe_float, safe_int,
)

RUGCHECK = "https://api.rugcheck.xyz/v1/tokens/{ca}/report"
HELIUS_TX = "https://api.helius.xyz/v0/addresses/{addr}/transactions"

# Bonding-curve pools are locked by construction — skip the LP check there.
BONDING_CURVE_MARKETS = {"pump_fun_amm", "pumpfun", "moonshot", "bonk_curve"}

CREATOR_RUG_PATTERNS = ("rugged", "creator history", "previous rug")


class SolanaAdapter(ChainAdapter):

    def __init__(self):
        super().__init__("solana")

    # ── SAFETY ────────────────────────────────────────────────────
    def safety(self, ca: str, pair_address: str | None = None) -> SafetyReport:
        rep = SafetyReport(ca=ca, chain=self.key)
        data = http_get(RUGCHECK.format(ca=ca), timeout=15)

        if not data or not isinstance(data, dict):
            rep.unavailable = [
                "top_holder_pct", "top10_pct", "lp_locked_pct",
                "mint_authority", "freeze_authority", "creator", "risk_raw",
            ]
            rep.flags.append("rugcheck_unreachable")
            return rep

        rep.sources.append("rugcheck")

        # -- hard kill switches ------------------------------------
        if data.get("rugged") is True:
            rep.hard_rejects.append("rugged")

        token = data.get("token") or {}
        mint_auth = token.get("mintAuthority")
        freeze_auth = token.get("freezeAuthority")
        rep.mint_authority = bool(mint_auth) and mint_auth != "null"
        rep.freeze_authority = bool(freeze_auth) and freeze_auth != "null"
        if rep.mint_authority and config.SAFETY["reject_on_mint_auth"]:
            rep.hard_rejects.append("mint_authority_active")
        if rep.freeze_authority and config.SAFETY["reject_on_freeze"]:
            rep.hard_rejects.append("freeze_authority_active")

        # -- raw risk score ---------------------------------------
        score = data.get("score")
        if score is None:
            rep.unavailable.append("risk_raw")
        else:
            rep.risk_raw = safe_float(score)
            rep.risk_scale = "rugcheck:lower_is_safer"
            if rep.risk_raw > config.SAFETY["rugcheck_raw_block"]:
                rep.hard_rejects.append(f"risk_score_{rep.risk_raw:g}")

        # -- danger flags -----------------------------------------
        risks = data.get("risks") or []
        for r in risks:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            level = (r.get("level") or "").lower()
            rep.flags.append(name)
            if level == "danger":
                low = name.lower()
                if (config.SAFETY["reject_creator_rug_history"]
                        and any(p in low for p in CREATOR_RUG_PATTERNS)):
                    rep.hard_rejects.append("creator_rug_history")

        # -- holder distribution ----------------------------------
        holders = data.get("topHolders")
        if not holders:
            rep.unavailable.extend(["top_holder_pct", "top10_pct"])
        else:
            # Insider-tagged wallets are excluded from concentration, and so
            # are pools, programs and exchange accounts — most of a young
            # token's float sits in the AMM by design.
            infra = [h for h in holders if is_solana_infrastructure(h)]
            outside = [h for h in holders
                       if not h.get("insider") and not is_solana_infrastructure(h)]
            if infra:
                rep.flags.append(f"excluded_{len(infra)}_infra_holders")
            # Insider supply was filtered out of concentration and then
            # discarded — it is the clearest bundling tell in the response.
            insiders = [h for h in holders if h.get("insider")]
            rep.insider_pct = round(
                sum(safe_float(h.get("pct")) for h in insiders), 2)
            pcts = sorted((safe_float(h.get("pct")) for h in outside), reverse=True)
            if pcts:
                rep.top_holder_pct = pcts[0]
                rep.top10_pct = sum(pcts[:10])
                if rep.top_holder_pct > config.SAFETY["max_top_holder_pct"]:
                    rep.hard_rejects.append(
                        f"top_holder_{rep.top_holder_pct:.0f}pct")
                if rep.top10_pct > config.SAFETY["max_top10_pct"]:
                    rep.hard_rejects.append(f"top10_{rep.top10_pct:.0f}pct")
            else:
                rep.unavailable.extend(["top_holder_pct", "top10_pct"])
        rep.holder_count = safe_int(data.get("totalHolders")) or None

        # -- LP lock, graduated pools only ------------------------
        markets = data.get("markets")
        if markets is None:
            rep.unavailable.append("lp_locked_pct")
        else:
            graduated = [m for m in markets
                         if (m.get("marketType") or "") not in BONDING_CURVE_MARKETS]
            rep.has_graduated_pool = bool(graduated)
            if not graduated:
                # Still on the curve — LP lock is not a meaningful question.
                rep.lp_locked_pct = 100.0
                rep.flags.append("bonding_curve")
            else:
                locks = [safe_float((m.get("lp") or {}).get("lpLockedPct"))
                         for m in graduated]
                locks = [x for x in locks if x is not None]
                if not locks:
                    rep.unavailable.append("lp_locked_pct")
                else:
                    rep.lp_locked_pct = max(locks)
                    if rep.lp_locked_pct < config.SAFETY["min_lp_locked_pct"]:
                        rep.hard_rejects.append(
                            f"lp_unlocked_{rep.lp_locked_pct:.0f}pct")

        # -- how long the lock actually lasts ---------------------
        # A lock expiring this afternoon is not protection. RugCheck returns
        # unlock timestamps in `lockers`, in a response already being fetched
        # — Surgeon read the percentage and discarded the horizon.
        lockers = data.get("lockers") or {}
        if isinstance(lockers, dict) and lockers:
            soonest = None
            burned = False
            for entry in lockers.values():
                if not isinstance(entry, dict):
                    continue
                kind = str(entry.get("type") or "").lower()
                if "burn" in kind:
                    burned = True
                    continue
                unlock = safe_float(entry.get("unlockDate"))
                if unlock > 0:
                    hours = (unlock - time.time()) / 3600
                    if soonest is None or hours < soonest:
                        soonest = hours
            if soonest is not None:
                rep.lp_unlock_hours = round(soonest, 2)
                rep.lp_lock_kind = "timed"
                if soonest <= 0:
                    # Heavily penalised in risk.py rather than rejected here.
                    # An expired lock is a real danger, but it can also mean
                    # stale locker data or LP burned after the lock lapsed —
                    # and turning an ambiguous reading into a veto is the
                    # mistake that cost us the Cancer Vaccine.
                    rep.flags.append("lp_lock_expired")
                elif soonest < config.SAFETY["lp_min_lock_hours"]:
                    rep.flags.append(f"lp_unlocks_in_{soonest:.0f}h")
            elif burned:
                rep.lp_lock_kind = "burned"

        # A reading of exactly zero on a graduated pool is often "could not
        # read this pool type" rather than "the deployer holds the LP" —
        # RugCheck cannot see inside every venue pump.fun graduates into.
        #
        # Deciding which it is by corroboration: a genuinely dev-controlled
        # LP does not coexist with a deployer holding nothing, no insider
        # supply and a large holder base. The Cancer Vaccine was rejected on
        # this with 17,900 holders, 0% insiders and 0% creator holdings.
        if rep.lp_locked_pct == 0.0:
            contradicted = (
                (rep.creator_holds_pct is not None
                 and rep.creator_holds_pct <= config.SAFETY["lp_zero_creator_max"])
                and (rep.insider_pct is not None
                     and rep.insider_pct <= config.SAFETY["lp_zero_insider_max"])
                and (rep.holder_count or 0) >= config.SAFETY["lp_zero_holder_min"]
            )
            if contradicted:
                rep.hard_rejects = [r for r in rep.hard_rejects
                                    if not r.startswith("lp_unlocked")]
                rep.lp_locked_pct = None
                rep.unavailable.append("lp_locked_pct")
                rep.flags.append("lp_unreadable_pool")

        # -- creator ----------------------------------------------
        creator = data.get("creator")
        if creator and creator != "11111111111111111111111111111111":
            rep.creator = creator
            supply = safe_float(token.get("supply"))
            bal = safe_float(data.get("creatorBalance"))
            if supply > 0:
                rep.creator_holds_pct = round(bal / supply * 100, 4)
        else:
            rep.unavailable.append("creator")

        return self.apply_common_gates(rep)

    # ── CREATOR ACTIVITY ──────────────────────────────────────────
    def creator_activity(self, ca: str, creator: Optional[str] = None) -> CreatorActivity:
        act = CreatorActivity(ca=ca, chain=self.key, creator=creator,
                              last_checked=int(time.time()))

        if not config.HELIUS_API_KEY:
            act.available = False
            act.note = "HELIUS_API_KEY not set"
            return act

        if not creator:
            rep = self.safety(ca)
            creator = rep.creator
            act.creator = creator
        if not creator:
            act.available = False
            act.note = "creator unknown"
            return act

        txs = http_get(
            HELIUS_TX.format(addr=creator),
            params={"api-key": config.HELIUS_API_KEY, "limit": 25},
            timeout=15,
        )
        if not isinstance(txs, list):
            act.available = False
            act.note = "helius unreachable"
            return act

        sold_total = 0.0
        for tx in txs:
            if tx.get("type") != "SWAP":
                continue
            for tr in (tx.get("tokenTransfers") or []):
                if tr.get("mint") != ca:
                    continue
                # Tokens leaving a creator-associated account = distribution.
                if tr.get("fromUserAccount"):
                    sold_total += safe_float(tr.get("tokenAmount"))

        if sold_total > 10_000:
            act.sold = True
            act.sold_amount = sold_total
        return act
