"""
agent.py — AdRx agent loop.

Drives a tool-calling loop with claude-sonnet-4-5 to produce a JSON
morning briefing from a campaign performance CSV.
"""

import json
import os
import re

import anthropic
from dotenv import load_dotenv

from tools import (
    load_data,
    get_date_windows,
    get_account_trends,
    compute_account_summary,
    TOOL_SCHEMAS,
    TOOL_FUNCTIONS,
)


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are AdRx, a morning briefing agent for performance marketers. \
Given a CSV of campaign performance data, your job is to diagnose what changed and \
produce a prioritized briefing of the top things the marketer needs to act on today.

WORKFLOW
You must call multiple analysis tools to build a complete picture before synthesizing \
findings. The minimum is four distinct tool calls. Do not produce a briefing from a \
single tool's output.

Required sequence (adapt based on what you find):
1. get_account_trends() — REQUIRED FIRST. Establishes the 7-day performance baseline \
   needed to contextualize all findings.
2. analyze_roas(dimension="keyword") — identify high and low ROAS performers
3. find_anomalies(metric="cpa") — catch keywords where CPA spiked
4. find_anomalies(metric="roas") — catch keywords where ROAS dropped
5. compute_budget_reallocation() — surface scale-up and pause candidates
6. detect_budget_pacing(budgets={"Solar Leads Q1": 500, "Home Insurance": 400}) — check delivery
7. find_new_search_terms() — surface new zero-conversion terms wasting budget

ACCOUNT SUMMARY AND ACCOUNT TRENDS
These fields are computed deterministically by the system after your response is received \
and will override any values you produce. Output placeholder values (0 for numbers, empty \
arrays for lists) for account_summary and account_trends. Focus entirely on producing \
high-quality, well-supported findings.

FINDINGS PRIORITIZATION
Rank by: (1) ROAS impact — dollars recoverable or cost avoidable — combined with \
(2) actionability. A finding with a specific, executable recommended action outranks a \
vague observation. Estimate dollar impact wherever the data supports it.

HARD CAP: Return at most 5 findings. If fewer than 5 issues genuinely warrant action, \
return fewer. Ensure at least 1 finding is an opportunity (scale-up) if the data supports it. \
Do not produce a briefing that contains only risks unless no clear opportunities exist.

CONFIDENCE AND VOLUME RULES
When interpreting find_anomalies results, discard any keyword that fails these checks:
- Fewer than 5 baseline conversions → signal too noisy, skip
- Fewer than 3 recent conversions → skip
- Recent spend under $50 → deprioritize regardless of pct_change magnitude
Only surface findings where the data volume is large enough to trust the signal.

RECOMMENDATIONS
Each finding must include a specific, immediately executable recommendation — not \
"review this keyword" but "lower bid 20%", "add as negative keyword across all ad groups", \
"increase daily budget by $150", "pause keyword until CPA returns to baseline". \
The recommendation must be actionable without further research.

TONE
Trusted analyst briefing an account manager at 8am. Professional, confident, concise. \
Never hedge — no "you may want to consider" or "it might be worth reviewing". \
State findings directly. If the data does not support a finding with high confidence, \
do not include it.

TERMINOLOGY
Use domain-native terms: ROAS, CPA, ad group, search term, negative keyword, bid, \
pacing, CPL, impression share. Avoid generic marketing language.

NUMERALS
Always use numerals for quantities in titles, summaries, details, and recommendations. \
Write "3 keywords" not "three keywords", "7 days" not "seven days".

SUPPORTING DATA FORMAT
Each finding must include a supporting_data object with exactly two keys:
- "headers": array of column name strings (3–5 columns)
- "rows": array of arrays; each inner array is one data row matching the headers

Two well-formed examples:

Example 1 — CPA spike:
{
  "headers": ["Metric", "Recent (7d)", "Baseline (30d)", "Change"],
  "rows": [
    ["CPA", "$190", "$85", "+124%"],
    ["ROAS", "0.59", "1.40", "-58%"],
    ["Conversions", "4", "18", "-78%"],
    ["Cost", "$760", "$1,530", "-50%"]
  ]
}

Example 2 — Zero-conversion waste:
{
  "headers": ["Keyword", "Cost", "Impressions", "Conversions"],
  "rows": [
    ["best home insurance", "$327", "2,145", "0"],
    ["cheap home insurance", "$198", "1,890", "0"],
    ["house insurance policy", "$145", "1,203", "0"]
  ]
}

Use this tabular format for every finding type. Column names and data must be meaningful \
for the finding type. Always use formatted strings with units (e.g. "$190", "124%", "4 convs"). \
Populate supporting_data with the actual values pulled from tool outputs — do not invent numbers.

Finding-type guidance:
- Zero-conversion waste: headers=["Keyword", "Cost", "Impressions", "Conversions"]
- CPA spike: headers=["Metric", "Recent (7d)", "Baseline (30d)", "Change"] — rows for CPA, ROAS, Conversions, Cost
- Negative keyword / new search terms: headers=["Search Term", "Impressions", "Cost", "Conversions"]
- ROAS opportunity: headers=["Metric", "This Keyword", "Account Avg"] — rows for ROAS, Conversions, Cost
- Budget pacing: headers=["Campaign", "Daily Budget", "Actual Spend", "Variance"]

OUTPUT FORMAT
After completing your tool calls, return a single JSON object. Your response must \
contain ONLY the JSON — no prose before it, no explanation after it, no markdown \
code fences around it. Begin your response with `{` and end with `}`.

The JSON must exactly match this schema:
{
  "user_name": "<echo back the user name from the briefing request>",
  "briefing_date": "YYYY-MM-DD",
  "account_summary": {},
  "account_trends": {},
  "findings": [
    {
      "priority": 1,
      "severity": "high|medium|low",
      "title": "short headline under 80 chars",
      "detail": "data-backed explanation in 1-2 sentences",
      "recommendation": "specific executable action",
      "estimated_impact": "e.g. '$340/week in wasted spend' or '~3x ROAS if scaled'",
      "confidence": "high|medium|low",
      "supporting_data": {
        "headers": ["Col1", "Col2", ...],
        "rows": [["val1", "val2", ...], ...]
      }
    }
  ]
}

account_summary and account_trends will be populated by the system — output empty \
objects for both. findings: 1–5 entries ordered by priority (1 = highest)."""


# ── Agent loop ────────────────────────────────────────────────────────────────

def generate_briefing(csv_path: str, user_name: str = "Sarah Chen") -> dict:
    """
    Load the CSV, run the tool-calling agent loop, and return the parsed
    briefing dict.

    Parameters
    ----------
    csv_path : str
        Path to the campaign performance CSV.

    Returns
    -------
    dict
        Parsed briefing JSON matching the schema in SYSTEM_PROMPT.
    """
    load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set — add it to .env")

    # ── Load data and build summary ───────────────────────────────────────────
    df = load_data(csv_path)
    w = get_date_windows(df)

    total_spend = df["cost"].sum()
    campaigns = df["campaign"].unique().tolist()
    num_keywords = df["keyword"].nunique()
    date_range = f"{df['date'].min().date()} to {df['date'].max().date()}"

    # Avg daily spend per campaign — agent uses these as budget proxies for
    # detect_budget_pacing
    daily_by_campaign = (
        df.groupby(["date", "campaign"])["cost"]
        .sum()
        .reset_index()
        .groupby("campaign")["cost"]
        .mean()
        .round(2)
        .to_dict()
    )

    data_summary = (
        f"Date range: {date_range}\n"
        f"Analysis date (yesterday): {w['yesterday'].date()}\n"
        f"Total spend (all time in CSV): ${total_spend:,.2f}\n"
        f"Campaigns ({len(campaigns)}): {', '.join(campaigns)}\n"
        f"Unique keywords: {num_keywords}\n"
        f"Average daily spend by campaign (use as budget estimates): "
        f"{json.dumps(daily_by_campaign)}"
    )

    # ── Initialise client ─────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": (
                f"Briefing for: {user_name}\n\n"
                f"Campaign data summary:\n\n{data_summary}\n\n"
                f"Briefing date: {w['yesterday'].date()}. "
                "Use the available tools to analyse the data, then return the "
                "briefing as a single JSON object with no surrounding text. "
                f"Echo back user_name as \"{user_name}\" in the JSON."
            ),
        }
    ]

    # ── Agent loop ────────────────────────────────────────────────────────────
    MAX_ITERATIONS = 15

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Must append full content objects so tool_use blocks are preserved
        messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if tool_use_blocks:
            # ── Dispatch every tool call in this turn ─────────────────────────
            tool_results = []
            for block in tool_use_blocks:
                args_str = ", ".join(
                    f"{k}={json.dumps(v)}" for k, v in block.input.items()
                )
                print(f"[tool] {block.name}({args_str})")

                try:
                    result = TOOL_FUNCTIONS[block.name](df, **block.input)
                    content = json.dumps(result, default=str)
                except Exception as exc:
                    content = json.dumps({"error": str(exc)})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                })

            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            # ── Extract JSON from the final text response ─────────────────────
            text_blocks = [b for b in response.content if b.type == "text"]
            if not text_blocks:
                raise ValueError(
                    "Agent returned end_turn with no text content."
                )

            raw = text_blocks[0].text.strip()

            # Try 1: clean JSON (ideal path)
            briefing = None
            try:
                briefing = json.loads(raw)
            except json.JSONDecodeError:
                pass

            # Try 2: JSON inside ``` ... ``` or ```json ... ```
            if briefing is None:
                fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
                if fence:
                    try:
                        briefing = json.loads(fence.group(1))
                    except json.JSONDecodeError:
                        pass

            # Try 3: outermost { ... } anywhere in the text (handles prose preamble)
            if briefing is None:
                brace = re.search(r"\{.*\}", raw, re.DOTALL)
                if brace:
                    try:
                        briefing = json.loads(brace.group(0))
                    except json.JSONDecodeError:
                        pass

            if briefing is None:
                print("\n[ERROR] Raw agent response:\n")
                print(raw)
                raise ValueError(
                    "Agent response could not be parsed as JSON. "
                    "Raw response printed above."
                )

            # Override account_summary and account_trends with deterministic Python
            # values — the agent's reasoning produces inconsistent numbers on identical
            # data; these functions always produce the same result for the same input.
            briefing["account_summary"] = compute_account_summary(
                df, briefing.get("findings", [])
            )
            briefing["account_trends"] = get_account_trends(df)
            return briefing

        else:
            raise ValueError(
                f"Unexpected stop_reason={response.stop_reason!r} "
                f"on iteration {iteration + 1}."
            )

    raise ValueError(
        f"Agent loop reached {MAX_ITERATIONS} iterations without a final response."
    )
