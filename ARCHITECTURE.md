# AdRx — Architecture

## Problem

Performance marketers spend the first hour of every day pulling reports, spotting anomalies, and deciding what to act on. Most of that work follows patterns — check pacing, look for CPA spikes, scan for new search terms — and most of it could be done by an agent before the marketer opens their laptop. AdRx is an agentic AI morning briefing that reads yesterday's campaign performance data, runs a diagnostic pass, and hands the marketer a prioritized list of what actually needs attention today.

## User

A performance marketer or PPC account manager who opens their laptop in the morning and wants to know "what changed and what should I do?" — not "let me pull data in a sheet and analyze it or have my analyst analyze the dashboards"

## High-Level Design

AdRx is a command-line agent built on the Anthropic API using Claude's tool-use capability. The user runs a single `brief` command with a CSV of campaign performance data. The agent autonomously decides which diagnostic analyses to run, interprets the results, prioritizes findings by ROAS impact and actionability, and returns a structured morning briefing capped at three findings.

## Components

### 1. Input Layer (CLI)
A Click-based Python CLI with one command:
- `brief --input <csv_path> --output <optional_json_path>`

The CSV is Google Ads-style daily performance data with columns: date, campaign, ad_group, keyword, impressions, clicks, cost, conversions, revenue.

### 2. Agent Core
A Python loop that:
1. Loads the CSV into a pandas DataFrame and passes a summary to Claude.
2. Sends the summary plus a system prompt to the Claude API with the five analysis tools attached.
3. On each iteration, if Claude requests a tool, runs it against the DataFrame and returns the result.
4. Continues until Claude returns the final briefing as structured JSON.
5. Hands the JSON to the output layer for rendering.

Same loop pattern as PolicyPilot — the agent chooses which tools to call, not the developer.

### 3. Analysis Tools
Five functions exposed to Claude via the Anthropic tool-use schema. Each does one thing well:

- **`analyze_roas(dimension)`** — Groups performance by keyword, ad group, or campaign and computes cost, revenue, CPA, and ROAS. Returns the top and bottom performers ranked by ROAS.
- **`detect_budget_pacing()`** — Flags campaigns pacing significantly above or below budget with days remaining in the period.
- **`find_anomalies(metric, lookback_days)`** — Compares yesterday's value for each entity to its recent trend and flags meaningful deviations (CPA spikes, ROAS drops, cost outliers).
- **`find_new_search_terms(lookback_days)`** — Surfaces search terms that appeared recently with zero or poor conversions, suggesting negative keyword candidates.
- **`compute_budget_reallocation()`** — Identifies high-ROAS keywords that could absorb more budget and low-ROAS keywords that could fund them.

Each tool takes the DataFrame and returns structured findings. The agent decides the order, interprets the output, and synthesizes the final briefing.

### 4. Output Layer
The agent returns a JSON briefing with a ranked list of findings. The CLI renders this as a color-coded terminal morning briefing using rich, with a small inline plotext bar chart highlighting the top finding. An optional `--output` flag writes the raw JSON to a file for downstream use (Slack integration, dashboards, archive).

## Data Flow

```
CSV of campaign performance
      ↓
Agent core (system prompt + data summary + tools)
      ↓
Claude API ⇄ Tool execution loop (pandas analysis)
      ↓
Structured JSON briefing (top 3 findings)
      ↓
Color-coded terminal morning briefing + optional JSON file
```

## Key Design Decisions

- **Five findings, hard cap.** A briefing with 10 findings is noise; 5 is a useful morning scan. The agent is instructed to prioritize by ROAS impact and actionability, and to balance risks (problems to fix) with opportunities (winners to scale) when both exist in the data. 

- **Rule-based tools, reasoning agent.** The analysis functions compute standard metrics; the agent reasons about which to run, how to interpret them, and which findings are worth surfacing. The alternative — letting the agent write its own pandas code on the fly — would be more flexible but far less reliable for a v1.

- **Structured JSON output.** Forcing a fixed schema makes the briefing scriptable, testable, and pipeable into Slack, dashboards, or other downstream tools.

- **"Yesterday" is the most recent date in the data.** No `--as-of` flag in v1. The recent 7 days form the comparison window. Simple and explicit.

- **Inline terminal visualization.** A single plotext bar chart for the top finding, rendered directly in the terminal. Keeps the demo coherent (stays in the CLI) while adding visual punch that prose alone can't deliver.

## Out of Scope (v1)

- Multi-day trend charts beyond the single terminal visual
- Attribution modeling or multi-touch analysis
- Cross-channel reporting (Meta, LinkedIn, etc.)
- Live Google Ads API integration — CSV only
- Predictive forecasting
- Web dashboard or HTML report mode
- Multi-account support

## Future Extensions

- HTML briefing report with richer charts (natural v2)
- Slack/email delivery of the morning briefing
- Live Google Ads API connector
- Multi-channel data ingestion (combine Google, Meta, LinkedIn into one briefing)
- Historical trend mode (7-day or 30-day performance review)
- Predictive alerts ("at this pacing, you'll overspend by Friday")
