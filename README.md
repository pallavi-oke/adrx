# AdRx

**An agentic morning briefing for performance marketers.**

---

## Demo

![demo](docs/demo.gif)

---

## The Problem

Performance marketers spend the first hour of every day pulling reports from Google Ads, scanning for anomalies, and deciding which campaigns need attention before the day's budget runs. The analysis is real work — but most of it follows repeatable patterns: flag CPA spikes, catch zero-conversion keywords, check pacing against budget. An agent that can run these diagnostics automatically, prioritize the findings by dollar impact, and surface a ready-to-act briefing gives marketers their mornings back and catches problems before they compound.

---

## What AdRx Does

- Reads Google Ads-style CSV performance data (date, campaign, keyword, spend, conversions, revenue)
- Runs a multi-tool diagnostic across ROAS, CPA anomalies, budget pacing, new search terms, and reallocation opportunities
- Produces a prioritized morning briefing capped at 5 findings
- Balances risks (wasted spend, CPA spikes) with opportunities (underbudgeted campaigns with high-ROAS keywords)
- Renders color-coded output with an inline terminal chart for the top finding

---

## How It Works

AdRx uses Claude as an autonomous reasoning layer. On each run, the agent receives a summary of the campaign data and iteratively calls five analysis tools — deciding for itself which tools to call, in what order, and how to interpret conflicting signals — until it has enough evidence to synthesize a briefing. The tool loop is driven by the Anthropic tool-use API: Claude emits a `tool_use` block, the Python runtime dispatches the call, appends the result to the message history, and loops until Claude emits a final JSON response.

```
CSV file
   │
   ▼
Agent Loop (Claude Sonnet via Anthropic tool-use API)
   │
   ├── analyze_roas(dimension="keyword")
   ├── find_anomalies(metric="cpa")
   ├── find_anomalies(metric="roas")
   ├── detect_budget_pacing(budgets={...})
   ├── compute_budget_reallocation()
   └── find_new_search_terms()
   │
   ▼
JSON Briefing (date, summary, findings[])
   │
   ▼
Color-coded terminal output + inline chart
```

The system prompt instructs the agent to call at least three distinct tools before synthesizing, apply volume filters to suppress noisy signals (fewer than 5 baseline conversions are discarded), and return only findings with specific, executable recommendations.

---

## Quickstart

```bash
git clone https://github.com/palllavioke/adrx.git && cd adrx
python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=your_key_here" > .env

python main.py brief --input examples/sample_campaigns.csv
```

---

## Example Output

Output from running `python main.py brief --input examples/sample_campaigns.csv`:

```
AdRx — running analysis…

[tool] analyze_roas(dimension="keyword")
[tool] find_anomalies(metric="cpa", min_deviation_pct=40, min_baseline_conversions=5)
[tool] find_anomalies(metric="roas", min_deviation_pct=40, min_baseline_conversions=5)
[tool] compute_budget_reallocation()
[tool] detect_budget_pacing(budgets={"Home Insurance": 548.4, "Solar Leads Q1": 555.74})
[tool] find_new_search_terms(lookback_days=10, min_impressions=100)

╭──────────────────── AdRx Morning Briefing  ·  2026-04-13 ────────────────────╮
│ Three Home Insurance keywords burned $948 at 0 ROAS in the past 7 days while │
│ Solar Leads Q1 under-delivered by 26%; immediate pause and negative keyword  │
│ actions required.                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯

╭───── #1  [HIGH]  Three Home Insurance keywords wasting $948/week at zero ROAS ─────╮
│                                                                                    │
│  Keywords 'best home insurance' ($327), 'home insurance' ($315), and 'house        │
│  insurance policy' ($306) generated zero conversions over the past 7 days          │
│  despite combined spend of $948. All three are broad, non-intent terms             │
│  attracting low-quality traffic.                                                   │
│                                                                                    │
│  Action:      Pause all three keywords immediately and add as phrase-match         │
│               negative keywords across the Home Insurance campaign.                │
│  Impact:      $948/week in wasted spend recovered                                  │
│  Confidence:  high                                                                 │
│                                                                                    │
╰────────────────────────────────────────────────────────────────────────────────────╯

╭──── #2  [HIGH]  Home insurance quotes CPA spiked 124% from $85 to $190 ────╮
│                                                                             │
│  'home insurance quotes' drove 9 conversions but CPA jumped from baseline   │
│  $84.85 to $189.85 in the past 7 days, costing $1,709 at 0.59 ROAS (down   │
│  58% from 1.41 baseline). This is the highest-spend underperformer.        │
│                                                                             │
│  Action:      Lower max CPC bid by 30% immediately and enable enhanced CPC │
│               bid strategy to regain efficiency.                            │
│  Impact:      $510/week in excess CPA cost; potential recovery to ~1.4 ROAS│
│  Confidence:  high                                                          │
│                                                                             │
╰─────────────────────────────────────────────────────────────────────────────╯

╭──── #3  [HIGH]  Four new search terms wasting $122 with zero conversions ────╮
│                                                                              │
│  New terms 'cheap auto policy free', 'solar panels scam', 'solar panels     │
│  stock tips', and 'free government solar program scam' appeared in the past  │
│  10 days with 2,429 impressions and $122 spend and zero conversions. All     │
│  are irrelevant broad-match waste.                                           │
│                                                                              │
│  Action:      Add all four as exact-match negative keywords across both      │
│               campaigns to prevent further budget leak.                      │
│  Impact:      $122/week in wasted spend avoided                              │
│  Confidence:  high                                                           │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

╭──── #4  [MEDIUM]  Solar Leads Q1 under-pacing by 26% ($142/day underspent) ────╮
│                                                                                 │
│  Solar Leads Q1 averaged $414/day vs. $556/day budget over the past 7 days,    │
│  leaving $142/day unrealized while top solar keywords (ROAS 3.4–6.8) have      │
│  room to scale.                                                                 │
│                                                                                 │
│  Action:      Increase daily budget by $150 and raise bids 15% on 'solar       │
│               installation near me' (6.78 ROAS) and 'solar company near me'    │
│               (3.89 ROAS).                                                      │
│  Impact:      ~$500/week incremental revenue at 4+ ROAS if scaled              │
│  Confidence:  medium                                                            │
│                                                                                 │
╰─────────────────────────────────────────────────────────────────────────────────╯

                             ROAS — Finding #1
    ┌──────────────────────────────────────────────────────┐
1.65┤                                         ████████████ │
    │                                         ████████████ │
1.10┤                                         ████████████ │
    │                                         ████████████ │
0.55┤                                         ████████████ │
    │                                         ████████████ │
0.00┤ ░░░░░░░░░░░░░░░░                        ████████████ │
    └───────────────────┬──────────────────────────┬───────┘
         house insurance policy               Acct avg
ROAS (revenue / cost)
```

---

## What I Learned

**Agents have a bias toward what the prompt asks them to find.** My first version of AdRx only returned risks — CPA spikes, pacing issues, wasted spend — and completely missed the scale-up opportunities sitting in the same data. Turned out the system prompt was framed entirely around "problems to fix," so the agent never considered "winners to scale." Adding one sentence — "balance risks with opportunities when both exist in the data" — changed the briefing from a list of bad news into something that actually felt useful in the morning.

**3 findings was too few. 5 was right.** I started with a hard cap of 3 findings, reasoning that discipline beats comprehensiveness. But running the agent on real data revealed a tradeoff I hadn't anticipated: three slots filled up with risks and pushed out the opportunities, which made the briefing feel one-sided. Bumping the cap to 5 gave the agent room to balance, and the output landed better. The lesson: prompt constraints that look clean in the abstract have to survive contact with actual outputs.

**Domain terminology was the fastest credibility lever.** Early briefings said things like "this keyword's cost-to-revenue ratio is low" — technically accurate, but not how a PPC manager talks. One pass through the system prompt swapping in ROAS, CPA, ad group, negative keyword, and bid instantly made the output feel like it was written by someone in the space. Speaking the user's language isn't polish — it's product.

**Rule-based tools plus a reasoning agent beat "let the agent write its own analysis."** I considered an architecture where the agent writes pandas code on the fly to analyze the data. It sounded more impressive, but it would have been far less reliable. Keeping the analysis functions deterministic and letting the agent decide which to call and how to interpret the results made the whole system easier to debug, test, and trust. Reliability of individual components compounds into reliability of the whole agent.

---

## Future Work

- **Predictive alerts** — budget burn forecasts and anomaly early warnings before end-of-day overspend
- **HTML briefing report** — styled exportable report alongside terminal output
- **Slack delivery** — post the morning briefing to a channel on a schedule
- **Google Ads API integration** — pull live data directly instead of requiring a CSV export
- **Multi-channel ingestion** — extend to Meta Ads, Microsoft Ads, and DV360 data formats

---

## Tech Stack

Python, Anthropic Claude Sonnet, pandas, Click, Rich, plotext
