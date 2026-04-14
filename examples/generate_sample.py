"""
Generate synthetic Google Ads performance data for adrx examples.

Fixed reference date: 2026-04-13 (yesterday relative to 2026-04-14).
60 days of daily data ending on that date.

Embedded signals:
  A) "home insurance quotes" — CPA spike ~2x in last 7 days vs prior 30-day avg
     (CVR halved; same CPC — realistic landing page / offer degradation pattern)
  B) "Solar Leads Q1" — pacing ~23% under budget in last 7 days (~$385/day vs $500)
  C) 3-4 zero-conversion irrelevant search terms appeared in last 10 days
  D) "solar installation near me" — high ROAS overperformer with room to scale
     (strong CVR + higher revenue per conversion vs campaign peers)
"""

import random
import pandas as pd

SEED = 42
random.seed(SEED)

END_DATE = pd.Timestamp("2026-04-13")
START_DATE = END_DATE - pd.Timedelta(days=59)
DATES = pd.date_range(START_DATE, END_DATE, freq="D")

# ── Campaign / ad-group / keyword taxonomy ────────────────────────────────────
# Impressions are calibrated so baseline daily campaign spend ≈ daily_budget.
# Formula per keyword:  cost ≈ impr × ctr × cpc

STRUCTURE = {
    "Solar Leads Q1": {
        "daily_budget": 500.0,
        # Baseline total ≈ $516/day  →  suppression 0.74× → ~$382/day in last 7d
        "ad_groups": {
            "Solar General": {
                # 4 kw × ~$63/day ≈ $252
                "solar panels cost":     dict(cpc=2.80, ctr=0.030, cvr=0.040, impr=750),
                "solar energy savings":  dict(cpc=2.80, ctr=0.030, cvr=0.038, impr=750),
                "home solar system":     dict(cpc=2.80, ctr=0.030, cvr=0.042, impr=750),
                "buy solar panels":      dict(cpc=2.80, ctr=0.030, cvr=0.035, impr=750),
            },
            "Solar Local": {
                # Signal D — ROAS overperformer: strong CVR + higher rev/conv vs peers
                "solar installation near me": dict(cpc=3.20, ctr=0.045, cvr=0.075, impr=400),
                # 2 kw × ~$63/day ≈ $126
                "solar company near me":      dict(cpc=2.80, ctr=0.030, cvr=0.038, impr=750),
                "local solar installer":      dict(cpc=2.80, ctr=0.030, cvr=0.040, impr=750),
            },
            "Solar Brand": {
                # 3 kw × ~$46/day ≈ $138 (brand = lower CPC, higher volume needed)
                "sunpower solar":   dict(cpc=1.80, ctr=0.030, cvr=0.028, impr=850),
                "tesla solar roof": dict(cpc=1.80, ctr=0.030, cvr=0.025, impr=850),
                "lg solar panels":  dict(cpc=1.80, ctr=0.030, cvr=0.022, impr=850),
            },
        },
    },
    "Home Insurance": {
        "daily_budget": 400.0,
        # Baseline total ≈ $393/day
        "ad_groups": {
            "Insurance General": {
                # 4 kw × ~$42/day ≈ $168
                "home insurance":          dict(cpc=4.80, ctr=0.035, cvr=0.045, impr=250),
                "homeowners insurance":    dict(cpc=4.80, ctr=0.035, cvr=0.048, impr=250),
                "house insurance policy":  dict(cpc=4.80, ctr=0.035, cvr=0.040, impr=250),
                "best home insurance":     dict(cpc=4.80, ctr=0.035, cvr=0.042, impr=250),
            },
            "Insurance Quotes": {
                # Signal A — CPA spike last 7 days; impr high enough to yield
                # measurable conversions (~46 clicks/day, ~2.5 conv/day baseline)
                "home insurance quotes":      dict(cpc=4.50, ctr=0.038, cvr=0.055, impr=1200),
                "home insurance quote online":dict(cpc=5.20, ctr=0.042, cvr=0.058, impr=200),
                "cheap home insurance":       dict(cpc=5.20, ctr=0.042, cvr=0.050, impr=200),
                "compare home insurance":     dict(cpc=5.20, ctr=0.042, cvr=0.055, impr=200),
                "home insurance rates":       dict(cpc=5.20, ctr=0.042, cvr=0.052, impr=200),
            },
        },
    },
}

# Irrelevant search terms injected in last 10 days (Signal C) — zero conversions
JUNK_TERMS = [
    ("Home Insurance",  "Insurance General", "cheap auto policy free"),
    ("Home Insurance",  "Insurance Quotes",  "solar panels scam"),
    ("Solar Leads Q1",  "Solar General",     "free government solar program scam"),
    ("Solar Leads Q1",  "Solar Local",       "solar panels stock tips"),
]


def jitter(value, pct=0.15):
    return value * (1 + random.uniform(-pct, pct))


# ── Row generation ─────────────────────────────────────────────────────────────

rows = []
cutoff_7  = END_DATE - pd.Timedelta(days=6)   # last 7 days inclusive
cutoff_10 = END_DATE - pd.Timedelta(days=9)   # last 10 days inclusive

for date in DATES:
    last7  = date >= cutoff_7
    last10 = date >= cutoff_10

    for campaign, camp_data in STRUCTURE.items():
        for ad_group, keywords in camp_data["ad_groups"].items():
            for keyword, p in keywords.items():
                cpc  = p["cpc"]
                ctr  = p["ctr"]
                cvr  = p["cvr"]
                impr_base = p["impr"]

                # Signal A — CVR drop for "home insurance quotes" in last 7 days
                # CPC stays normal; CVR halves → CPA roughly doubles vs 30-day avg
                if keyword == "home insurance quotes" and last7:
                    cvr = cvr * 0.40   # ~60% CVR drop → ~2x CPA spike
                cpc = jitter(cpc, pct=0.12)

                # Signal B — Solar Leads Q1 under-pacing last 7 days
                # Baseline ≈ $577/day; suppress 0.667× → ~$385/day (~23% under $500)
                if campaign == "Solar Leads Q1" and last7:
                    impr_base = impr_base * 0.667

                impr       = max(1, int(jitter(impr_base, pct=0.18)))
                clicks     = max(0, int(round(impr * jitter(ctr, pct=0.18))))
                cost       = round(clicks * max(0, cpc), 2)

                # Signal D — "solar installation near me" gets tighter CVR noise
                # and a higher revenue per conversion, producing a standout ROAS
                cvr_noise = 0.10 if keyword == "solar installation near me" else 0.22
                eff_cvr   = max(0, jitter(cvr, pct=cvr_noise))
                conversions = int(round(clicks * eff_cvr))

                if keyword == "solar installation near me":
                    rev_per_conv = jitter(260, pct=0.10)   # premium installs → higher job value
                elif campaign == "Solar Leads Q1":
                    rev_per_conv = jitter(180, pct=0.15)
                else:
                    rev_per_conv = jitter(120, pct=0.15)
                revenue = round(conversions * rev_per_conv, 2)

                rows.append({
                    "date":        date.strftime("%Y-%m-%d"),
                    "campaign":    campaign,
                    "ad_group":    ad_group,
                    "keyword":     keyword,
                    "impressions": impr,
                    "clicks":      clicks,
                    "cost":        cost,
                    "conversions": conversions,
                    "revenue":     revenue,
                })

    # Signal C — inject junk terms in last 10 days only
    if last10:
        for (camp, ag, junk_kw) in JUNK_TERMS:
            impr   = random.randint(30, 90)
            ctr_j  = random.uniform(0.010, 0.025)
            clicks = max(1, int(round(impr * ctr_j)))
            cpc_j  = random.uniform(1.50, 3.50)
            cost   = round(clicks * cpc_j, 2)
            rows.append({
                "date":        date.strftime("%Y-%m-%d"),
                "campaign":    camp,
                "ad_group":    ag,
                "keyword":     junk_kw,
                "impressions": impr,
                "clicks":      clicks,
                "cost":        cost,
                "conversions": 0,
                "revenue":     0.0,
            })

df = pd.DataFrame(rows).sort_values(["date", "campaign", "ad_group", "keyword"])
df.to_csv("examples/sample_campaigns.csv", index=False)
print(f"Wrote {len(df):,} rows to examples/sample_campaigns.csv")

# ── Sanity-check the embedded signals ─────────────────────────────────────────

df["date"] = pd.to_datetime(df["date"])
cutoff7 = pd.Timestamp("2026-04-07")

# Signal A — CPA spike: aggregate cost/conversions over each window
hiq = df[df["keyword"] == "home insurance quotes"]
pre30_start = cutoff7 - pd.Timedelta(days=30)
pre_win  = hiq[(hiq["date"] >= pre30_start) & (hiq["date"] < cutoff7)]
post_win = hiq[hiq["date"] >= cutoff7]
pre_cpa  = pre_win["cost"].sum()  / pre_win["conversions"].sum()
post_cpa = post_win["cost"].sum() / post_win["conversions"].sum()
print(f"\nSignal A — 'home insurance quotes' agg CPA:  30d-pre=${pre_cpa:.2f}  last-7d=${post_cpa:.2f}  spike={post_cpa/pre_cpa:.1f}x")

# Signal B
solar  = df[(df["campaign"] == "Solar Leads Q1") & (df["date"] >= cutoff7)]
pre_s  = df[(df["campaign"] == "Solar Leads Q1") & (df["date"] < cutoff7)]
post_spend = solar.groupby("date")["cost"].sum().mean()
pre_spend  = pre_s.groupby("date")["cost"].sum().mean()
print(f"\nSignal B — Solar Leads Q1 avg daily spend:  baseline=${pre_spend:.0f}  last 7d=${post_spend:.0f}  (budget $500)")

# Signal C
junk_kws = [j[2] for j in JUNK_TERMS]
cutoff10 = pd.Timestamp("2026-04-04")
junk = df[(df["keyword"].isin(junk_kws)) & (df["date"] >= cutoff10)]
print(f"\nSignal C — Junk terms rows (last 10d): {len(junk)}  total conversions: {junk['conversions'].sum()}")
for kw in junk_kws:
    sub = junk[junk["keyword"] == kw]
    print(f"           {kw!r}: {len(sub)} rows, ${sub['cost'].sum():.0f} spend, {sub['conversions'].sum()} conv")

# Signal D — ROAS overperformer
def roas(sub):
    cost = sub["cost"].sum()
    return sub["revenue"].sum() / cost if cost > 0 else 0

sol_mask  = df["keyword"] == "solar installation near me"
peer_mask = (df["campaign"] == "Solar Leads Q1") & ~sol_mask & ~df["keyword"].isin([j[2] for j in JUNK_TERMS])

sol_roas  = roas(df[sol_mask])
peer_roas = roas(df[peer_mask])
sol_clicks_day = df[sol_mask].groupby("date")["clicks"].sum().mean()

print(f"\nSignal D — 'solar installation near me':  ROAS={sol_roas:.1f}x  avg clicks/day={sol_clicks_day:.1f}")
print(f"           Other Solar Leads Q1 peers:     ROAS={peer_roas:.1f}x")
