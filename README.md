# AdRx — Agentic Morning Briefing for Performance Marketers

An AI agent that reads your campaign performance data and delivers a personalized HTML dashboard with prioritized findings, specific recommendations, interactive charts, and supporting data tables — before you've had your coffee.

## Demo

![AdRx Briefing](docs/briefing_screenshot.png)

*A 75-second walkthrough narrated by an AI avatar with my cloned voice is available at [`docs/adrx_final.mp4`](docs/adrx_final.mp4).*

## The Problem

Performance marketers spend the first hour of every day pulling reports, spotting anomalies, and deciding what's worth their attention. Most of that work follows patterns — check pacing, look for CPA spikes, scan for irrelevant search terms, find scaling opportunities.

Dashboards are great at showing this data. But they can't synthesize it — they can't tell you which 5 things out of 200 data points actually need your attention today, and they can't turn "CPA spiked 124%" into "lower bid 30% and monitor for 3 days."

AdRx automates the synthesis layer: the analyst work that happens *after* looking at a dashboard, where someone turns raw numbers into a prioritized morning briefing with specific, actionable recommendations.

## What AdRx Does

- Reads Google Ads-style CSV performance data (daily keyword-level metrics)
- Runs a multi-tool diagnostic across ROAS, budget pacing, CPA anomalies, search term quality, and reallocation opportunities
- Delivers a personalized HTML dashboard ("Good morning, Sarah Chen") that auto-opens in the browser
- Produces up to 5 prioritized findings, balancing risks (problems to fix) with opportunities (winners to scale)
- Each finding includes a specific, actionable recommendation with estimated ROAS impact and a supporting data table for at-a-glance scannability
- Renders interactive Plotly charts: Account Health (spend vs. revenue with ROAS overlay) and CPA Trend (7-day line)
- Computes account summary metrics deterministically in Python — consistent numbers on identical input, every run
- Account summary includes: Overall ROAS, Total Spend (7d), Wasted Spend (recoverable if acted on), and Projected ROAS (if findings are addressed)

## How It Works

AdRx is built on the Anthropic API using Claude's tool-use capability. The agent autonomously decides which analyses to run, interprets results, prioritizes findings by ROAS impact and actionability, and synthesizes a structured briefing. Account-level metrics and chart data are computed deterministically in Python — not by the LLM — ensuring consistency across runs.

```
CSV of campaign performance
      ↓
Deterministic pre-computation (account summary + chart data via Python/pandas)
      ↓
Agent core (system prompt + data summary + 5 analysis tools)
      ↓
Claude API ⇄ Tool execution loop (pandas analysis)
      ↓
Structured JSON briefing (up to 5 findings with supporting data)
      ↓
HTML dashboard with Jinja2 template + Plotly charts → auto-opens in browser
```

**The analysis tools:**

- `analyze_roas(dimension)` — ROAS, CPA, cost, revenue grouped by keyword, ad group, or campaign. Returns top and bottom performers ranked by ROAS.
- `detect_budget_pacing()` — flags campaigns pacing significantly above or below budget with days remaining in the period.
- `find_anomalies(metric, lookback_days)` — compares recent values to baseline trend; surfaces CPA spikes, ROAS drops, cost outliers.
- `find_new_search_terms(lookback_days)` — finds recent zero-conversion search terms suggesting negative keyword candidates.
- `compute_budget_reallocation()` — identifies high-ROAS keywords to scale up and low-ROAS keywords to pause or reduce.

**Deterministic functions (computed in Python, not by the agent):**

- `compute_account_summary(df, findings)` — calculates Overall ROAS, Total Spend, Wasted Spend, and Projected ROAS from raw data and agent findings.
- `get_account_trends(df, days)` — returns daily spend, revenue, ROAS, CPA, and budget arrays for chart rendering.

The agent chooses which analysis tools to call and in what order. The developer defines capabilities; the agent decides how to use them. Math stays deterministic; reasoning stays agentic.

## The HTML Dashboard

The briefing renders as a clean, professional HTML page using Jinja2 and Plotly:

**Header:** Personalized greeting ("Good morning, Sarah Chen") with the briefing date.

**Account Summary:** 4 metric cards — Overall ROAS, Total Spend (7d), Wasted Spend (with subtitle "recoverable if acted on"), and Projected ROAS (with subtitle "if findings are addressed"). Wasted Spend has a red accent border; Projected ROAS has a green accent border.

**Interactive Charts:** 2 Plotly charts side-by-side — Account Health (daily spend and revenue bars with ROAS trend line on secondary axis) and CPA Trend (daily CPA line over 7 days). Both support hover for exact values with a legend identifying each series.

**Findings Section:** Up to 5 findings, each in a severity-coded card (red/amber/blue left border). Each finding includes: priority badge, severity badge, title, data-backed detail paragraph, a supporting data table with the specific metrics backing the recommendation, and an action row with the recommendation, estimated impact, and confidence level.

**Footer:** Generated by AdRx with link to the GitHub repo.

## Quickstart

```bash
git clone https://github.com/pallavi-oke/adrx.git
cd adrx
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your Anthropic API key
python main.py brief --input examples/sample_campaigns.csv
```

The briefing opens automatically in your default browser.

Optional flags:
- `--user "Your Name"` — personalizes the greeting (default: "Sarah Chen")
- `--output results.json` — also saves raw JSON briefing to file

## Example Findings

Running AdRx on the included sample data produces findings such as:

- `#1 HIGH` — 3 Home Insurance keywords burning $948/week at 0 ROAS → Action: pause all 3 immediately; review match type strategy
- `#2 HIGH` — "home insurance quotes" CPA spiked 124% to $190 (was $85) → Action: lower bid 30%, monitor 3 days; if CPA stays above $120, pause
- `#3 HIGH` — 4 new search terms wasting budget on irrelevant traffic ($122 total, 0 conversions) → Action: add all 4 as exact-match negative keywords across both campaigns
- `#4 MEDIUM` — Solar Leads Q1 pacing 23% under budget with 4 days left → Action: raise daily cap to capture remaining demand
- `#5 LOW` — "solar installation near me" ROAS at 3.2x vs 1.8x account average → Action: increase bid to scale; room for additional budget allocation

Each finding is backed by a supporting data table with the specific metrics — keyword-level costs, impressions, conversions, ROAS comparisons — so the marketer can verify the recommendation at a glance.

## What I Learned

**The hardest question building AdRx was "why is this an agent, not a dashboard?"** The honest answer: for tracking and exploration, a Looker dashboard wins every time — cheaper, faster, more consistent. But dashboards show data; they don't synthesize it. They can't weigh ROAS impact against volume against actionability to tell you which 5 things matter today, and they can't turn "CPA spiked 124%" into "lower bid 30% and monitor for 3 days." That's analyst work — the work someone does reading the dashboard every morning and writing the team a summary of what actually needs attention. AdRx automates that synthesis layer, not the data layer beneath it. Being clear about where an agent belongs in the workflow turned out to be more important than the technical build.

**Agents have a bias toward what the prompt asks them to find.** My first version of AdRx only returned risks — CPA spikes, pacing issues, wasted spend — and completely missed the scale-up opportunities sitting in the same data. The system prompt was framed entirely around "problems to fix," so the agent never considered "winners to scale." Adding 1 sentence — "balance risks with opportunities when both exist in the data" — changed the briefing from a list of bad news into something that actually felt useful in the morning.

**3 findings was too few. 5 was right.** I started with a hard cap of 3 findings, reasoning that discipline beats comprehensiveness. But running the agent on real data revealed a tradeoff I hadn't anticipated: 3 slots filled up with risks and pushed out the opportunities, which made the briefing feel one-sided. Bumping the cap to 5 gave the agent room to balance, and the output landed better. Prompt constraints that look clean in the abstract have to survive contact with actual outputs.

**Domain terminology was the fastest credibility lever.** Early briefings said things like "this keyword's cost-to-revenue ratio is low" — technically accurate, but not how a PPC manager talks. 1 pass through the system prompt swapping in ROAS, CPA, ad group, negative keyword, and bid instantly made the output feel like it was written by someone in the space. Speaking the user's language isn't polish — it's product.

**Rule-based tools plus a reasoning agent beat "let the agent write its own analysis."** I considered an architecture where the agent writes pandas code on the fly. It sounded more impressive, but it would have been far less reliable. Keeping the analysis functions deterministic and letting the agent decide which to call and how to interpret the results made the whole system easier to debug, test, and trust.

**Math should never be non-deterministic.** My first version let the agent compute everything — findings, recommendations, and top-line aggregate numbers. Running the same input twice produced different "wasted spend" totals, which would erode user trust fast. The fix was architectural: let Python handle deterministic math (sums, ratios, aggregates) and let the agent handle synthesis (prioritization, explanation, recommendation). Separating the math layer from the reasoning layer was 1 of the most important decisions in the whole project.

**1 ambiguous metric label can undermine a whole dashboard.** An early version had a metric called "Overall Loss" — but the account was profitable (ROAS > 1). A reviewer asked how those numbers coexist. The metric actually meant "recoverable waste," not "net loss." Renamed it to "Wasted Spend (recoverable if acted on)." In data products, 1 misleading label makes users distrust every other number on the page, even when the math is right.

**Presentation is product.** The first version of AdRx was a terminal-only tool with an ugly plotext chart. Technically it worked, but it didn't look like something a marketer would want to open every morning. Rebuilding the output as an HTML dashboard with Jinja2 templating, Plotly interactive charts, and severity-coded finding cards transformed AdRx from a script into a product. The underlying agent didn't change — just the presentation. That was enough to make the difference between "interesting project" and "I'd actually use this."

## Future Work

- Predictive alerts: budget burn forecasts, CPA drift early warnings, saturation detection
- Slack/email delivery of the morning briefing
- Live Google Ads API connector (replace CSV with real-time data)
- Multi-channel ingestion (combine Google, Meta, LinkedIn into 1 briefing)
- Historical trend mode (7-day or 30-day performance review)
- Multi-account support with account-level comparison
- Performance optimization for sub-10-second end-to-end generation

## Tech Stack

Python · Anthropic Claude Sonnet · pandas · Jinja2 · Plotly · Click · python-dotenv

## About

AdRx is part of a portfolio of agentic AI prototypes built by [Pallavi Oke](https://github.com/pallavi-oke) — exploring how autonomous agents can own end-to-end product workflows in ad tech, insurance, and home services.

Also see: [PolicyPilot](https://github.com/pallavi-oke/policypilot) (ad compliance agent).
