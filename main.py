import click


@click.group()
def cli():
    """adrx — agentic AI campaign performance analyst."""
    pass


@cli.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the Google Ads-style CSV file.",
)
@click.option(
    "--output",
    "output_path",
    required=False,
    default=None,
    type=click.Path(),
    help="Optional path to write the briefing as JSON.",
)
def brief(input_path, output_path):
    """Generate a morning performance briefing from campaign CSV data."""
    click.echo(f"input:  {input_path}")
    click.echo(f"output: {output_path}")


if __name__ == "__main__":
    cli()
