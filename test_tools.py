"""
test_tools.py — Sanity-check that all five analysis tools run correctly and
that each planted signal in examples/sample_campaigns.csv is surfaced.

Expected detections
-------------------
  Signal A  find_anomalies(metric='cpa')       → "home insurance quotes" CPA spike ~2x
  Signal B  detect_budget_pacing()             → "Solar Leads Q1" ~22% under $500 budget
  Signal C  find_new_search_terms()            → 4 irrelevant zero-conversion terms
  Signal D  analyze_roas(dimension='keyword')  → "solar installation near me" top by ROAS

Run:  python test_tools.py
"""

import json
import sys
from pathlib import Path

from rich import print as rprint
from rich.rule import Rule
from rich.console import Console

from tools import (
    load_data,
    get_date_windows,
    analyze_roas,
    detect_budget_pacing,
    find_anomalies,
    find_new_search_terms,
    compute_budget_reallocation,
)

CSV_PATH = Path(__file__).parent / "examples" / "sample_campaigns.csv"
BUDGETS  = {"Solar Leads Q1": 500, "Home Insurance": 400}

console = Console()


def section(title: str) -> None:
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]"))


def dump(result: dict) -> None:
    console.print_json(json.dumps(result, default=str))


def check(label: str, condition: bool, detail: str = "") -> None:
    icon   = "[green]✓[/green]" if condition else "[red]✗[/red]"
    status = "[green]PASS[/green]" if condition else "[red]FAIL[/red]"
    msg    = f"  {icon} {status}  {label}"
    if detail:
        msg += f"  [dim]({detail})[/dim]"
    console.print(msg)


# ── Load ───────────────────────────────────────────────────────────────────────

section("Loading data")
df = load_data(str(CSV_PATH))
rprint(f"  Rows: [bold]{len(df):,}[/bold]  |  "
       f"Date range: [bold]{df['date'].min().date()}[/bold] → [bold]{df['date'].max().date()}[/bold]  |  "
       f"Campaigns: [bold]{df['campaign'].nunique()}[/bold]  |  "
       f"Keywords: [bold]{df['keyword'].nunique()}[/bold]")

w = get_date_windows(df)
rprint(f"\n  Date windows:")
rprint(f"    yesterday      = [bold]{w['yesterday'].date()}[/bold]")
rprint(f"    recent_start   = [bold]{w['recent_start'].date()}[/bold]")
rprint(f"    baseline_end   = [bold]{w['baseline_end'].date()}[/bold]")
rprint(f"    baseline_start = [bold]{w['baseline_start'].date()}[/bold]")


# ── analyze_roas ──────────────────────────────────────────────────────────────

section("Tool 1 · analyze_roas(dimension='keyword')")
roas_result = analyze_roas(df, "keyword")
dump(roas_result)

top_keywords = [r["keyword"] for r in roas_result["top_performers"]]
solar_near_me_roas = next(
    (r["roas"] for r in roas_result["top_performers"] if r["keyword"] == "solar installation near me"),
    None,
)
rprint("\n  [bold]Signal D check:[/bold]")
check(
    "'solar installation near me' is in top-5 ROAS keywords",
    "solar installation near me" in top_keywords,
    f"top keywords: {top_keywords}",
)
check(
    "'solar installation near me' ROAS > 4.0",
    solar_near_me_roas is not None and solar_near_me_roas > 4.0,
    f"ROAS = {solar_near_me_roas}",
)

section("Tool 1 · analyze_roas(dimension='campaign')")
roas_camp = analyze_roas(df, "campaign")
dump(roas_camp)


# ── detect_budget_pacing ──────────────────────────────────────────────────────

section("Tool 2 · detect_budget_pacing()")
pacing_result = detect_budget_pacing(df, BUDGETS)
dump(pacing_result)

flagged_camps  = [f["campaign"] for f in pacing_result["flagged_campaigns"]]
solar_flag     = next((f for f in pacing_result["flagged_campaigns"] if f["campaign"] == "Solar Leads Q1"), None)
rprint("\n  [bold]Signal B check:[/bold]")
check(
    "'Solar Leads Q1' is flagged for under-pacing",
    "Solar Leads Q1" in flagged_camps,
    f"flagged: {flagged_camps}",
)
if solar_flag:
    check(
        "Solar Leads Q1 pacing status is 'under'",
        solar_flag["status"] == "under",
        f"status = {solar_flag['status']}",
    )
    check(
        "Solar Leads Q1 pct_variance more negative than -15%",
        solar_flag["pct_variance"] < -15,
        f"pct_variance = {solar_flag['pct_variance']}%",
    )


# ── find_anomalies ────────────────────────────────────────────────────────────

section("Tool 3 · find_anomalies(metric='cpa')")
anomaly_result = find_anomalies(df, metric="cpa", min_deviation_pct=40)
dump(anomaly_result)

flagged_kws = [f["keyword"] for f in anomaly_result["flagged_keywords"]]
hiq_anomaly = next((f for f in anomaly_result["flagged_keywords"] if f["keyword"] == "home insurance quotes"), None)
rprint("\n  [bold]Signal A check:[/bold]")
check(
    "'home insurance quotes' is flagged for CPA anomaly",
    "home insurance quotes" in flagged_kws,
    f"flagged keywords: {flagged_kws}",
)
if hiq_anomaly:
    check(
        "CPA direction is 'spike'",
        hiq_anomaly["direction"] == "spike",
        f"direction = {hiq_anomaly['direction']}",
    )
    check(
        "CPA spike is at least 50% above baseline",
        hiq_anomaly["pct_change"] >= 50,
        f"pct_change = {hiq_anomaly['pct_change']}%",
    )

section("Tool 3 · find_anomalies(metric='roas')")
roas_anomaly = find_anomalies(df, metric="roas", min_deviation_pct=40)
dump(roas_anomaly)


# ── find_new_search_terms ─────────────────────────────────────────────────────

section("Tool 4 · find_new_search_terms(lookback_days=10, min_impressions=100)")
new_terms_result = find_new_search_terms(df, lookback_days=10, min_impressions=100)
dump(new_terms_result)

found_terms = [t["keyword"] for t in new_terms_result["new_zero_conversion_terms"]]
expected_junk = {
    "cheap auto policy free",
    "solar panels scam",
    "free government solar program scam",
    "solar panels stock tips",
}
rprint("\n  [bold]Signal C check:[/bold]")
check(
    "At least 3 junk terms detected",
    len(found_terms) >= 3,
    f"found {len(found_terms)}: {found_terms}",
)
for junk_kw in expected_junk:
    check(
        f"'{junk_kw}' detected",
        junk_kw in found_terms,
    )


# ── compute_budget_reallocation ───────────────────────────────────────────────

section("Tool 5 · compute_budget_reallocation()")
realloc_result = compute_budget_reallocation(df)
dump(realloc_result)

scale_kws = [r["keyword"] for r in realloc_result["scale_up_candidates"]]
pause_kws  = [r["keyword"] for r in realloc_result["pause_or_reduce_candidates"]]
rprint(f"\n  Scale-up candidates ({len(scale_kws)}): [bold]{scale_kws}[/bold]")
rprint(f"  Pause/reduce candidates ({len(pause_kws)}): [bold]{pause_kws}[/bold]")

# Scale-up may be empty if no keyword clears 10 conversions in the suppressed window.
# That's correct behaviour — the agent should rely on analyze_roas for Signal D instead.
rprint("\n  [bold]Volume note:[/bold] scale-up threshold is 10 conversions in the recent window.")
rprint("  Under-pacing suppression (Signal B) reduces Solar Leads Q1 volume,")
rprint("  so 'solar installation near me' surfaces via analyze_roas, not compute_budget_reallocation.")

# Verify that 'home insurance quotes' qualifies for pause consideration (ROAS < 1.0, cost > $100)
# even if it doesn't make the top-3 worst (three zero-revenue general keywords rank lower).
w = get_date_windows(df)
rec = df[(df["date"] >= w["recent_start"]) & (df["date"] <= w["yesterday"])]
hiq_rec = rec[rec["keyword"] == "home insurance quotes"]
hiq_cost = hiq_rec["cost"].sum()
hiq_roas = hiq_rec["revenue"].sum() / hiq_cost if hiq_cost > 0 else None

rprint("\n  [bold]Signal A cross-check (pause eligibility):[/bold]")
check(
    "'home insurance quotes' cost > $100 in recent window",
    hiq_cost > 100,
    f"cost = ${hiq_cost:.2f}",
)
check(
    "'home insurance quotes' ROAS < 1.0 in recent window (pause-eligible)",
    hiq_roas is not None and hiq_roas < 1.0,
    f"ROAS = {hiq_roas:.2f}" if hiq_roas else "ROAS = None",
)


# ── Summary ───────────────────────────────────────────────────────────────────

section("Summary")
rprint("  All five tools executed. Review the checks above.")
rprint("  Signals expected in the briefing:")
rprint("    A  CPA spike on 'home insurance quotes'")
rprint("    B  Solar Leads Q1 under-pacing budget by ~22%")
rprint("    C  4 irrelevant zero-conversion search terms wasting spend")
rprint("    D  'solar installation near me' overperforming on ROAS — room to scale")
console.print()
