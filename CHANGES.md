# Changes to judge

## Verdicts from the first full dataset (1,123 closed trades)

**Reverted — boosted widening.** 21.8% on 110 trades against first_moon's
25.3%, worst average close in the system at -45, and not one of the fifteen
biggest winners was boosted. The 32.1% that justified widening was 28 trades
of luck. Back to 24h / $20k FDV.

**Removed — DEAD session penalty.** Five of the fifteen biggest winners were
taxed ten points for launching overnight: Bullballs (+4,332%), Caesar
(+794%), Fatal Boner (+832%), Burpcoin, Onigiricoin. The gates still tighten
in dead hours; the score no longer charges a token for its launch time.

**Changed — top holder scaled by age.** Halved inside the first hour. Buying
Power took -14 and ran +3,128%; Caesar took -14 and ran +794%. Concentration
on a twenty-minute-old token is what an early runner looks like. Severe
concentration stays severe at any age.

**Changed — unverified muted rather than penalised twice.** Unflagged tokens
rug at 16.0%, flagged at 10.9%. Rugs come from what cannot be checked, so
unverifiable tokens no longer interrupt — but the penalty drops to -10 so
they stay above the tracking floor and keep feeding the outcome data.

**Kept — scam heuristics.** Flagged tokens win 25.7% against 21.1% and rug at
10.9% against 16.0%.

**Kept — meta detection.** Theme metas 32.6%, word metas 25.7% with an average
peak of 86, against a 22.0% baseline on 967 trades. My copycat worry was
wrong: word metas have the highest peaks in the system.

**Not raised — score floors.** Conviction is flat from 30 to 69 and the
fifteen biggest winners have a median score of 51. Raising the floor would
cut winners and losers in equal measure — fewer alerts at the same win rate,
which is a worse deal. Volume was tightened through safety instead.

Net effect on the fifteen biggest winners: 8 would have reached the phone
before, 13 now.

## Still unresolved

**Trailing stops are the largest leak.** 156 exits, average peak +122%,
average close -8% — giving back 130 points. Volume fade gives back 21 and
closes at +79. Not yet touched, because the two largest winners (+5,900% and
+4,332%) exited on MAX_HOLD after running the full eight hours, so trailing
harder would cut off exactly the tokens that pay for everything else.

---


Every adjustment made in the last two days, what it was meant to fix, and
what evidence would show it worked or should be removed.

Written before the outcomes are in, so the test cannot be moved afterwards.

Entries marked **MINE** rest on my judgement rather than King's data. Those
are the first candidates for removal if they cannot show their worth.

---

## Backed by outcome data

### Boosted widened, first_moon left alone
Boosted won 32.1% across 28 trades against first_moon's 17.9% across 184.
Boosted's ceiling went to 36h, FDV floor to $15k, volume floor to $3.5k.

*Right if:* boosted's share of signals rises and its win rate holds above 25%.
*Wrong if:* boosted's win rate falls toward first_moon's — the original edge
was small-sample luck and the wider gates diluted it.

### Base gates raised hard
46 trades, 13% win rate, average peak +4%. First_moon now needs 45% hourly
change, $10k volume, 0.35 turnover, $12k liquidity.

*Right if:* Base sends far fewer signals but its win rate approaches the
other chains'.
*Wrong if:* Base goes silent entirely — the bar became a wall, and it should
be lowered rather than left as a chain we pay to scan and never hear from.

### first_moon momentum gate reverted to 15%
I raised it to 25% inferring "tighten the weak tier" from data that only said
"older tokens do better". It blocked 83 of 96 Solana candidates. Entry
momentum showed no stable direction across 515 trades — down within boosted
and second_moon, up within first_moon.

*Right if:* Solana's tier rejections stop being dominated by `1h`.
*Wrong if:* first_moon's win rate falls below 15% — the looser gate is
letting through tokens that were being correctly excluded.

### Volume fade loosened to 0.45 ratio, +10% floor
Volume fade closed at +78% against a +101% peak. Trailing closed at -21%
against a +95% peak. Momentum dies before price does.

*Right if:* VOLUME_FADE's share of exits rises and its average close stays
well above other exit types.
*Wrong if:* its average close drops toward the others — firing earlier is
catching noise rather than genuine fade.

### Watcher every 5 minutes instead of 15
Trailing stops were closing at -21% on +95% peaks because a fifteen-minute
poll only saw the drawdown once the move was over.

*Right if:* TRAIL_STOP's average close moves up substantially.
*Wrong if:* it does not move — the problem was the trailing rule, not the
polling interval.

### Stop split into warn and grade
CATCOIN was signalled and stopped out inside five minutes at -26% with a peak
of exactly +0%. Warn at -15%, grade at -35% after 20 minutes.

*Right if:* some positions that trip STOP_WARN later close green — early dips
do recover, and grading them immediately was recording good calls as losses.
*Wrong if:* nothing that warns ever recovers. Then the split only delays the
inevitable and makes losses bigger; revert to grading at -15%.

### Per-tier alert floors
One floor at 60 muted boosted entirely: 82 signals, zero sent, because its
gates are loosest so its tokens score lower by construction. Now boosted 38,
second_moon 48, first_moon 52.

*Right if:* boosted starts sending and those alerts perform at least as well
as first_moon's.
*Wrong if:* boosted alerts underperform badly — the score was correctly
identifying them as weak and the low floor is letting noise through.

### Scam heuristics kept, not removed
King asked for removal after a run of rugs. The data said flagged tokens win
25.5% against 20.2%, peak 43 against 30, and every rug that reached him came
from the *unflagged* group.

*Right if:* the gap holds as the sample grows.
*Wrong if:* it closes — the flags are noise and the correlation was
incidental.

---

## MINE — judgement, not evidence

### Channel calls evaluated as candidates
Mentions were only used to top up scores of tokens Surgeon had already found,
so 76 of 78 were discarded. Each mention is now a candidate with its own tier
reaching $50m FDV and a week old, gated on consensus rather than score.

*Right if:* channel calls alert and win at a rate comparable to discovery.
*Wrong if:* they alert often and lose — the channels are noise and this is an
expensive way to import it. Watch specifically whether consensus (2+
channels) beats single mentions.

### Meta detection, 12 point cap
Learns the running meta from tokens performing above 80% in 24h. Early read:
meta-matched tokens won 47.4% against 21.4% on 19 trades.

*Right if:* the gap survives 60+ trades. Then the cap is probably too low.
*Wrong if:* it regresses to the mean. Also watch whether copycat clusters
(`67coin`, `z500`) drag — if word metas underperform theme metas, exclude
clone waves rather than cutting the layer.

### Unproven safety penalty, -12
Every rug that reached King came from tokens with nothing flagged — not clean,
just unexamined. A low RugCheck score on a token with under 300 holders now
costs 12 points.

*Right if:* the rugs that reach him drop, or unproven-flagged tokens
underperform clearly.
*Wrong if:* unproven tokens perform the same as checked ones — the penalty is
punishing youth rather than risk, and 300 holders is an arbitrary line.

### LP zero corroboration
Zero LP no longer rejects when the deployer holds nothing, insiders hold
nothing and there are 500+ holders. Recovered the Cancer Vaccine, which was
rejected while holding 17,900 holders and 0% insider supply.

*Right if:* tokens recovered this way do not rug more than average.
*Wrong if:* any of them rug — the corroboration is too weak and needs a
tighter condition.

### LP lock expiry penalties
-6 inside a day, -12 inside twelve hours, -20 inside two, -25 expired.

*Right if:* tokens with imminent unlocks underperform.
*Wrong if:* no difference — short rolling locks are normal and this is
penalising a convention rather than a risk.

### Dev sold, now functional
Was dead code reading a field that was never written. Now compares the
deployer's holding against what it held at signal time; fires on emptied or
50%+ shed.

*Right if:* it fires at all, and tokens it fires on drop afterwards.
*Wrong if:* it never fires — either deployers on our signals are clean, or
the comparison is still broken.

### Solana discovery depth 6 pages
Two pages is ~40 pools, and Solana produces more than that in fifteen
minutes. A graduation creates a new pool, which is how the Cancer Vaccine
went unseen.

*Right if:* Solana's candidate count roughly triples and new tokens appear
that were not surfacing before.
*Wrong if:* candidates rise but signals do not — the extra pools are junk and
the cost in throttle is wasted.

### Cooling off loosened to 5 losses / 20 min, alerts only
Was 2 losses / 60 min and halted the whole scan. Two losers at a 20% win rate
is an ordinary afternoon.

*Right if:* it rarely triggers.
*Wrong if:* it never triggers at all — then it is dead weight and should go.

### Channel weights levelled to 1.0
I discounted nine channels to 0.35 on a misreading, then removed it. The
mechanism stays for measured hit rates later.

*Right if:* channel accuracy scoring eventually fills it with real numbers.
*Wrong if:* overlap never reaches a level where channels can be measured —
then the whole weighting mechanism is scaffolding for something that will
never be built.

---

## Unresolved, and the honest reason

**Conviction barely predicts outcome.** 30-69 is a flat plateau: 19.2, 19.4,
22.4, 21.4 across 533 trades. Only 70+ separates, at 33.3% on 45 trades.
The score largely measures how much a token resembles a fresh launch, not how
likely it is to run. Every weight in it is either carried from the VPS or
mine. This is the thing most in need of rebuilding from outcomes, and the
thing I have least evidence for.

**The 50-150% band.** first_moon tokens entering up 50-150% won 11.7% across
94 trades — worst cell with a real sample, and a third of all signals. Both
extremes beat it. Needs 250+ before acting.

**Social overlap.** Two tokens have ever appeared in both mentions and
signals. Channel accuracy scoring is blocked until that reaches ~50.
