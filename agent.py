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

from tools import load_data, get_date_windows, TOOL_SCHEMAS, TOOL_FUNCTIONS


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are AdRx, a morning briefing agent for performance marketers. \
Given a CSV of campaign performance data, your job is to diagnose what changed and \
produce a prioritized briefing of the top things the marketer needs to act on today.

WORKFLOW
You must call multiple analysis tools to build a complete picture before synthesizing \
findings. The minimum is three distinct tool calls covering different dimensions of the \
account. Do not produce a briefing from a single tool's output.

Recommended sequence (adapt based on what you find):
1. analyze_roas(dimension="keyword") — identify high and low ROAS performers
2. find_anomalies(metric="cpa") — catch keywords where CPA spiked
3. find_anomalies(metric="roas") — catch keywords where ROAS dropped
4. compute_budget_reallocation() — surface scale-up and pause candidates
5. detect_budget_pacing(budgets=<avg daily spend from the data summary>) — check delivery
6. find_new_search_terms() — surface new zero-conversion terms wasting budget

FINDINGS PRIORITIZATION
Rank by: (1) ROAS impact — dollars recoverable or cost avoidable — combined with \
(2) actionability. A finding with a specific, executable recommended action outranks a \
vague observation. Estimate dollar impact wherever the data supports it.

HARD CAP: Return at most 5 findings. If fewer than 5 issues genuinely warrant action, \
return fewer. Never pad with low-confidence or low-impact observations. Ensure at least one \
finding should be an opportunity (scale-up recommendation) if the data supports it. \
Do not produce a briefing that contains only risks unless no clear opportunities exist in the data.

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

BUDGET PACING
When calling detect_budget_pacing, use the average daily spend per campaign from the \
data summary as the daily budget estimate. A campaign running 40% above its own \
historical average is a meaningful signal.

TONE
Trusted analyst briefing an account manager at 8am. Professional, confident, concise. \
Never hedge — no "you may want to consider" or "it might be worth reviewing". \
State findings directly. If the data does not support a finding with high confidence, \
do not include it.

TERMINOLOGY
Use domain-native terms: ROAS, CPA, ad group, search term, negative keyword, bid, \
pacing, CPL, impression share. Avoid generic marketing language.

OUTPUT FORMAT
After completing your tool calls, return a single JSON object. Your response must \
contain ONLY the JSON — no prose before it, no explanation after it, no markdown \
code fences around it. Begin your response with `{` and end with `}`.

The JSON must exactly match this schema:
{
  "briefing_date": "YYYY-MM-DD",
  "summary": "one-sentence overall account status",
  "findings": [
    {
      "priority": 1,
      "severity": "high|medium|low",
      "title": "short headline under 80 chars",
      "detail": "data-backed explanation in 1-2 sentences",
      "recommendation": "specific executable action",
      "estimated_impact": "e.g. '$340/week in wasted spend' or '~3x ROAS if scaled'",
      "confidence": "high|medium|low"
    }
  ]
}

findings: 1–3 entries ordered by priority (1 = highest). Return fewer than 3 if fewer \
than 3 issues genuinely warrant action."""


# ── Agent loop ────────────────────────────────────────────────────────────────

def generate_briefing(csv_path: str) -> dict:
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
                f"Campaign data summary:\n\n{data_summary}\n\n"
                f"Briefing date: {w['yesterday'].date()}. "
                "Use the available tools to analyse the data, then return the "
                "briefing as a single JSON object with no surrounding text."
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
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass

            # Try 2: JSON inside ``` ... ``` or ```json ... ```
            fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if fence:
                try:
                    return json.loads(fence.group(1))
                except json.JSONDecodeError:
                    pass

            # Try 3: outermost { ... } anywhere in the text (handles prose preamble)
            brace = re.search(r"\{.*\}", raw, re.DOTALL)
            if brace:
                try:
                    return json.loads(brace.group(0))
                except json.JSONDecodeError:
                    pass

            print("\n[ERROR] Raw agent response:\n")
            print(raw)
            raise ValueError(
                "Agent response could not be parsed as JSON. "
                "Raw response printed above."
            )

        else:
            raise ValueError(
                f"Unexpected stop_reason={response.stop_reason!r} "
                f"on iteration {iteration + 1}."
            )

    raise ValueError(
        f"Agent loop reached {MAX_ITERATIONS} iterations without a final response."
    )
