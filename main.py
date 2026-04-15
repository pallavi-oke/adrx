import json
import sys

import click
import plotext as plt
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from agent import generate_briefing
from tools import load_data, _recent, _baseline, _cpa, _roas

console = Console()

_SEVERITY_COLOR = {"high": "red", "medium": "yellow", "low": "green"}


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """adrx — agentic AI campaign performance analyst."""
    pass


# ── brief ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option(
    "--input", "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the Google Ads-style CSV file.",
)
@click.option(
    "--output", "output_path",
    required=False,
    default=None,
    type=click.Path(),
    help="Optional path to write the briefing as JSON.",
)
def brief(input_path, output_path):
    """Generate a morning performance briefing from campaign CSV data."""

    console.print("\n[bold cyan]AdRx[/bold cyan] — running analysis…\n")
    try:
        briefing = generate_briefing(input_path)
    except Exception as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        sys.exit(1)

    # ── Header ────────────────────────────────────────────────────────────────
    briefing_date = briefing.get("briefing_date", "—")
    summary = briefing.get("summary", "")

    console.print()
    console.print(
        Panel(
            Text(summary, style="bold white"),
            title=f"[bold cyan]AdRx Morning Briefing  ·  {briefing_date}[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
    )
    console.print()

    # ── Finding panels ────────────────────────────────────────────────────────
    findings = briefing.get("findings", [])
    for finding in findings:
        severity  = finding.get("severity", "low")
        color     = _SEVERITY_COLOR.get(severity, "white")
        priority  = finding.get("priority", "?")
        title     = finding.get("title", "")
        detail    = finding.get("detail", "")
        rec       = finding.get("recommendation", "")
        impact    = finding.get("estimated_impact", "")
        conf      = finding.get("confidence", "")

        body = Text()
        body.append(f"{detail}\n\n", style="white")
        body.append("Action:      ", style="bold")
        body.append(f"{rec}\n", style="white")
        body.append("Impact:      ", style="bold")
        body.append(f"{impact}\n", style="italic")
        body.append("Confidence:  ", style="bold")
        body.append(conf, style="dim")

        console.print(
            Panel(
                body,
                title=f"[bold {color}]#{priority}  {title}[/bold {color}]",
                border_style=color,
                padding=(1, 2),
            )
        )
        console.print()

    # ── Chart for #1 finding ──────────────────────────────────────────────────
    if findings:
        _render_chart(findings[0], input_path)

    # ── Optional JSON output ──────────────────────────────────────────────────
    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(briefing, fh, indent=2)
        console.print(f"\n[dim]Briefing written to {output_path}[/dim]\n")


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _render_chart(finding, csv_path):
    """Pick and render the right plotext chart for the #1 finding."""
    df = load_data(csv_path)
    text = " ".join([
        finding.get("title", ""),
        finding.get("detail", ""),
        finding.get("recommendation", ""),
    ]).lower()

    chart_type = _classify_chart(text)
    if chart_type == "cpa":
        _chart_cpa(finding, df, text)
    elif chart_type == "pacing":
        _chart_pacing(finding, df, text)
    else:
        _chart_roas(finding, df, text)


def _classify_chart(text):
    """Return 'cpa', 'pacing', or 'roas' based on finding text."""
    cpa_words    = ("cpa", "cost per acquisition", "cost per conv")
    pacing_words = ("pacing", "over-pacing", "under-pacing",
                    "overspend", "underspend", "daily budget", "budget delivery")

    if any(w in text for w in cpa_words) and any(
        w in text for w in ("spike", "increas", "high", "above", "expensive")
    ):
        return "cpa"
    if any(w in text for w in pacing_words):
        return "pacing"
    if any(w in text for w in cpa_words):
        return "cpa"
    return "roas"


def _pick_entity(text, candidates):
    """Return the longest candidate name that appears in text, or None."""
    for name in sorted(candidates, key=len, reverse=True):
        if name.lower() in text:
            return name
    return None


def _chart_cpa(finding, df, text):
    """Recent vs baseline CPA for the keyword flagged in the finding."""
    keywords = df["keyword"].unique().tolist()
    kw = _pick_entity(text, keywords)
    if kw is None:
        kw = _recent(df).groupby("keyword")["cost"].sum().idxmax()

    rec_df  = _recent(df)
    base_df = _baseline(df)
    r = rec_df[rec_df["keyword"] == kw]
    b = base_df[base_df["keyword"] == kw]

    recent_cpa   = _cpa(r["cost"].sum(), r["conversions"].sum())
    baseline_cpa = _cpa(b["cost"].sum(), b["conversions"].sum())

    labels, values = [], []
    if baseline_cpa is not None:
        labels.append("Baseline")
        values.append(baseline_cpa)
    if recent_cpa is not None:
        labels.append("Recent")
        values.append(recent_cpa)

    if not values:
        return

    plt.clf()
    plt.theme("clear")
    plt.bar(labels, values, color=["blue", "red"][:len(values)])
    plt.title(f"CPA — {kw}")
    plt.ylabel("$ per conversion")
    plt.show()


def _chart_pacing(finding, df, text):
    """Daily spend for the last 7 days for the campaign in the finding."""
    campaigns = df["campaign"].unique().tolist()
    camp = _pick_entity(text, campaigns)
    if camp is None:
        camp = _recent(df).groupby("campaign")["cost"].sum().idxmax()

    daily = (
        _recent(df)[_recent(df)["campaign"] == camp]
        .groupby("date")["cost"].sum()
        .reset_index()
        .sort_values("date")
    )

    if daily.empty:
        return

    labels = [str(d.date()) for d in daily["date"]]
    values = daily["cost"].round(2).tolist()

    plt.clf()
    plt.theme("clear")
    plt.bar(labels, values, color="orange")
    plt.title(f"Daily Spend — {camp}")
    plt.ylabel("Spend ($)")
    plt.show()


def _chart_roas(finding, df, text):
    """ROAS for flagged keyword vs account average, or bottom-5 by ROAS."""
    rec = _recent(df)
    agg = (
        rec.groupby("keyword")
        .agg(cost=("cost", "sum"), revenue=("revenue", "sum"))
        .reset_index()
    )
    agg["roas"] = agg.apply(lambda r: _roas(r["cost"], r["revenue"]), axis=1)
    agg = agg.dropna(subset=["roas"])

    if agg.empty:
        return

    kw = _pick_entity(text, agg["keyword"].tolist())

    if kw:
        kw_roas   = float(agg.loc[agg["keyword"] == kw, "roas"].iloc[0])
        mean_roas = round(float(agg["roas"].mean()), 2)
        labels    = [kw[:28], "Acct avg"]
        values    = [kw_roas, mean_roas]
        colors    = ["red", "blue"]
    else:
        bottom = agg[agg["cost"] >= 20].sort_values("roas").head(5)
        if bottom.empty:
            return
        labels = [k[:22] for k in bottom["keyword"].tolist()]
        values = bottom["roas"].tolist()
        colors = ["red"] * len(labels)

    plt.clf()
    plt.theme("clear")
    plt.bar(labels, values, color=colors)
    plt.title("ROAS — Finding #1")
    plt.ylabel("ROAS (revenue / cost)")
    plt.show()


if __name__ == "__main__":
    cli()
