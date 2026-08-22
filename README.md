# Surgeon v2 — multi-chain signal engine

Signal-only. No keys, no execution, no trade-router. Surgeon finds and scores
alpha, fires it to Telegram, and watches open positions. You take the trade.

## Chains

| chain | kind | market | safety | status |
|---|---|---|---|---|
| Solana | SVM | DexScreener | RugCheck + Helius | ready |
| Robinhood Chain | EVM | DexScreener | GoPlus + Blockscout | ids need verifying |
| Base | EVM | DexScreener | GoPlus + Blockscout | ready |
| BNB Chain | EVM | DexScreener | GoPlus | ready |
| Monad | EVM | DexScreener | GoPlus | ids need verifying |

Adding a chain later = one entry in `config.CHAINS`. If it is EVM, no new code
at all — `EvmAdapter` already handles it.

## First run

```bash
pip install -r requirements.txt

# 1. resolve the identifiers marked VERIFY in config.py
python3 discover_chain_ids.py

# 2. paste the results into config.CHAINS, then prove each chain works
python3 test_adapters.py

# 3. drill into one chain or one token
python3 test_adapters.py base
python3 test_adapters.py 0xYourContractAddress
```

`test_adapters.py` prints every safety field and labels anything it could not
fetch as `UNAVAILABLE`. That is the point — see the gaps rather than trust a
zero.

## Environment

Required: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
Solana dev-wallet monitoring: `HELIUS_API_KEY`
Persistence: `SUPABASE_URL`, `SUPABASE_KEY`
Optional, raises GoPlus rate limits: `GOPLUS_APP_KEY`, `GOPLUS_APP_SECRET`

## Layout

```
config.py                 all tuning: chains, thresholds, scoring, channels
chain_base.py             adapter contract + DexScreener + HTTP retry
chain_solana.py           RugCheck + Helius
chain_evm.py              GoPlus + Blockscout — serves all four EVM chains
chains.py                 registry, address routing, chain resolution
discover_chain_ids.py     one-time identifier resolution
test_adapters.py          smoke test
```

## Design rules

1. **Never invent a number.** Missing safety data goes in `unavailable` and
   renders as `n/a`. v1 defaulted to zero and showed clean tokens that had
   never been checked.
2. **Nothing imports a chain module directly.** Everything goes through
   `get_adapter()`, so the scoring core is chain-blind.
3. **Alerts are not gated on tracking state.** v1 nested the Telegram send
   inside `if not already_tracking`, which silently killed every repeat
   second-moon signal.
4. **Deepest pool wins.** Market data comes from the deepest pair, and a CA
   deployed on several EVM chains resolves to wherever the liquidity is.

## What is next

See `ROADMAP.md`. The position watcher is built, so outcomes now accumulate.
Next is derived smart money: promote wallets that were early in Surgeon's
own winners, rather than trusting a hand-researched list.

## Judging the changes

`CHANGES.md` records every adjustment, what it was meant to fix, and what
evidence would show it worked or should be removed — written before the
outcomes arrived, so the test cannot be moved afterwards.
