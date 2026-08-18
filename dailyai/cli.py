"""CLI interface for DailyAI Autonomous Pipeline."""

import os
from pathlib import Path
import sys
from typing import Optional
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dailyai.config import Settings, get_settings, reset_settings
from dailyai.logging_config import setup_logging
from dailyai.models.article import DomainType
from dailyai.pipeline.orchestrator import PipelineOrchestrator
from dailyai.services.scheduler.scheduler import PipelineScheduler
from dailyai.services.storage.sqlite import SQLiteDeduplicationStore

console = Console()


@click.group()
@click.option("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
def cli(log_level: str):
    """DailyAI — Autonomous Agentic Intelligence & Fact-Checking Pipeline.

    Monitors AI, Cybersecurity, and V2X developments, verifies claims,
    synthesizes executive briefings, and delivers newsletters.
    """
    setup_logging(level=log_level)


@cli.command("run")
@click.option("--provider", type=click.Choice(["gemini", "openai", "mock"], case_sensitive=False), help="LLM Provider override")
@click.option("--search", type=click.Choice(["duckduckgo", "tavily", "serper", "rss_only", "mock"], case_sensitive=False), help="Search provider override")
@click.option("--lookback", type=int, default=None, help="Lookback window in hours")
@click.option("--max-articles", type=int, default=None, help="Max articles per category")
@click.option("--recipients", type=str, default=None, help="Comma-separated recipient emails")
@click.option("--email/--no-email", default=None, help="Enable or disable SMTP email dispatch")
@click.option("--dry-run", is_flag=True, default=False, help="Run without permanently saving deduplication records")
def run_command(
    provider: Optional[str],
    search: Optional[str],
    lookback: Optional[int],
    max_articles: Optional[int],
    recipients: Optional[str],
    email: Optional[bool],
    dry_run: bool,
):
    """Execute a complete intelligence gathering, fact-checking, and newsletter run."""
    # Load base settings
    base_cfg = get_settings().model_dump()

    # Apply CLI overrides
    if provider:
        base_cfg["llm_provider"] = provider
    if search:
        base_cfg["search_provider"] = search
    if lookback:
        base_cfg["lookback_hours"] = lookback
    if max_articles:
        base_cfg["max_articles_per_category"] = max_articles
    if recipients:
        base_cfg["email_recipients"] = [r.strip() for r in recipients.split(",") if r.strip()]
    if email is not None:
        base_cfg["email_enabled"] = email
    if dry_run:
        base_cfg["dry_run"] = True

    settings = Settings(**base_cfg)
    reset_settings(settings)

    console.print(
        Panel.fit(
            f"[bold cyan]DailyAI Intelligence Pipeline[/bold cyan]\n"
            f"LLM Provider: [green]{settings.llm_provider}[/green] | "
            f"Search Engine: [green]{settings.search_provider}[/green] | "
            f"Lookback: [yellow]{settings.lookback_hours}h[/yellow] | "
            f"Dry Run: [magenta]{settings.dry_run}[/magenta]\n"
            f"Email Dispatch: [{'green' if settings.email_enabled else 'red'}]{'ENABLED' if settings.email_enabled else 'DISABLED'}[/]"
            f" -> {', '.join(settings.email_recipients)}",
            title="Pipeline Initializing",
            border_style="cyan",
        )
    )

    orchestrator = PipelineOrchestrator(settings=settings)
    report, newsletter = orchestrator.run()

    # Display Rich summary table
    table = Table(title=f"Pipeline Execution Report: {report.run_id}", show_header=True, header_style="bold magenta")
    table.add_column("Domain / Category", style="cyan")
    table.add_column("Published Articles", justify="right", style="green")

    for domain in [DomainType.AI, DomainType.CYBERSECURITY, DomainType.V2X]:
        count = report.domain_breakdown.get(domain, 0)
        table.add_row(domain.display_name, str(count))

    console.print()
    console.print(table)

    stats_panel = (
        f"[bold]Runtime Duration:[/bold] {report.duration_seconds}s\n"
        f"[bold]Drafts Collected (Agent 1):[/bold] {report.drafts_collected}\n"
        f"[bold]Articles Verified (Agent 2):[/bold] {report.articles_verified} (Rejected: {report.articles_rejected})\n"
        f"[bold]Total Published (Agent 3):[/bold] {report.articles_published}\n"
        f"[bold]Delivery Status:[/bold] {report.delivery_status}\n"
        f"[bold]Artifacts Archived:[/bold] {settings.output_dir.resolve()}"
    )
    console.print(Panel(stats_panel, title="Run Statistics", border_style="green" if report.is_success else "red"))

    if newsletter:
        console.print(f"\n[bold green]✓ Newsletter Generated:[/bold green] {newsletter.title}")
        console.print(f"HTML Preview: [link=file://{settings.output_dir.resolve()}/latest.html]{settings.output_dir.resolve()}/latest.html[/link]")


@cli.command("schedule")
@click.option("--cron", type=str, default=None, help="Cron expression override (e.g. '0 8 * * *')")
@click.option("--interval", type=int, default=None, help="Interval in minutes override")
def schedule_command(cron: Optional[str], interval: Optional[int]):
    """Start the automated recurring pipeline scheduler."""
    base_cfg = get_settings().model_dump()
    if cron:
        base_cfg["schedule_cron"] = cron
    if interval:
        base_cfg["schedule_interval_minutes"] = interval

    settings = Settings(**base_cfg)
    reset_settings(settings)

    console.print(
        Panel.fit(
            f"[bold cyan]DailyAI Scheduler Service[/bold cyan]\n"
            f"Cron Pattern: [green]{settings.schedule_cron or 'None'}[/green]\n"
            f"Interval: [yellow]{settings.schedule_interval_minutes} minutes[/yellow]\n"
            f"Press [bold red]Ctrl+C[/bold red] to stop.",
            title="Scheduler Running",
            border_style="blue",
        )
    )

    scheduler = PipelineScheduler(settings=settings)
    scheduler.start_blocking()


@cli.command("history")
@click.option("--limit", type=int, default=5, help="Number of past runs to display")
def history_command(limit: int):
    """View recent pipeline execution history and audit logs."""
    settings = get_settings()
    store = SQLiteDeduplicationStore(settings.database_path)
    runs = store.get_recent_runs(limit=limit)

    if not runs:
        console.print("[yellow]No pipeline execution history found in database.[/yellow]")
        return

    table = Table(title=f"Recent Pipeline Execution History (Last {len(runs)})", header_style="bold blue")
    table.add_column("Run ID", style="cyan")
    table.add_column("Started At", style="white")
    table.add_column("Duration", justify="right", style="yellow")
    table.add_column("Drafts", justify="right")
    table.add_column("Verified", justify="right", style="green")
    table.add_column("Published", justify="right", style="bold green")
    table.add_column("Status", style="magenta")

    for r in runs:
        table.add_row(
            r.get("run_id", "N/A"),
            r.get("started_at", "")[:19].replace("T", " "),
            f"{r.get('duration_seconds', 0):.1f}s",
            str(r.get("drafts_collected", 0)),
            str(r.get("articles_verified", 0)),
            str(r.get("articles_published", 0)),
            r.get("delivery_status", "UNKNOWN"),
        )

    console.print(table)


@cli.command("preview")
def preview_command():
    """Generate a fast preview newsletter using mock data to inspect formatting."""
    base_cfg = get_settings().model_dump()
    base_cfg["llm_provider"] = "mock"
    base_cfg["search_provider"] = "mock"
    base_cfg["enable_rss_feeds"] = False
    base_cfg["email_enabled"] = False
    base_cfg["dry_run"] = True

    settings = Settings(**base_cfg)
    reset_settings(settings)

    console.print("[cyan]Generating preview newsletter with mock intelligence data...[/cyan]")
    orchestrator = PipelineOrchestrator(settings=settings)
    report, newsletter = orchestrator.run()

    if newsletter:
        console.print(Panel(newsletter.text_content, title="Plain Text Email Preview", border_style="blue"))
        console.print(f"\n[green]HTML Preview generated at:[/green] {settings.output_dir.resolve()}/latest.html")


@cli.command("reset-cache")
@click.confirmation_option(prompt="Are you sure you want to clear the seen URLs and publication history?")
def reset_cache_command():
    """Clear all deduplication caches, seen URLs, and run history in the database."""
    settings = get_settings()
    if settings.database_path.exists():
        try:
            settings.database_path.unlink()
            console.print(f"[green]✓ Successfully cleared database cache at:[/green] {settings.database_path.resolve()}")
        except Exception as e:
            console.print(f"[red]Failed to delete database file:[/red] {e}")
    else:
        console.print("[yellow]Database file does not exist. Nothing to clear.[/yellow]")


def main():
    """Entry point for CLI script."""
    cli()


if __name__ == "__main__":
    main()
