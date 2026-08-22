# Surgeon-Pro

**Improved signal engine built on the proven Surgeon v2 architecture.**

Signal-only. No keys, no execution. Surgeon-Pro finds and scores alpha, fires higher-quality signals to a dedicated Telegram channel, and watches open positions with significantly better exit logic.

This is a parallel evolution. The original Surgeon---Main repo remains untouched.

## Key Improvements over original

### 1. Exit Logic Overhaul (Highest Impact)
- **Volume Fade** is now the primary profitable exit (data: +80 avg final vs Trailing –9).
- Much wider, smarter trailing that only tightens on real monsters (≥200% peaks).
- Hard protective floor once a position has been strongly profitable.
- Slightly longer MAX_HOLD for runners.

### 2. Conviction Scoring Refinements
- EXPLOSIVE momentum weight significantly increased (strongest quality signal in the data).
- Higher weight for confirmed smart money wallets.
- Ready for interaction bonuses and toxic band filters.

### 3. Derived Smart Money Foundation
- Architecture supports promoting wallets from the system’s own winning trades.
- Higher scoring impact for confirmed wallets.

### 4. Isolation
- Dedicated Telegram bot + channel (Pro).
- Independent config and deployment.

## Design Rules
1. Never invent a number. Missing data = `UNAVAILABLE`.
2. Chain-agnostic core via adapters.
3. Alerts are not gated on tracking state.
4. Outcome data is the source of truth.

## Quick Start

```bash
pip install -r requirements.txt

cp .env.example .env
# edit .env with your keys

python3 test_adapters.py
python3 scan.py --test-alert
