"""
renderer.py — HTML briefing renderer for AdRx.

render_briefing(briefing, output_path) writes a self-contained HTML file
and opens it in the default browser.
"""

import os
import webbrowser
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
from plotly.io import to_html
from jinja2 import Environment, FileSystemLoader


# ── Public entry point ────────────────────────────────────────────────────────

def render_briefing(briefing: dict, output_path: str) -> None:
    """
    Render the briefing dict to a self-contained HTML file and open it.

    Parameters
    ----------
    briefing    : dict returned by agent.generate_briefing()
    output_path : destination path for the HTML file
    """
    account_health_chart = _make_account_health_chart(briefing)
    cpa_trend_chart = _make_cpa_trend_chart(briefing)

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    env.filters["fmt_date_long"] = _fmt_date_long
    env.filters["fmt_currency"]  = _fmt_currency
    env.filters["fmt_roas"]      = _fmt_roas

    template = env.get_template("briefing.html")

    html = template.render(
        user_name=briefing.get("user_name", ""),
        briefing_date=briefing.get("briefing_date", ""),
        account_summary=briefing.get("account_summary", {}),
        findings=briefing.get("findings", []),
        account_health_chart=account_health_chart,
        cpa_trend_chart=cpa_trend_chart,
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    webbrowser.open(f"file://{os.path.abspath(output_path)}")


# ── Jinja2 filters ────────────────────────────────────────────────────────────

def _fmt_date_long(date_str: str) -> str:
    """'2026-04-14' → 'April 14, 2026'"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except (ValueError, TypeError):
        return str(date_str)


def _fmt_currency(value) -> str:
    """12345.6 → '$12,346'"""
    try:
        return f"${float(value):,.0f}"
    except (ValueError, TypeError):
        return str(value)


def _fmt_roas(value) -> str:
    """1.23 → '1.23x'"""
    try:
        return f"{float(value):.2f}x"
    except (ValueError, TypeError):
        return str(value)


# ── Plotly chart builders ─────────────────────────────────────────────────────

def _make_account_health_chart(briefing: dict) -> str:
    """
    Combined bar + line chart: Spend & Revenue bars, Daily Budget dashed line,
    ROAS line on a secondary y-axis.

    include_plotlyjs=True so this chart carries the full Plotly bundle.
    """
    trends = briefing.get("account_trends", {})
    dates         = trends.get("dates", [])
    daily_spend   = trends.get("daily_spend", [])
    daily_revenue = trends.get("daily_revenue", [])
    daily_roas    = trends.get("daily_roas", [])
    budget_line   = trends.get("budget_line", [])

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Daily Spend",
        x=dates,
        y=daily_spend,
        marker_color="#4A7FB0",
        yaxis="y",
        offsetgroup=1,
    ))

    fig.add_trace(go.Bar(
        name="Daily Revenue",
        x=dates,
        y=daily_revenue,
        marker_color="#5B9279",
        yaxis="y",
        offsetgroup=2,
    ))

    if budget_line:
        fig.add_trace(go.Scatter(
            name="Daily Budget",
            x=dates,
            y=budget_line,
            mode="lines",
            line=dict(color="#f97316", dash="dash", width=2),
            yaxis="y",
        ))

    fig.add_trace(go.Scatter(
        name="Daily ROAS (right axis)",
        x=dates,
        y=daily_roas,
        mode="lines+markers",
        line=dict(color="#E8A54A", width=2),
        marker=dict(size=7, color="#E8A54A", symbol="circle"),
        yaxis="y2",
        connectgaps=False,
    ))

    fig.update_layout(
        title=dict(text="Account Health — Last 7 Days", font=dict(size=14, color="#334155")),
        barmode="group",
        yaxis=dict(
            title="Spend / Revenue ($)",
            gridcolor="#E5E5E5",
            showgrid=True,
            zeroline=False,
        ),
        yaxis2=dict(
            title="ROAS (x)",
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            font=dict(size=12),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size=12),
        margin=dict(l=50, r=60, t=90, b=50),
        height=360,
    )

    return to_html(fig, include_plotlyjs="cdn", full_html=False, config={"displayModeBar": False})


def _make_cpa_trend_chart(briefing: dict) -> str:
    """
    Line chart showing daily CPA over the last 7 days.

    include_plotlyjs=False — reuses the bundle loaded by the first chart.
    """
    trends    = briefing.get("account_trends", {})
    dates     = trends.get("dates", [])
    daily_cpa = trends.get("daily_cpa", [])

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        name="Daily CPA",
        x=dates,
        y=daily_cpa,
        mode="lines+markers",
        line=dict(color="#C06B6B", width=2),
        marker=dict(size=7, color="#C06B6B", symbol="circle"),
        connectgaps=False,
        fill="tozeroy",
        fillcolor="rgba(192,107,107,0.08)",
    ))

    fig.update_layout(
        title=dict(text="CPA Trend — Last 7 Days", font=dict(size=14, color="#334155")),
        xaxis=dict(
            title="Date",
            gridcolor="#E5E5E5",
            showgrid=False,
        ),
        yaxis=dict(
            title="CPA ($)",
            gridcolor="#E5E5E5",
            showgrid=True,
            zeroline=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            font=dict(size=12),
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size=12),
        margin=dict(l=50, r=40, t=90, b=50),
        height=360,
    )

    return to_html(fig, include_plotlyjs=False, full_html=False, config={"displayModeBar": False})
