"""Command-line interface for GarminAnalyzer."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)
from rich.console import Console

from garmin_analyzer.auth import GarminAuth
from garmin_analyzer.client import GarminAnalyzer
from garmin_analyzer.daily import parse_date_input
from garmin_analyzer.evaluator import evaluate_daily_health, print_evaluation_summary
from garmin_analyzer.formatter import (
    print_activities_table,
    print_activity_summary,
    print_daily_summary,
)
from garmin_analyzer.uploader import (
    DEFAULT_MEMREPORT_URL,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    MemReportClient,
)

app = typer.Typer(
    name="garmin-analyzer",
    help="Download and analyze recent Garmin activities, telemetry, GPS tracks, daily health stats, and photos.",
    add_completion=False,
)
console = Console()


def get_authenticated_client(
    token_dir: Path | None = None,
    email: str | None = None,
    password: str | None = None,
    force_reauth: bool = False,
):
    """Initializes GarminAuth and logs in."""
    auth = GarminAuth(token_dir=token_dir, email=email, password=password)
    return auth.login(force_reauth=force_reauth)


@app.command()
def download(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Number of recent activities to download.",
            min=1,
            max=500,
        ),
    ] = 10,
    activity_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            "-t",
            help="Filter by activity type (e.g. running, cycling, walking, hiking).",
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Destination directory for downloads.",
        ),
    ] = Path("./garmin_data"),
    include_tracks: Annotated[
        bool,
        typer.Option(
            "--tracks/--no-tracks",
            help="Download GPS tracks (GPX, TCX, and FIT files).",
        ),
    ] = True,
    include_photos: Annotated[
        bool,
        typer.Option(
            "--photos/--no-photos",
            help="Discover and download attached activity photos.",
        ),
    ] = True,
    include_daily: Annotated[
        bool,
        typer.Option(
            "--daily/--no-daily",
            help="Download daily health stats and 7-day averages for activity dates.",
        ),
    ] = True,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Re-download already existing files.",
        ),
    ] = False,
    token_dir: Annotated[
        Path | None,
        typer.Option(
            "--token-dir",
            help="Directory to store/load OAuth session tokens.",
        ),
    ] = None,
    email: Annotated[
        str | None,
        typer.Option(
            "--email",
            "-e",
            help="Garmin Connect account email (or GARMIN_EMAIL env).",
        ),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            "-p",
            help="Garmin Connect password (or GARMIN_PASSWORD env).",
        ),
    ] = None,
) -> None:
    """Download recent Garmin activities with complete stats, tracks, photos, and daily health metrics."""
    client = get_authenticated_client(token_dir=token_dir, email=email, password=password)
    analyzer = GarminAnalyzer(client, console=console)

    results = analyzer.download_batch(
        limit=limit,
        activity_type=activity_type,
        output_dir=output_dir,
        include_tracks=include_tracks,
        include_photos=include_photos,
        include_daily=include_daily,
        force=force,
    )

    if results:
        console.print("\n[bold]Most Recent Activity Summary:[/bold]")
        print_activity_summary(results[0], console)


@app.command()
def activity(
    activity_id: Annotated[
        int,
        typer.Argument(help="Garmin Activity ID to download and inspect."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Destination directory for downloads.",
        ),
    ] = Path("./garmin_data"),
    include_tracks: Annotated[
        bool,
        typer.Option(
            "--tracks/--no-tracks",
            help="Download GPS tracks (GPX, TCX, and FIT files).",
        ),
    ] = True,
    include_photos: Annotated[
        bool,
        typer.Option(
            "--photos/--no-photos",
            help="Discover and download attached photos.",
        ),
    ] = True,
    include_daily: Annotated[
        bool,
        typer.Option(
            "--daily/--no-daily",
            help="Download daily health stats and 7-day averages for that day.",
        ),
    ] = True,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Re-download already existing files.",
        ),
    ] = False,
    token_dir: Annotated[
        Path | None,
        typer.Option(
            "--token-dir",
            help="Directory to store/load OAuth session tokens.",
        ),
    ] = None,
) -> None:
    """Download and view all information for a specific Garmin activity by ID."""
    client = get_authenticated_client(token_dir=token_dir)
    analyzer = GarminAnalyzer(client, console=console)

    console.print(f"[cyan]Fetching activity {activity_id}...[/cyan]")
    raw_act = client.get_activity(activity_id)
    if not raw_act:
        console.print(f"[red]Activity {activity_id} not found.[/red]")
        raise typer.Exit(1)

    downloaded = analyzer.download_activity(
        raw_act,
        output_dir=output_dir,
        include_tracks=include_tracks,
        include_photos=include_photos,
        include_daily=include_daily,
        force=force,
    )

    print_activity_summary(downloaded, console)
    console.print(f"\n[green]Saved to: [bold]{downloaded.directory}[/bold][/green]")


@app.command()
def daily(
    date: Annotated[
        str | None,
        typer.Option(
            "--date",
            "-d",
            help="Target date (e.g. 16.09.2026, 2026-09-16, today, yesterday). Defaults to today.",
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Destination directory for health stats.",
        ),
    ] = Path("./garmin_data"),
    include_activities: Annotated[
        bool,
        typer.Option(
            "--activities/--no-activities",
            help="Download all activities recorded on that day.",
        ),
    ] = True,
    include_tracks: Annotated[
        bool,
        typer.Option(
            "--tracks/--no-tracks",
            help="Download GPS tracks (GPX, TCX, FIT) for activities.",
        ),
    ] = True,
    include_photos: Annotated[
        bool,
        typer.Option(
            "--photos/--no-photos",
            help="Download uploaded photos attached to activities.",
        ),
    ] = True,
    llm_summary: Annotated[
        bool,
        typer.Option(
            "--llm-summary",
            "--llm_summary",
            help="Generate an AI-powered first-person diary story with embedded base64 images.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Re-fetch and overwrite existing cached data.",
        ),
    ] = False,
    upload: Annotated[
        bool,
        typer.Option(
            "--upload",
            help="Automatically upload markdown diary/summary to MemReport.",
        ),
    ] = False,
    memreport_url: Annotated[
        str,
        typer.Option(
            "--memreport-url",
            help="MemReport endpoint URL.",
        ),
    ] = DEFAULT_MEMREPORT_URL,
    memreport_user: Annotated[
        str,
        typer.Option(
            "--memreport-user",
            help="MemReport username.",
        ),
    ] = DEFAULT_USERNAME,
    memreport_pass: Annotated[
        str,
        typer.Option(
            "--memreport-pass",
            help="MemReport password.",
        ),
    ] = DEFAULT_PASSWORD,
    token_dir: Annotated[
        Path | None,
        typer.Option(
            "--token-dir",
            help="Directory to store/load OAuth session tokens.",
        ),
    ] = None,
) -> None:
    """Download all health information and activities for a specific day."""
    try:
        target_date, _ = parse_date_input(date)
    except ValueError as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(1) from err

    client = get_authenticated_client(token_dir=token_dir)
    analyzer = GarminAnalyzer(client, console=console)

    console.print(
        f"[cyan]Fetching daily health data & activities for [bold]{target_date}[/bold]...[/cyan]"
    )
    daily_summary, downloaded_activities, diary_path = analyzer.download_daily(
        target_date,
        output_dir=output_dir,
        include_activities=include_activities,
        include_tracks=include_tracks,
        include_photos=include_photos,
        generate_llm_summary=llm_summary,
        force=force,
    )

    print_daily_summary(daily_summary, console)

    # Print condensed evaluation
    evaluation = evaluate_daily_health(daily_summary)
    console.print()
    print_evaluation_summary(evaluation, console)

    # Print activities summary if downloaded
    if downloaded_activities:
        console.print()
        print_activities_table(
            [da.overview for da in downloaded_activities],
            console=console,
            title=f"🏃 Activities Recorded on {target_date} ({len(downloaded_activities)})",
        )
        for da in downloaded_activities:
            console.print(
                f"[dim]  • {da.overview.activity_name}: saved to {Path(da.directory).name}/[/dim]"
            )
    elif include_activities:
        console.print(f"\n[dim]No recorded activities found on {target_date}.[/dim]")

    if diary_path and diary_path.exists():
        console.print()
        console.print(
            f"[bold green]✨ AI Personal Daily Journal generated:[/bold green] [bold]{diary_path}[/bold]"
        )
        console.print(
            f"[dim]   (Self-contained markdown file with interactive OpenStreetMap route & Plotly biometrics, {diary_path.stat().st_size // 1024} KB)[/dim]"
        )

    save_path = output_dir / "daily_health" / target_date
    console.print(f"\n[green]Saved reports & evaluations to: [bold]{save_path}[/bold][/green]")
    charts_path = save_path / "charts"
    if charts_path.exists():
        charts = list(charts_path.glob("*.png"))
        if charts:
            console.print(f"[dim]Generated {len(charts)} visual charts in: {charts_path}[/dim]")

    # Automated upload to MemReport
    if upload:
        report_file = None
        if diary_path and diary_path.exists():
            report_file = diary_path
        else:
            daily_md = save_path / "daily_summary.md"
            if daily_md.exists():
                report_file = daily_md

        if report_file:
            console.print(f"\n[cyan]Uploading report to MemReport ({memreport_url})...[/cyan]")
            try:
                uploader = MemReportClient(
                    base_url=memreport_url,
                    username=memreport_user,
                    password=memreport_pass,
                )
                lat, lon, loc_name = None, None, None
                if downloaded_activities:
                    first_act = downloaded_activities[0]
                    lat = first_act.overview.location.start_latitude
                    lon = first_act.overview.location.start_longitude
                    loc_name = (
                        first_act.overview.location.location_name
                        or first_act.overview.activity_name
                    )

                uploader.upload_file(
                    file_path=report_file,
                    date_str=target_date,
                    latitude=lat,
                    longitude=lon,
                    location_name=loc_name,
                )
                console.print(f"[bold green]✨ Successfully uploaded {report_file.name} to MemReport: {target_date}[/bold green]")
            except Exception as e:
                console.print(f"[bold red]MemReport upload failed: {e}[/bold red]")



@app.command(name="list")
def list_activities(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Number of recent activities to show.",
            min=1,
            max=500,
        ),
    ] = 10,
    only_images: Annotated[
        bool,
        typer.Option(
            "--only-images",
            "--only_images",
            help="Only show activities where photos/images are available.",
        ),
    ] = False,
    activity_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            "-t",
            help="Filter by activity type.",
        ),
    ] = None,
    token_dir: Annotated[
        Path | None,
        typer.Option(
            "--token-dir",
            help="Directory to store/load OAuth session tokens.",
        ),
    ] = None,
) -> None:
    """Quickly display recent activities without downloading full tracks and photos."""
    client = get_authenticated_client(token_dir=token_dir)
    analyzer = GarminAnalyzer(client, console=console)

    raw_activities = analyzer.get_recent_activities(limit=limit, activity_type=activity_type)
    if not raw_activities:
        console.print("[yellow]No activities found.[/yellow]")
        return

    parsed = [analyzer.parse_activity(a) for a in raw_activities]

    # Check MemReport uploaded status if configured
    try:
        uploader = MemReportClient()
        uploaded_dates = uploader.get_uploaded_dates()
        for a in parsed:
            a.memreport_uploaded = a.date_str in uploaded_dates
    except Exception:
        pass

    if only_images:
        with console.status(
            f"[bold blue]Inspecting {len(parsed)} recent activities for photos...[/bold blue]"
        ):
            analyzer.check_activities_photos(parsed)

        parsed = [a for a in parsed if a.photos_count > 0]
        if not parsed:
            console.print(
                f"[yellow]No activities with photos found in the last {len(raw_activities)} activities.[/yellow]"
            )
            return

        print_activities_table(
            parsed,
            console,
            title=f"Garmin Activities with Photos ({len(parsed)} found in last {len(raw_activities)} activities)",
            show_photos=True,
            show_memreport=True,
        )
    else:
        print_activities_table(parsed, console, show_memreport=True)


@app.command()
def login(
    token_dir: Annotated[
        Path | None,
        typer.Option(
            "--token-dir",
            help="Directory to store session tokens.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force new login even if token cache exists.",
        ),
    ] = False,
) -> None:
    """Log into Garmin Connect and persist session tokens for subsequent commands."""
    auth = GarminAuth(token_dir=token_dir)
    client = auth.login(force_reauth=force)
    console.print(f"[bold green]Ready to use! Authenticated as: {client.display_name}[/bold green]")


@app.command()
def status(
    token_dir: Annotated[
        Path | None,
        typer.Option(
            "--token-dir",
            help="Directory to inspect for cached tokens.",
        ),
    ] = None,
) -> None:
    """Check authentication and session token cache status."""
    auth = GarminAuth(token_dir=token_dir)
    has_tokens = auth.has_cached_tokens()

    console.print(f"Token Directory: [bold]{auth.token_dir}[/bold]")
    if has_tokens:
        token_files = list(auth.token_dir.glob("*.json"))
        console.print(
            f"[green]✓ Token cache exists ({len(token_files)} token file(s) present)[/green]"
        )
        try:
            client = auth.login()
            console.print(
                f"[green]✓ Token valid for user: [bold]{client.display_name}[/bold][/green]"
            )
        except (
            GarminConnectConnectionError,
            GarminConnectAuthenticationError,
            OSError,
            ValueError,
            KeyError,
        ) as e:
            console.print(
                f"[yellow]Token verification failed ({e}). Run `garmin-analyzer login` to refresh.[/yellow]"
            )
    else:
        console.print(
            f"[yellow]No cached tokens found in {auth.token_dir}. Run `garmin-analyzer login` to authenticate.[/yellow]"
        )


@app.command(name="upload")
def upload_report_cmd(
    file: Annotated[
        Path,
        typer.Option(
            "--file",
            "-f",
            help="Path to the markdown report file to upload.",
        ),
    ],
    date: Annotated[
        str,
        typer.Option(
            "--date",
            "-d",
            help="Target date for the report (YYYY-MM-DD or DD.MM.YYYY).",
        ),
    ],
    url: Annotated[
        str,
        typer.Option(
            "--url",
            "--memreport-url",
            help="MemReport base URL endpoint.",
        ),
    ] = DEFAULT_MEMREPORT_URL,
    username: Annotated[
        str,
        typer.Option(
            "--username",
            "-u",
            "--memreport-user",
            help="MemReport username.",
        ),
    ] = DEFAULT_USERNAME,
    password: Annotated[
        str,
        typer.Option(
            "--password",
            "-p",
            "--memreport-pass",
            help="MemReport password.",
        ),
    ] = DEFAULT_PASSWORD,
    lat: Annotated[
        float | None,
        typer.Option(
            "--lat",
            help="Optional GPS latitude for map pinning.",
        ),
    ] = None,
    lon: Annotated[
        float | None,
        typer.Option(
            "--lon",
            help="Optional GPS longitude for map pinning.",
        ),
    ] = None,
    location_name: Annotated[
        str | None,
        typer.Option(
            "--location-name",
            help="Optional GPS location name.",
        ),
    ] = None,
) -> None:
    """Upload a markdown report and optional GPS coordinates directly to MemReport."""
    target_date, _ = parse_date_input(date)
    if not file.exists():
        console.print(f"[bold red]File not found: {file}[/bold red]")
        raise typer.Exit(1)

    client = MemReportClient(base_url=url, username=username, password=password)
    try:
        client.login()
        client.upload_file(
            file_path=file,
            date_str=target_date,
            latitude=lat,
            longitude=lon,
            location_name=location_name,
        )
        console.print(
            f"[bold green]✨ Successfully uploaded {file.name} for {target_date} to MemReport ({url})![/bold green]"
        )
    except Exception as e:
        console.print(f"[bold red]Upload to MemReport failed: {e}[/bold red]")
        raise typer.Exit(1) from e


@app.command(name="web")
def run_web_server(
    host: Annotated[
        str,
        typer.Option(
            "--host",
            "-h",
            help="Host address to bind to.",
        ),
    ] = "0.0.0.0",
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port to bind to.",
        ),
    ] = 8080,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload",
            help="Enable automatic reload on code changes.",
        ),
    ] = False,
) -> None:
    """Launch the Garmin Analyzer FastAPI Web UI with uvicorn."""
    import uvicorn

    console.print(f"[bold cyan]🚀 Starting Garmin Analyzer Web UI on http://{host}:{port}[/bold cyan]")
    console.print("[dim]Admin Password can be configured via WEB_ADMIN_PASSWORD (default: admin123)[/dim]")
    uvicorn.run("garmin_analyzer.web.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()

