"""
tools.py — pandas analysis functions for AdRx.

Each function takes a pre-loaded DataFrame and returns a structured dict.
The agent calls these via the Anthropic tool-use API; TOOL_SCHEMAS and
TOOL_FUNCTIONS at the bottom wire up the dispatch.

Date windows (from get_date_windows):
  recent   : [recent_start, yesterday]   — 8 days, the primary analysis window
  baseline : [baseline_start, baseline_end] — 30 days, used for trend comparisons
"""

import pandas as pd


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_data(csv_path: str) -> pd.DataFrame:
    """Read the campaign CSV, parse dates, and sort chronologically."""
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def get_date_windows(df: pd.DataFrame) -> dict:
    """
    Return the four date anchors used by every analysis function.

    Keys
    ----
    yesterday      Most recent date in the data (treated as "today's yesterday").
    recent_start   7 days before yesterday — start of the recent comparison window.
    baseline_end   8 days before yesterday — last day of the baseline window
                   (one day before the recent window, so windows don't overlap).
    baseline_start 37 days before yesterday — 30-day baseline window start.
    """
    yesterday = df["date"].max()
    return {
        "yesterday":      yesterday,
        "recent_start":   yesterday - pd.Timedelta(days=7),
        "baseline_end":   yesterday - pd.Timedelta(days=8),
        "baseline_start": yesterday - pd.Timedelta(days=37),
    }


def _recent(df: pd.DataFrame) -> pd.DataFrame:
    w = get_date_windows(df)
    return df[(df["date"] >= w["recent_start"]) & (df["date"] <= w["yesterday"])]


def _baseline(df: pd.DataFrame) -> pd.DataFrame:
    w = get_date_windows(df)
    return df[(df["date"] >= w["baseline_start"]) & (df["date"] <= w["baseline_end"])]


def _roas(cost: float, revenue: float):
    return round(revenue / cost, 2) if cost > 0 else None


def _cpa(cost: float, conversions: float):
    return round(cost / conversions, 2) if conversions > 0 else None


def _window_label(start, end) -> str:
    return f"{pd.Timestamp(start).date()} to {pd.Timestamp(end).date()}"


# ── Analysis functions ────────────────────────────────────────────────────────

def analyze_roas(df: pd.DataFrame, dimension: str) -> dict:
    """
    Group the recent 7-day window by dimension and rank entities by ROAS.

    Parameters
    ----------
    dimension : 'keyword' | 'ad_group' | 'campaign'

    Returns
    -------
    dict with top_performers and bottom_performers (up to 5 each), each entry
    containing: dimension value, cost, revenue, conversions, cpa, roas.
    """
    if dimension not in ("keyword", "ad_group", "campaign"):
        raise ValueError(f"dimension must be keyword, ad_group, or campaign — got {dimension!r}")

    w = get_date_windows(df)
    rec = _recent(df)

    agg = (
        rec.groupby(dimension)
        .agg(cost=("cost", "sum"), revenue=("revenue", "sum"), conversions=("conversions", "sum"))
        .reset_index()
    )
    agg["cpa"]  = agg.apply(lambda r: _cpa(r["cost"], r["conversions"]), axis=1)
    agg["roas"] = agg.apply(lambda r: _roas(r["cost"], r["revenue"]), axis=1)

    ranked = agg.sort_values("roas", ascending=False, na_position="last")

    def to_record(row):
        return {
            dimension:      row[dimension],
            "cost":         round(row["cost"], 2),
            "revenue":      round(row["revenue"], 2),
            "conversions":  int(row["conversions"]),
            "cpa":          row["cpa"],
            "roas":         row["roas"],
        }

    top    = [to_record(r) for _, r in ranked.head(5).iterrows()]
    bottom = [to_record(r) for _, r in ranked.tail(5).iloc[::-1].iterrows()]

    return {
        "dimension":        dimension,
        "window":           _window_label(w["recent_start"], w["yesterday"]),
        "top_performers":   top,
        "bottom_performers": bottom,
    }


def detect_budget_pacing(df: pd.DataFrame, budgets: dict) -> dict:
    """
    Flag campaigns whose average daily spend in the recent 7-day window deviates
    from their daily budget by more than 15% in either direction.

    Parameters
    ----------
    budgets : dict  e.g. {"Solar Leads Q1": 500, "Home Insurance": 400}

    Returns
    -------
    dict with a list of flagged campaigns, each containing: campaign, daily_budget,
    avg_daily_spend, pct_variance, and status ('over' | 'under').
    """
    w   = get_date_windows(df)
    rec = _recent(df)

    daily = rec.groupby(["date", "campaign"])["cost"].sum().reset_index()
    avg   = daily.groupby("campaign")["cost"].mean().reset_index()
    avg.columns = ["campaign", "avg_daily_spend"]

    flagged = []
    for _, row in avg.iterrows():
        camp   = row["campaign"]
        budget = budgets.get(camp)
        if budget is None:
            continue
        actual      = row["avg_daily_spend"]
        pct_var     = (actual - budget) / budget * 100
        if abs(pct_var) > 15:
            flagged.append({
                "campaign":        camp,
                "daily_budget":    budget,
                "avg_daily_spend": round(actual, 2),
                "pct_variance":    round(pct_var, 1),
                "status":          "over" if pct_var > 0 else "under",
            })

    flagged.sort(key=lambda x: abs(x["pct_variance"]), reverse=True)

    return {
        "window":             _window_label(w["recent_start"], w["yesterday"]),
        "flagged_campaigns":  flagged,
    }


def find_anomalies(
    df: pd.DataFrame,
    metric: str = "cpa",
    min_deviation_pct: float = 40,
    min_baseline_conversions: int = 5,
) -> dict:
    """
    Compare each keyword's recent 7-day metric value against its 30-day baseline
    and flag those that deviate by more than min_deviation_pct percent.

    Parameters
    ----------
    metric                    : 'cpa' or 'roas'
    min_deviation_pct         : minimum absolute percent change to flag (default 40)
    min_baseline_conversions  : keywords with fewer conversions than this in the
                                baseline window are skipped — their metrics are too
                                noisy to distinguish real change from random variance
                                (default 5)

    Returns
    -------
    dict with up to 10 flagged keywords, sorted by magnitude of deviation.
    Each entry includes volume context (recent and baseline conversions and cost)
    so the caller can judge statistical confidence alongside the metric change.
    """
    if metric not in ("cpa", "roas"):
        raise ValueError(f"metric must be 'cpa' or 'roas' — got {metric!r}")

    w    = get_date_windows(df)
    rec  = _recent(df)
    base = _baseline(df)

    def agg_window(sub: pd.DataFrame) -> dict:
        cost        = sub["cost"].sum()
        revenue     = sub["revenue"].sum()
        conversions = int(sub["conversions"].sum())
        if metric == "cpa":
            value = _cpa(cost, conversions)
        else:
            value = _roas(cost, revenue)
        return {"value": value, "conversions": conversions, "cost": round(cost, 2)}

    flagged = []
    for kw, rec_sub in rec.groupby("keyword"):
        base_sub = base[base["keyword"] == kw]

        rec_agg  = agg_window(rec_sub)
        base_agg = agg_window(base_sub)

        # Skip keywords with too few baseline conversions — CPA/ROAS is unreliable
        if base_agg["conversions"] < min_baseline_conversions:
            continue

        rec_val  = rec_agg["value"]
        base_val = base_agg["value"]

        if rec_val is None or base_val is None or base_val == 0:
            continue

        pct_change = (rec_val - base_val) / base_val * 100
        if abs(pct_change) < min_deviation_pct:
            continue

        flagged.append({
            "keyword":              kw,
            "metric":               metric,
            "baseline_value":       base_val,
            "recent_value":         rec_val,
            "pct_change":           round(pct_change, 1),
            "direction":            "spike" if pct_change > 0 else "drop",
            # Volume context — use these to assess statistical confidence.
            # A large pct_change on low conversion volume is likely noise.
            "recent_conversions":   rec_agg["conversions"],
            "recent_cost":          rec_agg["cost"],
            "baseline_conversions": base_agg["conversions"],
            "baseline_cost":        base_agg["cost"],
        })

    flagged.sort(key=lambda x: abs(x["pct_change"]), reverse=True)

    return {
        "metric":                   metric,
        "min_deviation_pct":        min_deviation_pct,
        "min_baseline_conversions": min_baseline_conversions,
        "recent_window":            _window_label(w["recent_start"], w["yesterday"]),
        "baseline_window":          _window_label(w["baseline_start"], w["baseline_end"]),
        "flagged_keywords":         flagged[:10],
    }


def find_new_search_terms(
    df: pd.DataFrame,
    lookback_days: int = 10,
    min_impressions: int = 100,
) -> dict:
    """
    Identify keywords that first appeared in the last lookback_days, have
    accumulated at least min_impressions, and have zero conversions.
    These are candidates for negative keyword lists.

    Parameters
    ----------
    lookback_days   : how far back to look for "new" first appearances (default 10)
    min_impressions : minimum total impressions to include (filters noise, default 100)

    Returns
    -------
    dict with a list of zero-conversion new terms, each containing: keyword,
    campaign, ad_group, first_seen, impressions, clicks, cost, conversions.
    """
    yesterday      = df["date"].max()
    lookback_start = yesterday - pd.Timedelta(days=lookback_days - 1)

    first_seen = df.groupby("keyword")["date"].min().rename("first_seen")

    new_kws = first_seen[first_seen >= lookback_start].index.tolist()
    if not new_kws:
        return {"lookback_days": lookback_days, "min_impressions": min_impressions, "new_zero_conversion_terms": []}

    recent_new = df[(df["keyword"].isin(new_kws)) & (df["date"] >= lookback_start)]

    agg = (
        recent_new.groupby(["keyword", "campaign", "ad_group"])
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            cost=("cost", "sum"),
            conversions=("conversions", "sum"),
        )
        .reset_index()
    )

    filtered = agg[(agg["impressions"] >= min_impressions) & (agg["conversions"] == 0)]

    terms = []
    for _, row in filtered.iterrows():
        terms.append({
            "keyword":     row["keyword"],
            "campaign":    row["campaign"],
            "ad_group":    row["ad_group"],
            "first_seen":  first_seen[row["keyword"]].strftime("%Y-%m-%d"),
            "impressions": int(row["impressions"]),
            "clicks":      int(row["clicks"]),
            "cost":        round(row["cost"], 2),
            "conversions": 0,
        })

    terms.sort(key=lambda x: x["impressions"], reverse=True)

    return {
        "lookback_days":            lookback_days,
        "min_impressions":          min_impressions,
        "new_zero_conversion_terms": terms,
    }


def get_account_trends(df: pd.DataFrame, days: int = 7) -> dict:
    """
    Return daily time-series data for the last `days` days across all campaigns.

    Parameters
    ----------
    days : int
        Number of trailing days to return (default 7).

    Returns
    -------
    dict with:
      dates         — list of date strings YYYY-MM-DD
      daily_spend   — total spend per day
      daily_revenue — total revenue per day
      daily_roas    — ROAS per day (None if no spend)
      daily_cpa     — CPA per day (None if conversions = 0)
      budget_line   — total daily budget across all campaigns ($900/day fixed)
    """
    yesterday = df["date"].max()
    start = yesterday - pd.Timedelta(days=days - 1)

    window = df[(df["date"] >= start) & (df["date"] <= yesterday)]

    daily = (
        window.groupby("date")
        .agg(
            spend=("cost", "sum"),
            revenue=("revenue", "sum"),
            conversions=("conversions", "sum"),
        )
        .reset_index()
    )

    # Ensure all days are present even if no data
    all_dates = pd.date_range(start=start, end=yesterday, freq="D")
    daily = daily.set_index("date").reindex(all_dates, fill_value=0).reset_index()
    daily.columns = ["date", "spend", "revenue", "conversions"]

    dates        = [d.strftime("%Y-%m-%d") for d in daily["date"]]
    daily_spend   = [round(float(v), 2) for v in daily["spend"]]
    daily_revenue = [round(float(v), 2) for v in daily["revenue"]]
    daily_roas    = [_roas(daily["spend"].iloc[i], daily["revenue"].iloc[i]) for i in range(len(daily))]
    daily_cpa     = [_cpa(daily["spend"].iloc[i], daily["conversions"].iloc[i]) for i in range(len(daily))]

    # Fixed total daily budget: Solar Leads Q1 = $500, Home Insurance = $400
    budget_line = [900.0] * len(dates)

    return {
        "dates":         dates,
        "daily_spend":   daily_spend,
        "daily_revenue": daily_revenue,
        "daily_roas":    daily_roas,
        "daily_cpa":     daily_cpa,
        "budget_line":   budget_line,
    }


def compute_account_summary(df: pd.DataFrame, findings: list) -> dict:
    """
    Deterministically compute account-level KPIs from the DataFrame.

    The findings list is accepted for API compatibility but the summary is derived
    entirely from df using fixed rules — not from parsed agent findings — so the
    output is identical on every run for the same input data.

    Waste rule
    ----------
    1. Zero-conversion new keywords (from find_new_search_terms): sum their recent
       7-day cost.
    2. CPA spike keywords (from find_anomalies metric='cpa', direction='spike'):
       excess spend above what the keyword would have cost at its baseline CPA
       (= recent_cost − recent_conversions × baseline_CPA).

    Parameters
    ----------
    df       : full campaign DataFrame
    findings : agent findings list (unused in computation; retained for signature)

    Returns
    -------
    dict with overall_roas, total_spend_7d, wasted_spend_7d, projected_roas.
    """
    rec = _recent(df)

    total_revenue = rec["revenue"].sum()
    total_cost    = rec["cost"].sum()

    overall_roas   = round(total_revenue / total_cost, 1) if total_cost > 0 else None
    total_spend_7d = round(total_cost)

    wasted = 0.0

    # 1. Zero-conversion new keywords — their entire 7-day cost is waste
    zero_conv_result = find_new_search_terms(df)
    zero_kws = {t["keyword"] for t in zero_conv_result.get("new_zero_conversion_terms", [])}
    if zero_kws:
        wasted += float(rec[rec["keyword"].isin(zero_kws)]["cost"].sum())

    # 2. CPA spike keywords — excess cost above baseline-CPA expectation
    cpa_result = find_anomalies(df, metric="cpa")
    for kw in cpa_result.get("flagged_keywords", []):
        if kw["direction"] == "spike" and kw["baseline_conversions"] > 0:
            baseline_cpa  = kw["baseline_cost"] / kw["baseline_conversions"]
            expected_cost = kw["recent_conversions"] * baseline_cpa
            excess        = kw["recent_cost"] - expected_cost
            if excess > 0:
                wasted += excess

    wasted_spend_7d = round(wasted)

    net_spend = total_spend_7d - wasted_spend_7d
    if net_spend > 0 and total_revenue > 0:
        projected_roas = round(total_revenue / net_spend, 1)
    else:
        projected_roas = overall_roas

    return {
        "overall_roas":    overall_roas,
        "total_spend_7d":  total_spend_7d,
        "wasted_spend_7d": wasted_spend_7d,
        "projected_roas":  projected_roas,
    }


def compute_budget_reallocation(df: pd.DataFrame) -> dict:
    """
    Identify which keywords to scale up and which to pause based on recent
    7-day ROAS and volume thresholds.

    Scale-up candidates   : top 3 by ROAS among keywords with >= 10 conversions.
    Pause/reduce candidates: bottom 3 by ROAS among keywords with >= $100 spend
                             and ROAS below 1.0 (spending more than they return).

    Returns
    -------
    dict with scale_up_candidates and pause_or_reduce_candidates, each entry
    containing: keyword, cost, revenue, conversions, roas.
    """
    w   = get_date_windows(df)
    rec = _recent(df)

    agg = (
        rec.groupby("keyword")
        .agg(cost=("cost", "sum"), revenue=("revenue", "sum"), conversions=("conversions", "sum"))
        .reset_index()
    )
    agg["roas"] = agg.apply(lambda r: _roas(r["cost"], r["revenue"]), axis=1)

    def to_record(row):
        return {
            "keyword":     row["keyword"],
            "cost":        round(row["cost"], 2),
            "revenue":     round(row["revenue"], 2),
            "conversions": int(row["conversions"]),
            "roas":        row["roas"],
        }

    scale_mask = agg["conversions"] >= 10
    scale_up   = [
        to_record(row)
        for _, row in agg[scale_mask].sort_values("roas", ascending=False).head(3).iterrows()
    ]

    pause_mask = (agg["cost"] >= 100) & (agg["roas"].notna()) & (agg["roas"] < 1.0)
    pause      = [
        to_record(row)
        for _, row in agg[pause_mask].sort_values("roas").head(3).iterrows()
    ]

    return {
        "window":                   _window_label(w["recent_start"], w["yesterday"]),
        "scale_up_candidates":      scale_up,
        "pause_or_reduce_candidates": pause,
    }


# ── Anthropic tool-use schemas ────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "get_account_trends",
        "description": (
            "Return daily time-series data for the last 7 days across the entire account. "
            "CALL THIS FIRST — the results provide the 7-day performance baseline needed "
            "to contextualize all findings. Note: account_trends and account_summary in the "
            "final JSON are populated deterministically by the system, not by the agent. "
            "Returns: dates (array of YYYY-MM-DD strings), daily_spend, daily_revenue, "
            "daily_roas (null where no spend), daily_cpa (null where no conversions), "
            "and budget_line (fixed at $900/day: Solar Leads Q1 $500 + Home Insurance $400)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of trailing days to return. Default is 7.",
                    "default": 7,
                },
            },
            "required": [],
        },
    },
    {
        "name": "analyze_roas",
        "description": (
            "Group performance data from the recent 7-day window by a chosen dimension "
            "(keyword, ad_group, or campaign) and rank entities by ROAS (revenue ÷ cost). "
            "Returns the top 5 and bottom 5 performers with cost, revenue, conversions, CPA, "
            "and ROAS for each. Call this first to get a quick overview of what's working and "
            "what isn't. Call it at the keyword level to surface specific scaling or pausing "
            "candidates, or at the campaign level for a high-level budget allocation view."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "enum": ["keyword", "ad_group", "campaign"],
                    "description": (
                        "The level at which to group performance. Use 'keyword' for granular "
                        "findings, 'ad_group' for mid-level, 'campaign' for budget pacing context."
                    ),
                },
            },
            "required": ["dimension"],
        },
    },
    {
        "name": "detect_budget_pacing",
        "description": (
            "Check whether each campaign's average daily spend over the recent 7 days is "
            "on track with its daily budget. Flags campaigns that are more than 15% above "
            "(over-pacing, risk of overspend) or below (under-pacing, opportunity cost) their "
            "budget. Call this whenever you want to assess budget delivery health. Returns "
            "flagged campaigns with their budget, actual daily spend, and percent variance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "budgets": {
                    "type": "object",
                    "description": (
                        "A JSON object mapping each campaign name to its daily budget in USD. "
                        "Example: {\"Solar Leads Q1\": 500, \"Home Insurance\": 400}"
                    ),
                    "additionalProperties": {"type": "number"},
                },
            },
            "required": ["budgets"],
        },
    },
    {
        "name": "find_anomalies",
        "description": (
            "Compare each keyword's recent 7-day metric value against its 30-day baseline "
            "(the 30 days ending 8 days ago, before the recent window) and flag keywords where "
            "the change exceeds min_deviation_pct. Use metric='cpa' to catch keywords where "
            "cost-per-acquisition has spiked (a spike is bad — the keyword is becoming less "
            "efficient). Use metric='roas' to catch keywords where return on spend has dropped. "
            "Returns up to 10 keywords ranked by magnitude of deviation. Each result includes "
            "volume context: recent_conversions, recent_cost, baseline_conversions, baseline_cost. "
            "IMPORTANT: use these volume fields to assess confidence before surfacing a finding. "
            "A keyword with fewer than 5 baseline conversions or fewer than 3 recent conversions "
            "has too little data for its metric change to be statistically meaningful — treat it "
            "as noise and do not include it in the briefing. Keywords with low spend (under $50) "
            "in the recent window should also be deprioritized regardless of pct_change magnitude. "
            "Only flag findings where the volume is large enough to trust the signal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["cpa", "roas"],
                    "description": (
                        "The metric to analyze. 'cpa' (cost per acquisition) flags keywords "
                        "that have become more expensive per conversion. 'roas' (revenue / cost) "
                        "flags keywords where revenue efficiency has changed."
                    ),
                },
                "min_deviation_pct": {
                    "type": "number",
                    "description": (
                        "Minimum absolute percent change from baseline required to flag a keyword. "
                        "Default is 40 (flag anything that changed by 40% or more)."
                    ),
                    "default": 40,
                },
                "min_baseline_conversions": {
                    "type": "integer",
                    "description": (
                        "Keywords with fewer conversions than this in the 30-day baseline are "
                        "excluded before computing the metric — their CPA or ROAS is too noisy "
                        "to distinguish real change from random variance. Default is 5. "
                        "Increase to 10 if you want higher confidence findings only."
                    ),
                    "default": 5,
                },
            },
            "required": ["metric"],
        },
    },
    {
        "name": "find_new_search_terms",
        "description": (
            "Find keywords that first appeared in the data within the last lookback_days and "
            "have zero conversions. These are likely irrelevant search terms that matched "
            "broad-match keywords and are wasting budget — strong negative keyword candidates. "
            "Only returns terms with at least min_impressions to filter out statistical noise. "
            "Call this to surface search term waste and protect budgets from irrelevant traffic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lookback_days": {
                    "type": "integer",
                    "description": "How many days back to look for new terms. Default is 10.",
                    "default": 10,
                },
                "min_impressions": {
                    "type": "integer",
                    "description": (
                        "Minimum total impressions over the lookback window to include a term. "
                        "Filters out terms with too little data to be actionable. Default is 100."
                    ),
                    "default": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "compute_budget_reallocation",
        "description": (
            "Identify the top 3 high-ROAS keywords that could absorb more budget (scale-up "
            "candidates: at least 10 conversions in the recent 7 days) and the bottom 3 "
            "keywords that are actively losing money and should be paused or reduced "
            "(ROAS below 1.0 with at least $100 spend in the recent 7 days). Call this to "
            "generate specific, actionable budget reallocation recommendations. Takes no "
            "parameters — it operates on the recent 7-day window automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ── Dispatch table ────────────────────────────────────────────────────────────

TOOL_FUNCTIONS = {
    "get_account_trends":          get_account_trends,
    "analyze_roas":                analyze_roas,
    "detect_budget_pacing":        detect_budget_pacing,
    "find_anomalies":              find_anomalies,
    "find_new_search_terms":       find_new_search_terms,
    "compute_budget_reallocation": compute_budget_reallocation,
}
