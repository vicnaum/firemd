"""Server management for the local Firecrawl instance."""

from __future__ import annotations

import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

import httpx
from rich.console import Console

from firemd.config import (
    DEFAULT_API_URL,
    FIRECRAWL_REPO_URL,
    HEALTH_ENDPOINT,
    get_default_env_content,
    get_firecrawl_dir,
    get_state_dir,
)

console = Console()


@dataclass
class ServerStatus:
    """Status of the Firecrawl server."""

    installed: bool
    containers_exist: bool
    containers_running: bool
    api_reachable: bool
    api_url: str

    @property
    def is_ready(self) -> bool:
        """Check if server is ready to accept requests."""
        return self.api_reachable


class ServerError(Exception):
    """Error related to server operations."""

    pass


class ServerManager:
    """Manages the local Firecrawl server lifecycle."""

    def __init__(self, api_url: str = DEFAULT_API_URL) -> None:
        self.api_url = api_url
        self.state_dir = get_state_dir()
        self.firecrawl_dir = get_firecrawl_dir()

    def _run_compose(
        self,
        *args: str,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a docker compose command in the Firecrawl directory."""
        # Prefer explicit env file to avoid noisy "variable not set" warnings from Compose.
        env_file = self.firecrawl_dir / ".env"
        cmd = ["docker", "compose"]
        if env_file.exists():
            cmd.extend(["--env-file", ".env"])
        cmd.extend(args)
        try:
            result = subprocess.run(
                cmd,
                cwd=self.firecrawl_dir,
                capture_output=capture,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            raise ServerError(f"Docker compose command failed: {' '.join(cmd)}\n{e.stderr or ''}")
        except FileNotFoundError:
            raise ServerError(
                "Docker not found. Please install Docker or OrbStack first.\n"
                "See: https://docs.docker.com/get-docker/"
            )

    def _check_docker(self) -> bool:
        """Check if Docker is available and running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _check_api_health(self) -> bool:
        """Check if the Firecrawl API is responding."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.api_url}{HEALTH_ENDPOINT}")
                return response.status_code == 200
        except httpx.RequestError:
            return False

    def _get_container_status(self) -> tuple[bool, bool]:
        """Check if containers exist and are running.

        Returns:
            Tuple of (containers_exist, containers_running)
        """
        if not self.firecrawl_dir.exists():
            return False, False

        try:
            result = self._run_compose("ps", "--format", "{{.State}}", capture=True, check=False)
            output = result.stdout.strip()
            if not output:
                return False, False

            states = output.split("\n")
            containers_exist = len(states) > 0
            containers_running = all(s == "running" for s in states if s)
            return containers_exist, containers_running
        except ServerError:
            return False, False

    def status(self) -> ServerStatus:
        """Get the current server status."""
        installed = self.firecrawl_dir.exists() and (self.firecrawl_dir / ".env").exists()
        containers_exist, containers_running = self._get_container_status()
        api_reachable = self._check_api_health()

        return ServerStatus(
            installed=installed,
            containers_exist=containers_exist,
            containers_running=containers_running,
            api_reachable=api_reachable,
            api_url=self.api_url,
        )

    def install(self, force: bool = False) -> None:
        """Install Firecrawl by cloning the repository and configuring it.

        Args:
            force: If True, re-clone even if directory exists
        """
        # Note: We don't require Docker to be running for install - only for up

        # Create state directory
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Clone or update repository
        if self.firecrawl_dir.exists():
            if force:
                console.print(f"[yellow]Removing existing installation at {self.firecrawl_dir}[/yellow]")
                import shutil
                shutil.rmtree(self.firecrawl_dir)
            else:
                console.print(f"[dim]Firecrawl already installed at {self.firecrawl_dir}[/dim]")
                console.print("[dim]Use --force to reinstall[/dim]")
                # Update .env and override files anyway
                self._write_config_files()
                return

        console.print(f"[cyan]Cloning Firecrawl to {self.firecrawl_dir}...[/cyan]")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", FIRECRAWL_REPO_URL, str(self.firecrawl_dir)],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ServerError(f"Failed to clone Firecrawl repository: {e}")
        except FileNotFoundError:
            raise ServerError("Git not found. Please install git first.")

        self._write_config_files()
        console.print("[green]✓ Firecrawl installed successfully![/green]")

    def _write_config_files(self) -> None:
        """Write .env and docker-compose.override.yml files."""
        # Generate a random BULL_AUTH_KEY
        bull_auth_key = secrets.token_urlsafe(32)

        # Write .env file
        env_file = self.firecrawl_dir / ".env"
        env_content = get_default_env_content(bull_auth_key)
        env_content = self._ensure_compose_env_vars(env_content)
        env_file.write_text(env_content)
        console.print(f"[dim]Wrote {env_file}[/dim]")

        # Ensure we don't have a docker-compose.override.yml that *adds* an extra port mapping.
        # Docker Compose merges lists by appending, so an override that adds a ports entry would
        # result in two published 3002 bindings (0.0.0.0:3002 and 127.0.0.1:3002) -> "address already in use".
        override_file = self.firecrawl_dir / "docker-compose.override.yml"
        if override_file.exists():
            try:
                override_file.unlink()
                console.print(f"[dim]Removed {override_file} (avoid duplicate ports)[/dim]")
            except OSError:
                # Not fatal; compose will still work if the file isn't picked up / is empty.
                console.print(f"[yellow]Warning: could not remove {override_file}[/yellow]")

    def _ensure_compose_env_vars(self, env_content: str) -> str:
        """Ensure env_content defines all variables referenced by docker-compose.yaml.

        Docker Compose prints warnings when `${VAR}` is referenced but VAR is undefined.
        To keep UX clean, we define any missing variables as empty (`VAR=`).
        """
        compose_file = self.firecrawl_dir / "docker-compose.yaml"
        if not compose_file.exists():
            return env_content

        existing_keys: set[str] = set()
        for line in env_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            if key:
                existing_keys.add(key)

        text = compose_file.read_text(encoding="utf-8", errors="ignore")
        # Capture variable names from ${VAR}, ${VAR:-default}, ${VAR-default}, etc.
        vars_found = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", text))

        missing = sorted(v for v in vars_found if v not in existing_keys)
        if not missing:
            return env_content

        # Append missing vars at the end so user can edit above without losing order.
        lines = [env_content.rstrip(), "", "# Added by firemd to silence docker compose warnings"]
        lines.extend([f"{k}=" for k in missing])
        lines.append("")
        return "\n".join(lines)

    def up(self, build: bool = True) -> None:
        """Start the Firecrawl server.

        Args:
            build: If True, build images before starting
        """
        if not self.firecrawl_dir.exists():
            raise ServerError(
                "Firecrawl not installed. Run 'firemd server install' first."
            )

        console.print("[cyan]Starting Firecrawl server...[/cyan]")
        args = ["up", "-d"]
        if build:
            args.append("--build")

        self._run_compose(*args)
        console.print("[green]✓ Server started[/green]")

    def stop(self) -> None:
        """Stop the Firecrawl server (keeps containers)."""
        if not self.firecrawl_dir.exists():
            console.print("[yellow]Firecrawl not installed[/yellow]")
            return

        console.print("[cyan]Stopping Firecrawl server...[/cyan]")
        self._run_compose("stop")
        console.print("[green]✓ Server stopped[/green]")

    def down(self, remove_volumes: bool = False) -> None:
        """Stop and remove Firecrawl containers.

        Args:
            remove_volumes: If True, also remove volumes
        """
        if not self.firecrawl_dir.exists():
            console.print("[yellow]Firecrawl not installed[/yellow]")
            return

        console.print("[cyan]Stopping and removing Firecrawl containers...[/cyan]")
        args = ["down"]
        if remove_volumes:
            args.append("-v")
        self._run_compose(*args)
        console.print("[green]✓ Containers removed[/green]")

    def logs(self, follow: bool = False, tail: int | None = None) -> None:
        """Show server logs.

        Args:
            follow: If True, follow log output
            tail: Number of lines to show from end
        """
        if not self.firecrawl_dir.exists():
            raise ServerError("Firecrawl not installed.")

        args = ["logs"]
        if follow:
            args.append("-f")
        if tail is not None:
            args.extend(["--tail", str(tail)])

        # Don't capture output - let it stream to terminal
        self._run_compose(*args, capture=False, check=False)

    def wait_ready(self, timeout: float = 120.0, poll_interval: float = 2.0) -> bool:
        """Wait for the server to become ready.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between health checks

        Returns:
            True if server became ready, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._check_api_health():
                return True
            time.sleep(poll_interval)
        return False

    def ensure(
        self,
        timeout: float = 120.0,
    ) -> bool:
        """Ensure the server is running and ready.

        Starts the server if not running.

        Args:
            timeout: Maximum time to wait for readiness

        Returns:
            True if we started the server (caller should stop it later)
        """
        status = self.status()

        if status.api_reachable:
            return False  # Already running, we didn't start it

        if not status.installed:
            raise ServerError(
                "Firecrawl not installed. Run 'firemd server install' first."
            )

        # Start the server
        we_started = True
        if status.containers_exist and not status.containers_running:
            # Containers exist but stopped - just start them
            console.print("[cyan]Starting existing containers...[/cyan]")
            self._run_compose("start")
        else:
            # Need to bring up
            self.up(build=False)

        # Wait for readiness
        console.print("[dim]Waiting for Firecrawl to be ready...[/dim]")
        if not self.wait_ready(timeout=timeout):
            raise ServerError(
                f"Firecrawl did not become ready within {timeout}s. "
                "Check logs with 'firemd server logs'."
            )

        console.print("[green]✓ Firecrawl is ready[/green]")
        return we_started

