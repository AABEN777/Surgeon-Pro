"""
Persistence.

GitHub Actions gives us no disk between runs, so anything Surgeon needs to
remember — what it already alerted on, which positions are open, which
channels mentioned what — lives in Supabase.

Everything degrades to in-memory if credentials are absent, so the whole
system still runs and tests offline. A missing database must never take the
scanner down; it just makes it forgetful.
"""

from __future__ import annotations

import time
import json
import logging
from typing import Any, Optional

import requests

import config

log = logging.getLogger("surgeon.store")

_session = requests.Session()
_session.headers.update({"User-Agent": config.USER_AGENT})

# in-memory fallback
_mem: dict[str, list[dict]] = {"signals": [], "mentions": [],
                               "positions": [], "watchlist": [],
                               "meta_terms": []}


class Store:
    """Thin Supabase REST client. No SDK, no migrations, no ORM."""

    def __init__(self, url: str = "", key: str = ""):
        self.url = (url or config.SUPABASE_URL).rstrip("/")
        self.key = key or config.SUPABASE_KEY
        self.live = bool(self.url and self.key)
        if not self.live:
            log.warning("Supabase not configured — using in-memory store. "
                        "State will not survive this run.")

    # ── plumbing ──────────────────────────────────────────────────
    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _req(self, method: str, table: str, params: Optional[dict] = None,
             body: Any = None, extra_headers: Optional[dict] = None,
             timeout: int = 15):
        if not self.live:
            return None
        url = f"{self.url}/rest/v1/{table}"
        try:
            r = _session.request(method, url, headers=self._headers(extra_headers),
                                 params=params, json=body, timeout=timeout)
            if r.status_code in (200, 201, 204):
                if r.text and r.text.strip():
                    try:
                        return r.json()
                    except ValueError:
                        return None
                return []
            log.warning("supabase %s %s -> %s %s", method, table,
                        r.status_code, r.text[:200])
            return None
        except Exception as e:
            log.warning("supabase %s %s failed: %s", method, table, e)
            return None

    @staticmethod
    def _mem_filter(rows: list[dict], params: Optional[dict]) -> list[dict]:
        """
        Apply PostgREST-style filters to the in-memory store.

        Without this the fallback returned every row regardless of filter,
        so offline runs silently disagreed with live ones — closed positions
        still showed as open, and a CA mentioned once looked like consensus.
        """
        if not params:
            return list(rows)

        ops = {
            "eq":  lambda a, b: str(a) == b,
            "neq": lambda a, b: str(a) != b,
            "gt":  lambda a, b: float(a or 0) >  float(b),
            "gte": lambda a, b: float(a or 0) >= float(b),
            "lt":  lambda a, b: float(a or 0) <  float(b),
            "lte": lambda a, b: float(a or 0) <= float(b),
        }
        out = list(rows)
        for field, expr in params.items():
            if field in ("select", "order", "limit", "on_conflict"):
                continue
            if not isinstance(expr, str) or "." not in expr:
                continue
            op, _, val = expr.partition(".")
            fn = ops.get(op)
            if not fn:
                continue
            kept = []
            for r in out:
                try:
                    if fn(r.get(field), val):
                        kept.append(r)
                except (TypeError, ValueError):
                    continue
            out = kept

        order = params.get("order")
        if order:
            # PostgREST syntax: "col.asc", "col.desc.nullsfirst", ...
            parts = order.split(".")
            key = parts[0]
            direction = parts[1] if len(parts) > 1 else "asc"
            nulls = parts[2] if len(parts) > 2 else ""
            desc = direction.startswith("desc")
            nulls_first = ("nullsfirst" in nulls) or (not nulls and desc)

            def sort_key(r):
                v = r.get(key)
                missing = v is None
                rank = 0 if (missing == nulls_first) else 1
                if desc:
                    rank = 1 - rank
                return (rank, v if not missing else 0)

            out.sort(key=sort_key, reverse=desc)

        limit = params.get("limit")
        if limit:
            try:
                out = out[:int(limit)]
            except ValueError:
                pass
        return out

    def select(self, table: str, params: Optional[dict] = None) -> list[dict]:
        if not self.live:
            return self._mem_filter(_mem.get(table, []), params)
        return self._req("GET", table, params=params) or []

    def insert(self, table: str, rows: list[dict] | dict) -> list[dict]:
        rows = rows if isinstance(rows, list) else [rows]
        if not self.live:
            _mem.setdefault(table, []).extend(rows)
            return rows
        return self._req("POST", table, body=rows,
                         extra_headers={"Prefer": "return=representation"}) or []

    def upsert(self, table: str, rows: list[dict] | dict,
               on_conflict: str = "id") -> list[dict]:
        rows = rows if isinstance(rows, list) else [rows]
        if not self.live:
            store = _mem.setdefault(table, [])
            for row in rows:
                match = next((r for r in store
                              if r.get(on_conflict) == row.get(on_conflict)), None)
                if match:
                    match.update(row)
                else:
                    store.append(row)
            return rows
        return self._req("POST", table, params={"on_conflict": on_conflict},
                         body=rows,
                         extra_headers={"Prefer": "resolution=merge-duplicates,"
                                                  "return=representation"}) or []

    def update(self, table: str, match: dict, changes: dict) -> list[dict]:
        if not self.live:
            out = []
            for row in _mem.get(table, []):
                if all(row.get(k) == v for k, v in match.items()):
                    row.update(changes)
                    out.append(row)
            return out
        params = {k: f"eq.{v}" for k, v in match.items()}
        return self._req("PATCH", table, params=params, body=changes,
                         extra_headers={"Prefer": "return=representation"}) or []

    # ── alert dedupe ──────────────────────────────────────────────
    def recently_alerted(self, minutes: Optional[int] = None) -> dict[str, float]:
        """
        {ca: last_alert_epoch} inside the window.

        Deliberately keyed on time alone. v1 suppressed alerts for anything
        already being tracked, which silenced every repeat signal.
        """
        window = (minutes if minutes is not None
                  else config.REALERT_COOLDOWN_MINUTES)
        cutoff = time.time() - window * 60
        rows = self.select("signals", {
            "select": "ca,alerted_at",
            "alerted_at": f"gte.{cutoff}",
            "order": "alerted_at.desc",
            "limit": "500",
        })
        out: dict[str, float] = {}
        for r in rows:
            ca = r.get("ca")
            ts = float(r.get("alerted_at") or 0)
            if ca and ts > out.get(ca, 0):
                out[ca] = ts
        return out

    # ── signals ───────────────────────────────────────────────────
    def record_signal(self, ev, adapter, sent_ok: bool) -> dict:
        m, s, c = ev.market, ev.safety, ev.conviction
        row = {
            "ca":              m.ca,
            "chain":           ev.chain,
            "name":            m.name,
            "symbol":          m.symbol,
            "tier":            ev.tier.tier,
            "conviction":      c.score,
            "band":            c.band,
            "momentum":        c.momentum,
            "launch_phase":    c.launch,
            "narrative":       c.narrative,
            "session":         c.session,
            "entry_price":     m.price_usd,
            "liquidity_usd":   m.liquidity_usd,
            "fdv":             m.fdv,
            "volume_24h":      m.volume_24h,
            "change_5m":       m.change_5m,
            "change_1h":       m.change_1h,
            "age_hours":       m.age_hours if m.age_known else None,
            "dex":             m.dex,
            "launchpad":       m.launchpad,
            "social_channels": c.social_channels,
            "smart_wallets":   c.smart_wallets,
            "safety_verdict":  s.verdict,
            # Needed by the watcher: DEV_SOLD compares the deployer's holding
            # now against what it was at signal time. Without this the check
            # could never fire, because there was nothing to compare against.
            "creator_holds_pct": s.creator_holds_pct,
            "dev_held":        (s.creator_holds_pct or 0) > 0.01,
            "top_holder_pct":  s.top_holder_pct,
            "lp_locked_pct":   s.lp_locked_pct,
            "safety_sources":  ",".join(s.sources),
            "unavailable":     ",".join(s.unavailable),
            "breakdown":       c.explain(),
            "from_watchlist":  getattr(ev, "from_watchlist", False),
            "alerted_at":      time.time(),
            "alert_sent":      sent_ok,
            "outcome":         "pending",
        }
        self.insert("signals", row)
        return row

    def open_positions(self, chain: Optional[str] = None) -> list[dict]:
        params = {"select": "*", "outcome": "eq.pending",
                  "order": "alerted_at.desc", "limit": "200"}
        if chain:
            params["chain"] = f"eq.{chain}"
        return self.select("signals", params)

    def close_position(self, ca: str, outcome: str, exit_type: str,
                       final_pnl: float, peak_pnl: float = 0.0):
        return self.update("signals", {"ca": ca, "outcome": "pending"}, {
            "outcome":    outcome,
            "exit_type":  exit_type,
            "final_pnl":  final_pnl,
            "peak_pnl":   peak_pnl,
            "closed_at":  time.time(),
        })

    def mark_watch_event(self, ca: str, event: str, pnl: float):
        """Record a fired watch event so it does not repeat every cycle."""
        return self.insert("watch_events", {
            "ca": ca, "event": event, "pnl": pnl, "fired_at": time.time(),
        })

    def fired_watch_events(self, ca: str) -> set[str]:
        rows = self.select("watch_events",
                           {"select": "event", "ca": f"eq.{ca}", "limit": "50"})
        return {r.get("event") for r in rows if r.get("event")}

    # ── watchlist ─────────────────────────────────────────────────
    # Tokens rejected only for being too young. Discovery surfaces pools
    # minutes old, the entry-delay filter wants ten minutes, and by the next
    # scan they have dropped out of the new-pool feed. Waiting is correct;
    # forgetting is not.
    def watch_later(self, ca: str, chain: str, age_hours: float,
                    name: str = "", symbol: str = "") -> bool:
        """
        Park a token, once.

        Discovery re-surfaces the same pools between scans, and an upsert on
        every sighting overwrote first_seen and reset checks to zero — so a
        token could be re-checked repeatedly and still look untouched, and
        could never age out of the queue. Existing entries are left alone.
        """
        existing = self.select("watchlist",
                               {"select": "ca", "ca": f"eq.{ca}", "limit": "1"})
        if existing:
            return False
        self.insert("watchlist", {
            "ca": ca, "chain": chain, "name": name, "symbol": symbol,
            "first_seen": time.time(),
            "first_age_hours": age_hours,
            "checks": 0,
        })
        return True

    def due_for_recheck(self, max_age_hours: float = 6.0,
                        min_age_hours: Optional[float] = None,
                        recheck_gap_seconds: int = 240,
                        limit: int = 200) -> list[dict]:
        """
        Parked tokens that have actually aged into range.

        Maturity is computed rather than assumed: a token parked at 0.03h two
        minutes ago is still too young, and re-fetching it only spends a rate
        limit to learn what we already knew. Oldest first, so nothing starves.
        """
        if min_age_hours is None:
            min_age_hours = config.THRESHOLDS["first_moon"]["min_age_hours"]

        now = time.time()
        cutoff = now - max_age_hours * 3600
        # Ordered by least-recently-checked, not oldest-first. Oldest-first
        # meant the same 45 tokens filled every slot on every scan while the
        # rest of the queue was never looked at once.
        rows = self.select("watchlist", {
            "select": "*",
            "first_seen": f"gte.{cutoff}",
            "order": "last_checked.asc.nullsfirst",
            "limit": "600",
        })

        due = []
        for r in rows:
            first_seen = float(r.get("first_seen") or 0)
            born_at = first_seen - float(r.get("first_age_hours") or 0) * 3600
            age_now = (now - born_at) / 3600
            if age_now < min_age_hours:
                continue                      # still inside the delay window
            if int(r.get("checks") or 0) >= config.WATCH["max_watchlist_checks"]:
                continue                      # exhausted, purge will collect it
            last = float(r.get("last_checked") or 0)
            if last and (now - last) < recheck_gap_seconds:
                continue                      # checked moments ago
            r["_age_now"] = round(age_now, 3)
            due.append(r)
            if len(due) >= limit:
                break
        return due

    def purge_watchlist(self, max_age_hours: float = 6.0) -> int:
        """
        Delete entries past their useful life.

        Rows were only ever removed when re-checked, but due_for_recheck
        ignores anything older than the window — so stale entries became
        permanent and buried the fresh ones behind them.
        """
        cutoff = time.time() - max_age_hours * 3600
        max_checks = config.WATCH["max_watchlist_checks"]

        def dead(r):
            return (float(r.get("first_seen") or 0) < cutoff
                    or int(r.get("checks") or 0) >= max_checks)

        if not self.live:
            before = len(_mem.get("watchlist", []))
            _mem["watchlist"] = [r for r in _mem.get("watchlist", [])
                                 if not dead(r)]
            return before - len(_mem["watchlist"])

        stale = self.select("watchlist", {"select": "ca",
                                          "first_seen": f"lt.{cutoff}",
                                          "limit": "500"})
        self._req("DELETE", "watchlist", params={"first_seen": f"lt.{cutoff}"})
        spent = self.select("watchlist", {"select": "ca",
                                          "checks": f"gte.{max_checks}",
                                          "limit": "500"})
        self._req("DELETE", "watchlist", params={"checks": f"gte.{max_checks}"})
        return len(stale) + len(spent)

    def watchlist_size(self, chain: Optional[str] = None) -> int:
        params = {"select": "ca", "limit": "1000"}
        if chain:
            params["chain"] = f"eq.{chain}"
        return len(self.select("watchlist", params))

    def drop_from_watchlist(self, ca: str):
        if not self.live:
            _mem["watchlist"] = [r for r in _mem.get("watchlist", [])
                                 if r.get("ca") != ca]
            return []
        return self._req("DELETE", "watchlist", params={"ca": f"eq.{ca}"})

    def bump_check(self, ca: str, checks: int):
        return self.update("watchlist", {"ca": ca},
                           {"checks": checks + 1, "last_checked": time.time()})

    # ── meta terms ────────────────────────────────────────────────
    def record_meta_terms(self, rows: list[dict]):
        return self.insert("meta_terms", rows) if rows else []

    # ── social mentions ───────────────────────────────────────────
    def record_mentions(self, rows: list[dict]):
        return self.insert("mentions", rows) if rows else []

    def recent_mentions(self, seconds: Optional[int] = None) -> list[dict]:
        window = seconds or config.SOCIAL_WINDOW_SECONDS
        cutoff = time.time() - window
        return self.select("mentions", {
            "select": "ca,chain,channel,seen_at",
            "seen_at": f"gte.{cutoff}",
            "limit": "2000",
        })

    def channels_for(self, ca: str, seconds: Optional[int] = None) -> list[str]:
        window = seconds or config.SOCIAL_WINDOW_SECONDS
        cutoff = time.time() - window
        rows = self.select("mentions", {
            "select": "channel",
            "ca": f"eq.{ca}",
            "seen_at": f"gte.{cutoff}",
            "limit": "100",
        })
        return sorted({r["channel"] for r in rows if r.get("channel")})

    # ── learning ──────────────────────────────────────────────────
    def closed_trades(self, limit: int = 2000) -> list[dict]:
        return self.select("signals", {
            "select": "*",
            "outcome": "neq.pending",
            "order": "closed_at.desc",
            "limit": str(limit),
        })

    def stats(self) -> dict:
        # Backlog rows were signalled hours before anything watched them, so
        # they measure a gap in tracking rather than the quality of a call.
        excluded = {"DATA_ERROR", "BACKLOG_UNTRACKED"}
        closed = [t for t in self.closed_trades()
                  if str(t.get("outcome", "")).upper() not in excluded]
        if not closed:
            return {"trades": 0, "wins": 0, "win_rate": 0.0}
        wins = [t for t in closed
                if str(t.get("outcome", "")).upper() in
                ("WIN", "BIG_WIN", "MOON", "WEAK_WIN")]
        return {
            "trades":   len(closed),
            "wins":     len(wins),
            "win_rate": round(len(wins) / len(closed) * 100, 1),
        }


# module-level default
store = Store()
