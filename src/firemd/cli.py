"""CLI entry point for firemd."""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from firemd import __version__
from firemd.config import (
    DEFAULT_API_URL,
    clear_proxy_config,
    load_proxy_url,
    parse_proxy_url,
    save_proxy_url,
)
from firemd.firecrawl import (
    CrawlJob,
    FirecrawlClient,
    FirecrawlError,
    is_success,
)
from firemd.manifest import ManifestEntry, load_manifest, save_error_entry, save_manifest_entry
from firemd.outputs import write_markdown
from firemd.server import ServerError, ServerManager
from firemd.util import get_crawl_output_dir, get_output_dir, is_url, parse_url_file

# Create two apps - one for when URL is provided directly, one for subcommands
app = typer.Typer(
    name="firemd",
    help="Local Firecrawl → Markdown CLI. Convert URLs to Markdown using a locally running Firecrawl instance.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"firemd version {__version__}")
        raise typer.Exit()


# Server subcommand group
server_app = typer.Typer(help="Manage the local Firecrawl server.")
app.add_typer(server_app, name="server")


@app.command()
def proxy(
    url: Optional[str] = typer.Argument(
        None,
        help="Proxy URL (http://user:pass@host:port). Omit to show status.",
    ),
    clear: bool = typer.Option(
        False, "--clear", help="Remove saved proxy configuration",
    ),
) -> None:
    """Configure or check proxy for Firecrawl.

    Examples:
      firemd proxy http://user:pass@proxy.example.com:8080
      firemd proxy                    # show current config
      firemd proxy --clear            # remove proxy
    """
    if clear:
        if clear_proxy_config():
            console.print("[green]Proxy config removed.[/green]")
            console.print(
                "[yellow]Restart the server to apply:[/yellow]"
            )
            console.print(
                "  firemd server install && firemd server up"
            )
        else:
            console.print("[dim]No proxy config to remove.[/dim]")
        return

    if url:
        # Set proxy
        try:
            parts = parse_proxy_url(url)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(2)

        env_file = save_proxy_url(url)
        console.print(f"[green]Proxy saved to {env_file}[/green]")
        console.print(f"  Host: {parts['host']}")
        if parts["port"]:
            console.print(f"  Port: {parts['port']}")
        if parts["username"]:
            console.print(f"  Username: {parts['username']}")
        if parts["password"]:
            masked = "*" * len(parts["password"])
            console.print(f"  Password: {masked}")
        console.print()
        console.print("[yellow]Restart the server to apply:[/yellow]")
        console.print(
            "  firemd server install && firemd server up"
        )
        return

    # Show status
    saved = load_proxy_url()
    if not saved:
        console.print("[dim]No proxy configured.[/dim]")
        console.print(
            "[dim]Usage: firemd proxy http://user:pass@host:port[/dim]"
        )
        return

    try:
        parts = parse_proxy_url(saved)
    except ValueError:
        console.print(f"[yellow]Stored URL:[/yellow] {saved}")
        console.print("[yellow]  (could not parse)[/yellow]")
        return

    table = Table(title="Proxy Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    table.add_row("Host", parts["host"])
    table.add_row("Port", parts["port"] or "[dim](default)[/dim]")
    table.add_row(
        "Username",
        parts["username"] or "[dim](not set)[/dim]",
    )
    pw = parts["password"]
    table.add_row(
        "Password",
        ("*" * len(pw)) if pw else "[dim](not set)[/dim]",
    )
    console.print(table)


@server_app.command("install")
def server_install(
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
) -> None:
    """Install/provision Firecrawl locally (clone repo, configure)."""
    try:
        manager = ServerManager(api_url=api_url)
        manager.install(force=force)
    except ServerError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)


@server_app.command("up")
def server_up(
    build: bool = typer.Option(True, "--build/--no-build", help="Build images before starting"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
) -> None:
    """Start the Firecrawl server."""
    try:
        manager = ServerManager(api_url=api_url)
        manager.up(build=build)
    except ServerError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)


@server_app.command("stop")
def server_stop(
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
) -> None:
    """Stop the Firecrawl server (containers remain for fast restart)."""
    try:
        manager = ServerManager(api_url=api_url)
        manager.stop()
    except ServerError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)


@server_app.command("down")
def server_down(
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Also remove volumes"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
) -> None:
    """Stop and remove Firecrawl containers."""
    try:
        manager = ServerManager(api_url=api_url)
        manager.down(remove_volumes=volumes)
    except ServerError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)


@server_app.command("status")
def server_status(
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
) -> None:
    """Show Firecrawl server status."""
    manager = ServerManager(api_url=api_url)
    status = manager.status()

    table = Table(title="Firecrawl Server Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    def status_icon(ok: bool) -> str:
        return "[green]✓[/green]" if ok else "[red]✗[/red]"

    table.add_row("Installed", status_icon(status.installed))
    table.add_row("Containers exist", status_icon(status.containers_exist))
    table.add_row("Containers running", status_icon(status.containers_running))
    table.add_row("API reachable", status_icon(status.api_reachable))
    table.add_row("API URL", status.api_url)

    console.print(table)

    if status.is_ready:
        console.print("\n[green]Server is ready![/green]")
    elif status.installed:
        console.print("\n[yellow]Server installed but not running. Use 'firemd server up' to start.[/yellow]")
    else:
        console.print("\n[yellow]Server not installed. Use 'firemd server install' first.[/yellow]")


@server_app.command("logs")
def server_logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    tail: int = typer.Option(None, "--tail", "-n", help="Number of lines to show"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
) -> None:
    """Show Firecrawl server logs."""
    try:
        manager = ServerManager(api_url=api_url)
        manager.logs(follow=follow, tail=tail)
    except ServerError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(2)


@server_app.command("doctor")
def server_doctor(
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
) -> None:
    """Run diagnostics on the Firecrawl server setup."""
    import shutil
    import socket
    import subprocess
    from urllib.parse import urlparse

    from firemd.config import DEFAULT_API_PORT, get_firecrawl_dir

    console.print("[bold]Running firemd diagnostics...[/bold]\n")
    all_ok = True

    # Check 1: Docker installed
    docker_path = shutil.which("docker")
    if docker_path:
        console.print("[green]✓[/green] Docker found: " + docker_path)
    else:
        console.print("[red]✗[/red] Docker not found in PATH")
        console.print("  [dim]Install Docker: https://docs.docker.com/get-docker/[/dim]")
        all_ok = False

    # Check 2: Docker daemon running
    if docker_path:
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                console.print("[green]✓[/green] Docker daemon is running")
            else:
                console.print("[red]✗[/red] Docker daemon not running")
                console.print("  [dim]Start Docker or OrbStack[/dim]")
                all_ok = False
        except subprocess.TimeoutExpired:
            console.print("[red]✗[/red] Docker daemon check timed out")
            all_ok = False
        except Exception as e:
            console.print(f"[red]✗[/red] Docker check failed: {e}")
            all_ok = False

    # Check 3: Docker Compose version
    if docker_path:
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version_line = result.stdout.strip()
                console.print(f"[green]✓[/green] Docker Compose: {version_line}")
            else:
                console.print("[yellow]![/yellow] Docker Compose v2 not available")
                console.print("  [dim]firemd requires 'docker compose' (v2)[/dim]")
                all_ok = False
        except Exception:
            console.print("[yellow]![/yellow] Could not check Docker Compose version")
            all_ok = False

    # Check 4: Git installed
    git_path = shutil.which("git")
    if git_path:
        console.print("[green]✓[/green] Git found: " + git_path)
    else:
        console.print("[red]✗[/red] Git not found in PATH")
        console.print("  [dim]Git is needed for 'firemd server install'[/dim]")
        all_ok = False

    # Check 5: Firecrawl installation
    firecrawl_dir = get_firecrawl_dir()
    if firecrawl_dir.exists():
        console.print(f"[green]✓[/green] Firecrawl installed: {firecrawl_dir}")

        # Check .env exists
        env_file = firecrawl_dir / ".env"
        if env_file.exists():
            console.print("[green]✓[/green] Configuration file (.env) exists")
        else:
            console.print("[yellow]![/yellow] Configuration file (.env) missing")
            console.print("  [dim]Run 'firemd server install' to create it[/dim]")
    else:
        console.print("[yellow]![/yellow] Firecrawl not installed")
        console.print(f"  [dim]Run 'firemd server install' to set up at {firecrawl_dir}[/dim]")

    # Check 6: Port availability
    parsed = urlparse(api_url)
    port = parsed.port or DEFAULT_API_PORT
    host = parsed.hostname or "127.0.0.1"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            # Port is in use - check if it's Firecrawl
            manager = ServerManager(api_url=api_url)
            if manager._check_api_health():
                console.print(f"[green]✓[/green] Firecrawl API responding on port {port}")
            else:
                console.print(f"[yellow]![/yellow] Port {port} is in use but not by Firecrawl")
                console.print("  [dim]Another service may be using this port[/dim]")
        else:
            console.print(f"[dim]○[/dim] Port {port} is available (server not running)")
    except socket.error as e:
        console.print(f"[yellow]![/yellow] Could not check port {port}: {e}")
    finally:
        sock.close()

    # Summary
    console.print()
    if all_ok:
        console.print("[green]All checks passed![/green]")
    else:
        console.print("[yellow]Some issues found. See above for details.[/yellow]")


def scrape_single_url(
    url: str,
    output_dir: Path,
    front_matter: bool,
    verbose: bool,
    client: FirecrawlClient,
) -> bool:
    """Scrape a single URL.

    Returns:
        True if successful, False otherwise
    """
    console.print(f"[cyan]Scraping:[/cyan] {url}")

    result = client.scrape_url(url)

    if not result.success:
        console.print(f"[red]Failed:[/red] {result.error}")
        return False

    filepath = write_markdown(output_dir, result, front_matter=front_matter)
    console.print(f"[green]✓ Saved:[/green] {filepath}")

    if verbose and result.title:
        console.print(f"  [dim]Title: {result.title}[/dim]")

    return True


def do_scrape(
    input_: str,
    out: Optional[str],
    front_matter: bool,
    verbose: bool,
    api_url: str,
    overwrite: bool,
    server: str,
    lifecycle: str,
    batch_mode: bool,
    delay: float,
    max_retries: int,
    max_backoff: float,
) -> None:
    """Execute the scrape operation."""
    import time

    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

    # Determine if input is URL or file
    if is_url(input_):
        urls = [input_]
        is_multi = False
    else:
        # It's a file path
        input_path = Path(input_)
        if not input_path.exists():
            console.print(f"[red]Error:[/red] File not found: {input_}")
            raise typer.Exit(2)
        urls = parse_url_file(input_path)
        is_multi = True
        if not urls:
            console.print(f"[red]Error:[/red] No URLs found in {input_}")
            raise typer.Exit(2)

    # Determine output directory
    output_dir = get_output_dir(input_, out)

    if verbose:
        console.print(f"[dim]Output directory: {output_dir}[/dim]")
        console.print(f"[dim]URLs to process: {len(urls)}[/dim]")

    # Handle server lifecycle
    manager = ServerManager(api_url=api_url)
    we_started_server = False

    try:
        if server == "never":
            # Require server to be running
            status = manager.status()
            if not status.api_reachable:
                console.print("[red]Error:[/red] Server not reachable and --server=never specified")
                raise typer.Exit(2)
        else:
            # auto or always - ensure server is running
            try:
                we_started_server = manager.ensure()
            except ServerError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(2)

        # Create client and scrape
        success_count = 0
        fail_count = 0
        permanent_fail_count = 0

        # Set up paths
        manifest_path = output_dir / "manifest.jsonl"
        errors_path = output_dir / "errors.jsonl"

        with FirecrawlClient(api_url=api_url) as client:
            if is_multi:
                # Load existing manifest for resume (default behavior)
                existing_manifest = {}
                if not overwrite and manifest_path.exists():
                    existing_manifest = load_manifest(manifest_path)
                    if verbose:
                        console.print(f"[dim]Loaded {len(existing_manifest)} existing entries from manifest[/dim]")

                # Filter URLs unless overwriting - only skip successful (2xx) entries
                if not overwrite:
                    urls_to_process = [
                        u for u in urls
                        if u not in existing_manifest
                        or existing_manifest[u].status != "ok"
                        or not is_success(existing_manifest[u].http_status)
                    ]
                    skipped = len(urls) - len(urls_to_process)
                    if skipped > 0:
                        console.print(f"[dim]Skipping {skipped} already processed URLs (use --overwrite to re-scrape)[/dim]")
                    urls = urls_to_process

                if not urls:
                    console.print("[green]All URLs already processed![/green]")
                    raise typer.Exit(0)

                # Create URL to index mapping for consistent file naming
                url_to_index = {url: i + 1 for i, url in enumerate(urls)}

                if batch_mode:
                    # Old batch mode (for users with proxy infrastructure)
                    success_count, fail_count = _do_batch_scrape(
                        client=client,
                        urls=urls,
                        output_dir=output_dir,
                        manifest_path=manifest_path,
                        front_matter=front_matter,
                        url_to_index=url_to_index,
                    )
                else:
                    # Sequential mode (default) - with retry logic
                    retryable_failures: list[tuple[str, int]] = []  # (url, index)

                    total_retries = 0

                    def on_retry(url: str, attempt: int, status_code: int | None) -> None:
                        if verbose:
                            console.print(f"  [yellow]Retry {attempt}:[/yellow] {url} (HTTP {status_code})")

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Scraping...", total=len(urls))

                        for result, is_perm_error, retry_count in client.scrape_urls_sequential(
                            urls,
                            delay=delay,
                            max_retries=max_retries,
                            max_backoff=max_backoff,
                            on_retry=on_retry if verbose else None,
                        ):
                            total_retries += retry_count
                            url_index = url_to_index.get(result.url, success_count + fail_count + 1)

                            if result.success:
                                # Success - save markdown and manifest entry
                                filepath = write_markdown(
                                    output_dir,
                                    result,
                                    index=url_index,
                                    front_matter=front_matter,
                                )
                                success_count += 1
                                entry = ManifestEntry(
                                    url=result.url,
                                    file=filepath.name,
                                    status="ok",
                                    title=result.title,
                                    http_status=result.status_code,
                                )
                                save_manifest_entry(manifest_path, entry)
                            else:
                                # Failed
                                fail_count += 1
                                error_msg = result.error or f"HTTP {result.status_code}"
                                entry = ManifestEntry(
                                    url=result.url,
                                    file="",
                                    status="error",
                                    http_status=result.status_code,
                                    error=error_msg,
                                )
                                save_manifest_entry(manifest_path, entry)

                                if is_perm_error:
                                    # Permanent error - save to errors.jsonl immediately
                                    permanent_fail_count += 1
                                    save_error_entry(errors_path, entry)
                                    if verbose:
                                        console.print(f"  [red]Permanent error:[/red] {result.url} ({error_msg})")
                                else:
                                    # Retryable error - add to list for end-of-run retry
                                    retryable_failures.append((result.url, url_index))
                                    if verbose:
                                        console.print(f"  [yellow]Will retry:[/yellow] {result.url} ({error_msg})")

                            progress.update(task, advance=1)

                    # End-of-run retry for retryable failures
                    if retryable_failures:
                        console.print(f"\n[cyan]Retrying {len(retryable_failures)} failed URLs after 30s cooldown...[/cyan]")
                        time.sleep(30)

                        retry_success = 0
                        retry_fail = 0

                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            BarColumn(),
                            TaskProgressColumn(),
                            console=console,
                        ) as progress:
                            task = progress.add_task("Retrying...", total=len(retryable_failures))

                            retry_urls = [url for url, _ in retryable_failures]
                            retry_index_map = {url: idx for url, idx in retryable_failures}

                            for result, is_perm_error, retry_count in client.scrape_urls_sequential(
                                retry_urls,
                                delay=delay,
                                max_retries=max_retries,
                                max_backoff=max_backoff,
                                on_retry=on_retry if verbose else None,
                            ):
                                url_index = retry_index_map.get(result.url, 0)

                                if result.success:
                                    # Success on retry
                                    filepath = write_markdown(
                                        output_dir,
                                        result,
                                        index=url_index,
                                        front_matter=front_matter,
                                    )
                                    retry_success += 1
                                    success_count += 1
                                    fail_count -= 1  # Remove from fail count
                                    entry = ManifestEntry(
                                        url=result.url,
                                        file=filepath.name,
                                        status="ok",
                                        title=result.title,
                                        http_status=result.status_code,
                                    )
                                    save_manifest_entry(manifest_path, entry)
                                else:
                                    # Still failed - save to errors.jsonl
                                    retry_fail += 1
                                    error_msg = result.error or f"HTTP {result.status_code}"
                                    entry = ManifestEntry(
                                        url=result.url,
                                        file="",
                                        status="error",
                                        http_status=result.status_code,
                                        error=error_msg,
                                    )
                                    save_error_entry(errors_path, entry)

                                progress.update(task, advance=1)

                        console.print(f"[dim]Retry results: {retry_success} succeeded, {retry_fail} still failed[/dim]")

                    # Show retry stats if any retries happened
                    if verbose and total_retries > 0:
                        console.print(f"[dim]Total retries during scraping: {total_retries}[/dim]")

            else:
                # Single URL mode
                if scrape_single_url(urls[0], output_dir, front_matter, verbose, client):
                    success_count = 1
                else:
                    fail_count = 1

        # Print summary for multi-URL mode
        if is_multi:
            console.print()
            if permanent_fail_count > 0:
                console.print(f"[green]Completed:[/green] {success_count} succeeded, {fail_count} failed ({permanent_fail_count} permanent)")
            else:
                console.print(f"[green]Completed:[/green] {success_count} succeeded, {fail_count} failed")
            if fail_count > 0:
                console.print(f"[dim]Failed URLs saved to: {errors_path}[/dim]")

        # Determine exit code
        if fail_count > 0 and success_count == 0:
            exit_code = 2
        elif fail_count > 0:
            exit_code = 1
        else:
            exit_code = 0

    finally:
        # Handle server lifecycle
        if we_started_server and lifecycle != "keep" and server != "always":
            if lifecycle == "down":
                manager.down()
            else:  # stop (default)
                manager.stop()

    raise typer.Exit(exit_code)


def _do_batch_scrape(
    client: FirecrawlClient,
    urls: list[str],
    output_dir: Path,
    manifest_path: Path,
    front_matter: bool,
    url_to_index: dict[str, int],
) -> tuple[int, int]:
    """Execute batch scraping (old behavior).

    Returns:
        Tuple of (success_count, fail_count)
    """
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

    success_count = 0
    fail_count = 0

    try:
        job = client.batch_scrape(urls)
        console.print(f"[cyan]Started batch job:[/cyan] {job.job_id}")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Scraping...", total=job.total)

            for job_status, results in client.poll_batch(job.job_id):
                # Update progress
                progress.update(task, completed=job_status.completed)

                # Process new results
                for result in results:
                    url_index = url_to_index.get(result.url, success_count + fail_count + 1)

                    if result.success:
                        filepath = write_markdown(
                            output_dir,
                            result,
                            index=url_index,
                            front_matter=front_matter,
                        )
                        success_count += 1
                        entry = ManifestEntry(
                            url=result.url,
                            file=filepath.name,
                            status="ok",
                            title=result.title,
                            http_status=result.status_code,
                        )
                    else:
                        fail_count += 1
                        entry = ManifestEntry(
                            url=result.url,
                            file="",
                            status="error",
                            http_status=result.status_code,
                            error=result.error,
                        )

                    save_manifest_entry(manifest_path, entry)

    except FirecrawlError as e:
        console.print(f"[red]Batch scraping failed:[/red] {e}")
        raise typer.Exit(2)

    return success_count, fail_count


@app.callback()
def callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Convert URLs to Markdown using local Firecrawl."""
    pass


@app.command()
def scrape(
    input_: str = typer.Argument(..., metavar="INPUT", help="URL or path to file containing URLs"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output directory"),
    front_matter: bool = typer.Option(False, "--front-matter", help="Add YAML front matter"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
    overwrite: bool = typer.Option(False, "--overwrite", "-f", help="Re-scrape URLs even if already in manifest"),
    server: str = typer.Option(
        "auto",
        "--server",
        help="Server policy: auto (start if needed), never (require running), always (keep running after)",
    ),
    lifecycle: str = typer.Option(
        "stop",
        "--lifecycle",
        help="After scrape: stop (stop containers), down (remove containers), keep (leave running)",
    ),
    batch: bool = typer.Option(
        False,
        "--batch",
        help="Use batch mode (faster but may trigger rate limits)",
    ),
    delay: float = typer.Option(
        1.0,
        "--delay",
        help="Max delay in seconds between requests, actual is random 0 to delay (sequential mode only)",
    ),
    max_retries: int = typer.Option(
        5,
        "--max-retries",
        help="Maximum retry attempts for retryable errors (sequential mode only)",
    ),
    max_backoff: float = typer.Option(
        32.0,
        "--max-backoff",
        help="Maximum backoff delay in seconds (sequential mode only)",
    ),
) -> None:
    """Scrape URL(s) and convert to Markdown.

    INPUT can be a single URL or a path to a file containing URLs (one per line).

    By default, URLs are scraped sequentially with retry logic for rate limits.
    Use --batch for faster parallel scraping (requires proxy infrastructure).

    Examples:
      firemd scrape https://example.com
      firemd scrape urls.txt --front-matter
      firemd scrape urls.txt --delay 2.0 --max-retries 8
      firemd scrape urls.txt --batch  # old parallel mode
    """
    do_scrape(
        input_=input_,
        out=out,
        front_matter=front_matter,
        verbose=verbose,
        api_url=api_url,
        overwrite=overwrite,
        server=server,
        lifecycle=lifecycle,
        batch_mode=batch,
        delay=delay,
        max_retries=max_retries,
        max_backoff=max_backoff,
    )


def do_crawl(
    url: str,
    out: Optional[str],
    limit: int,
    max_depth: int,
    front_matter: bool,
    verbose: bool,
    api_url: str,
    overwrite: bool,
    server: str,
    lifecycle: str,
    wait: int,
    include: Optional[list[str]],
    exclude: Optional[list[str]],
    allow_external: bool,
    allow_subdomains: bool,
    allow_backward_links: bool,
    ignore_sitemap: bool,
    ignore_robots: bool,
    max_concurrency: int,
    delay: float,
    max_retries: int,
    max_backoff: float,
) -> None:
    """Execute the crawl operation."""
    # Determine output directory and create it immediately
    output_dir = get_crawl_output_dir(url, out)
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Output: {output_dir}[/dim]")
    if verbose:
        console.print(f"[dim]Crawl limit: {limit}, max depth: {max_depth}[/dim]")
        console.print(f"[dim]Concurrency: {max_concurrency}, delay: {delay}s[/dim]")

    # Handle server lifecycle
    manager = ServerManager(api_url=api_url)
    we_started_server = False

    try:
        if server == "never":
            status = manager.status()
            if not status.api_reachable:
                console.print(
                    "[red]Error:[/red] Server not reachable and --server=never specified"
                )
                raise typer.Exit(2)
        else:
            try:
                we_started_server = manager.ensure()
            except ServerError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(2)

        # Set up paths
        manifest_path = output_dir / "manifest.jsonl"
        errors_path = output_dir / "errors.jsonl"

        # Load existing manifest for resume
        existing_manifest = {}
        if not overwrite and manifest_path.exists():
            existing_manifest = load_manifest(manifest_path)
            if verbose:
                console.print(
                    f"[dim]Loaded {len(existing_manifest)} entries from manifest[/dim]"
                )

        success_count = 0
        fail_count = 0
        skipped_count = 0
        failed_urls: list[str] = []
        crawl_job: CrawlJob | None = None

        with FirecrawlClient(api_url=api_url) as client:
            try:
                # Start crawl
                crawl_job = client.start_crawl(
                    url,
                    limit=limit,
                    max_depth=max_depth,
                    include_paths=include,
                    exclude_paths=exclude,
                    allow_backward_links=allow_backward_links,
                    allow_external_links=allow_external,
                    allow_subdomains=allow_subdomains,
                    ignore_sitemap=ignore_sitemap,
                    ignore_robots_txt=ignore_robots,
                    wait_for=wait,
                    max_concurrency=max_concurrency,
                    delay=delay,
                )
                console.print(f"[cyan]Started crawl:[/cyan] {crawl_job.job_id}")

                client._ws_error = None
                with console.status("Crawling...") as status:
                    for job_status, results in client.stream_crawl(crawl_job.job_id):
                        if client._ws_error:
                            client._ws_error = None

                        # Update spinner with progress counts
                        total = job_status.total or "?"
                        status.update(
                            f"Crawling... {job_status.completed}/{total}"
                            f"  [green]{success_count} ok[/green]"
                            f"  [red]{fail_count} err[/red]"
                        )

                        for result in results:
                            # Skip already-processed URLs (resume)
                            if (
                                not overwrite
                                and result.url in existing_manifest
                                and existing_manifest[result.url].status == "ok"
                                and is_success(
                                    existing_manifest[result.url].http_status
                                )
                            ):
                                skipped_count += 1
                                continue

                            if result.success:
                                filepath = write_markdown(
                                    output_dir,
                                    result,
                                    index=None,
                                    front_matter=front_matter,
                                )
                                success_count += 1
                                entry = ManifestEntry(
                                    url=result.url,
                                    file=filepath.name,
                                    status="ok",
                                    title=result.title,
                                    http_status=result.status_code,
                                )
                                save_manifest_entry(manifest_path, entry)
                                console.print(
                                    f"  [green]OK:[/green] {result.url}"
                                )
                            else:
                                fail_count += 1
                                error_msg = (
                                    result.error or f"HTTP {result.status_code}"
                                )
                                entry = ManifestEntry(
                                    url=result.url,
                                    file="",
                                    status="error",
                                    http_status=result.status_code,
                                    error=error_msg,
                                )
                                save_manifest_entry(manifest_path, entry)
                                failed_urls.append(result.url)
                                console.print(
                                    f"  [red]Fail:[/red] {result.url}"
                                    f" ({error_msg})"
                                )

            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted![/yellow]")
                if crawl_job:
                    console.print("[dim]Cancelling crawl on server...[/dim]")
                    client.cancel_crawl(crawl_job.job_id)

            except FirecrawlError as e:
                console.print(f"[red]Crawl failed:[/red] {e}")
                raise typer.Exit(2)

            # Retry failed URLs sequentially
            if failed_urls and max_retries > 0:
                console.print(
                    f"\n[cyan]Retrying {len(failed_urls)} failed URLs"
                    f" sequentially...[/cyan]"
                )
                retry_success = 0

                def on_retry(u: str, attempt: int, sc: int | None) -> None:
                    console.print(
                        f"  [yellow]Retry {attempt}:[/yellow]"
                        f" {u} (HTTP {sc})"
                    )

                for result, _, _ in client.scrape_urls_sequential(
                    failed_urls,
                    delay=1.0,
                    max_retries=max_retries,
                    max_backoff=max_backoff,
                    on_retry=on_retry,
                ):
                    if result.success:
                        filepath = write_markdown(
                            output_dir,
                            result,
                            index=None,
                            front_matter=front_matter,
                        )
                        retry_success += 1
                        success_count += 1
                        fail_count -= 1
                        entry = ManifestEntry(
                            url=result.url,
                            file=filepath.name,
                            status="ok",
                            title=result.title,
                            http_status=result.status_code,
                        )
                        save_manifest_entry(manifest_path, entry)
                        console.print(
                            f"  [green]Retry OK:[/green] {result.url}"
                        )
                    else:
                        error_msg = (
                            result.error or f"HTTP {result.status_code}"
                        )
                        entry = ManifestEntry(
                            url=result.url,
                            file="",
                            status="error",
                            http_status=result.status_code,
                            error=error_msg,
                        )
                        save_error_entry(errors_path, entry)
                        console.print(
                            f"  [red]Still failed:[/red] {result.url}"
                            f" ({error_msg})"
                        )

                console.print(
                    f"[dim]Retry: {retry_success} recovered,"
                    f" {fail_count} still failed[/dim]"
                )

        # Print summary
        console.print()
        parts = [f"{success_count} saved"]
        if fail_count > 0:
            parts.append(f"{fail_count} failed")
        if skipped_count > 0:
            parts.append(f"{skipped_count} skipped (resume)")
        console.print(f"[green]Completed:[/green] {', '.join(parts)}")
        console.print(f"[dim]Output: {output_dir}[/dim]")
        if fail_count > 0:
            console.print(f"[dim]Errors: {errors_path}[/dim]")

        # Exit code
        if fail_count > 0 and success_count == 0:
            exit_code = 2
        elif fail_count > 0:
            exit_code = 1
        else:
            exit_code = 0

    finally:
        if we_started_server and lifecycle != "keep" and server != "always":
            if lifecycle == "down":
                manager.down()
            else:
                manager.stop()

    raise typer.Exit(exit_code)


@app.command()
def crawl(
    url: str = typer.Argument(..., help="Starting URL to crawl"),
    out: Optional[str] = typer.Option(
        None, "--out", "-o", help="Output directory (default: domain)"
    ),
    limit: int = typer.Option(1000, "--limit", "-l", help="Maximum pages to crawl"),
    max_depth: int = typer.Option(10, "--max-depth", "-d", help="Maximum link depth"),
    entire_domain: bool = typer.Option(
        False, "--entire-domain",
        help="Crawl entire domain (sets allow-backward-links + allow-subdomains)",
    ),
    front_matter: bool = typer.Option(False, "--front-matter", help="Add YAML front matter"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--api", help="API URL"),
    overwrite: bool = typer.Option(
        False, "--overwrite", "-f", help="Re-save pages already in manifest"
    ),
    server: str = typer.Option(
        "auto", "--server",
        help="Server policy: auto, never, always",
    ),
    lifecycle: str = typer.Option(
        "stop", "--lifecycle",
        help="After crawl: stop (stop containers), down (remove containers), keep (leave running)",
    ),
    wait: int = typer.Option(0, "--wait", help="Milliseconds to wait for JS rendering"),
    include: Optional[list[str]] = typer.Option(
        None, "--include", help="URL path patterns to include (repeatable)"
    ),
    exclude: Optional[list[str]] = typer.Option(
        None, "--exclude", help="URL path patterns to exclude (repeatable)"
    ),
    allow_external: bool = typer.Option(False, "--allow-external", help="Follow external links"),
    allow_subdomains: bool = typer.Option(
        False, "--allow-subdomains", help="Follow subdomain links"
    ),
    ignore_sitemap: bool = typer.Option(False, "--ignore-sitemap", help="Skip sitemap discovery"),
    ignore_robots: bool = typer.Option(False, "--ignore-robots", help="Ignore robots.txt"),
    max_concurrency: int = typer.Option(
        1, "--concurrency", "-c", help="Max concurrent scrapes (default 1 to avoid 403s)",
    ),
    crawl_delay: float = typer.Option(
        0.5, "--delay", help="Seconds between scrapes on the server side",
    ),
    max_retries: int = typer.Option(
        3, "--max-retries", help="Retry attempts for failed URLs after crawl",
    ),
    max_backoff: float = typer.Option(
        32.0, "--max-backoff", help="Max backoff delay in seconds for retries",
    ),
) -> None:
    """Crawl a website starting from URL and save pages as Markdown.

    Follows links automatically up to --limit pages and --max-depth link depth.
    Uses WebSocket streaming when available, falls back to HTTP polling.
    Failed URLs are retried sequentially after the crawl finishes.

    Examples:
      firemd crawl https://docs.example.com --limit 50
      firemd crawl https://example.com --entire-domain --limit 500
      firemd crawl https://example.com --concurrency 3 --delay 1
      firemd crawl https://example.com --include "/docs/*" --exclude "/blog/*"
    """
    do_crawl(
        url=url,
        out=out,
        limit=limit,
        max_depth=max_depth,
        front_matter=front_matter,
        verbose=verbose,
        api_url=api_url,
        overwrite=overwrite,
        server=server,
        lifecycle=lifecycle,
        wait=wait,
        include=include,
        exclude=exclude,
        allow_external=allow_external,
        allow_subdomains=entire_domain or allow_subdomains,
        allow_backward_links=entire_domain,
        ignore_sitemap=ignore_sitemap,
        ignore_robots=ignore_robots,
        max_concurrency=max_concurrency,
        delay=crawl_delay,
        max_retries=max_retries,
        max_backoff=max_backoff,
    )


def main() -> None:
    """Main entry point that handles both direct URL input and subcommands."""
    # Check if first arg looks like a URL or file (not a subcommand or option)
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        # If it's not an option and not a known subcommand, treat as scrape input
        known = ("server", "scrape", "crawl", "proxy")
        if not first_arg.startswith("-") and first_arg not in known:
            # Insert 'scrape' command before the input
            sys.argv.insert(1, "scrape")

    app()


if __name__ == "__main__":
    main()
