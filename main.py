import os
import sys
from datetime import date

import click

from agent import generate_briefing
from renderer import render_briefing


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
    "--user",
    default="Sarah Chen",
    show_default=True,
    help="Name of the person the briefing is addressed to.",
)
def brief(input_path, user):
    """Generate a morning performance briefing from campaign CSV data."""
    try:
        briefing = generate_briefing(input_path, user_name=user)
    except Exception as exc:
        click.echo(f"\nError: {exc}", err=True)
        sys.exit(1)

    briefing_date = briefing.get("briefing_date", date.today().isoformat())
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"briefing_{briefing_date}.html")

    render_briefing(briefing, output_path)

    click.echo("Briefing generated — opening in browser...")
    click.echo(output_path)


if __name__ == "__main__":
    cli()
