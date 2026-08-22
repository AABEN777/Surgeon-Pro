# Surgeon v2 — build plan

Signal only. No keys, no execution. Everything below is about producing
better signals and knowing which ones were right.

---

## Built

- Five chain adapters — Solana, Robinhood, Base, BNB Chain, Monad
- Discovery: GeckoTerminal new pools + DexScreener promoted, merged
- Market data: DexScreener with GeckoTerminal fallback, batched 30/request
- Safety: RugCheck (Solana), GoPlus + Blockscout (EVM), never invents a value
- Scoring: tiers, momentum, launch phase, narrative, conviction 0–100
- Watchlist: park too-young tokens, re-check as they mature, retire the spent
- Social velocity: 25 Telegram channels, cross-channel consensus
- Smart money: Solana wallets via Helius
- Macro regime: SOL 24h move → BULLISH / NEUTRAL / CAUTION / PAUSE
- Alerts: Telegram HTML, escaped, copy-on-tap CA, visible score breakdown
- Persistence: Supabase, in-memory fallback for offline runs
- 95 offline tests

---

## 1. Position watcher — BUILT

`watch.py`. Tracks every alerted token and notifies on TP1/TP2/TP3, stop,
trailing stop after TP2, volume fade, whale concentration appearing after
entry, bonding-curve graduation, time stops and max hold.

Outcomes are graded on both final and peak PnL: a token that ran 300% and
gave it back was a correct call badly exited, and grading that as a loss
would poison every weight learned from this data.

Results land in `signals`, which unblocks items 2, 4 and 5.

Still to wire: dev-wallet-sold needs the creator's holding recorded at
signal time to compare against.

## 2. Derived smart money — NEXT

The wallets currently tracked were hand-researched on a machine that no
longer exists, and nothing has verified they are still any good. Third-party
leaderboards are not a fix — fomo has exactly the right data but no public
API, and no certainty it exposes addresses rather than usernames.

Better source: **Surgeon's own winners.**

1. When a signal closes as a winner, pull its early holders
2. Wallets appearing across several unrelated winners become candidates
3. Promote into `smart_wallets`, tagged with the evidence
4. Measure existing entries the same way — retire ones that stop earning

Self-tuning, tied to this signal universe rather than someone else's, and
dependent on nothing external. Works on every chain where holder data is
available.

**Needs:** outcome tracking (item 1).

---

## 3. CA analyzer — BUILT

`analyze.py`. Paste an address, get exactly what Surgeon computes and which
gate decides it. Chain detected from address format, then resolved by asking
which chain actually holds liquidity.

Three ways in: the command line, the Actions tab via workflow_dispatch, or by
sending an address to the bot — the last polls every five minutes rather than
listening, since scheduled jobs cannot hold a socket open.

Built because "would Surgeon have caught this?" kept being answered by
reasoning about thresholds instead of running them.

## 3b. CA analyzer (original note)

Paste a contract address to the bot, get the full readout: market, safety
including top-holder percentage, conviction with breakdown, chain
auto-detected from address format. The chain resolution already exists in
`chains.resolve_chain()`.

Independent of everything else — buildable at any point.

---

## 4. Channel accuracy scoring

Twenty-five channels are weighted equally. Some are consistently early,
some consistently late, some noise. Track each channel's calls against
outcomes over a rolling window and weight the social bonus by hit rate.

v1 never had enough overlap to do this — only two tokens appeared in both
mentions and trades. Needs a few hundred outcomes.

**Needs:** outcome tracking (item 1).

---

## 5. Narrative auto-retune

Two layers now score narrative. `config.NARRATIVES` is a fixed list with
weights carried from the old VPS history. `meta.py` learns the current meta
from whatever is actually running — every scan already fetches a hundred
tokens per chain with their 24h change, and the words shared by the ones
performing are the meta.

The fixed weights still need retuning against realised outcomes;
`v_narrative_performance` computes them. The learned layer needs no retuning
by design.

## 5b. Narrative weight retune (original)

`NARRATIVES` weights are fixed guesses carried over from v1's trade history
(AI +8, ANIMAL +5, POLITICAL −15, ELON −8). `v_narrative_performance` already
computes real win rates per narrative; feed those back so the weights follow
evidence rather than memory.

**Needs:** outcome tracking (item 1).

---

## 6. Scam heuristics — remaining two

Four of King's six tells are live in `risk.py`: top holder over 3.5%, volume
under 80% of cap, bundled supply over 15%, plus deployer holdings and thin
holder counts. Scored as warnings, with three severe flags blocking outright.

Two are not built:

**Fresh-wallet funding.** Trading terminals show this by checking when each
top holder was funded and from where. Reproducible via Helius on Solana —
walk the top holders, look at first funding transaction age and whether they
share a funder. Costs a request per holder, so it needs to run only on
tokens that already passed everything else. No equivalent on EVM.

**Fees paid against volume.** Roughly 1% of genuine volume should appear as
fees, and a painted chart shows volume without them. No free API exposes
this — DexScreener and GeckoTerminal both omit it — so it means summing fee
transfers per pool ourselves.

**X account quality** is deferred rather than planned: it needs the Twitter
API at $200/month plus account age and location analysis.

## 7. Buildable now, not yet built

**LP lock expiry — BUILT.** Unlock timestamps parsed from RugCheck's
`lockers`, surfaced in the alert ("LP 100% unlocks in 90m") and scored:
-6 inside a day, -12 inside twelve hours, -20 inside two, -25 once expired.
Burned LP and locks without an expiry are unaffected. Penalised rather than
rejected, since an expired lock can also mean stale locker data or liquidity
burned afterwards.

**Daily briefing.** One message: win rate, best and worst chain, conviction
band performance, current meta, watchlist conversion. Replaces running SQL by
hand every check-in and makes drift visible without being asked.

**The 50-150% penalty band.** first_moon tokens up 50-150% at entry won 11.7%
across 94 trades — the worst cell with a real sample, and a third of all
signals land there. Both extremes beat it. Wait for 250+ trades before acting.

## 8. EVM holder data gap

On Base and BNB Chain, tokens under roughly fifteen minutes old have no
holder distribution at all — GoPlus has not scanned them, Blockscout 404s.
Every early EVM signal therefore scores with `safety_partial −8` and an
unchecked top-holder field.

Robinhood is fine; its Blockscout instance indexes from block one.

Options: re-check safety at +15/+60min via the position watcher and alert if
concentration turns out ugly; find a faster indexer; or compute distribution
directly from an RPC.

---

## 9. Paid data — evaluated, deferred

**Solana Tracker Data API.** 70+ endpoints including trending by timeframe,
recently graduated pump tokens, top-100 holders, and a 1-10 risk score
covering snipers, bundlers and insider wallets. v1 used it on the VPS.

Well matched to the discovery gap — "recently graduated pump tokens" is
precisely the Cancer Vaccine, a pump.fun token that had moved to Meteora.

Not taken because the free tier is 2,500 requests total, which is a trial
rather than a tier: 96 scans a day exhausts it in under a fortnight. Paid
starts around 50 euro a month.

Deferred in favour of deepening GeckoTerminal discovery first, which is free
and addresses the same gap. Revisit if that does not close it — then the
purchase is justified rather than hopeful.

**fomo and J7 Tracker** — no public API. Both are consumer products whose
trackers depend on an authenticated X session, which scheduled jobs cannot
hold. Use them by hand and paste contracts to the analyzer instead.

## 10. Going live

Alerting is deliberately fail-closed. Sending requires **both** `--live` on
the command and `SURGEON_LIVE=true` in the environment; either alone stays
dry. Confirm delivery first with `python3 scan.py --test-alert`.

---

## Deferred

- **EVM smart money** — Helius is Solana-only, no per-chain wallet indexer found
- **PumpFun WebSocket watcher** — cannot survive on scheduled Actions runs
- **fomo integration** — revisit if a public API appears
