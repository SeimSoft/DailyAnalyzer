"""Authentication and session token caching for Garmin Connect."""

from __future__ import annotations

import getpass
import os
from pathlib import Path

import typer
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from rich.console import Console

console = Console()

DEFAULT_TOKEN_DIR = Path.home() / ".garminconnect_tokens"


class GarminAuth:
    """Manages Garmin Connect login with persistent OAuth token storage."""

    def __init__(
        self,
        token_dir: Path | str | None = None,
        email: str | None = None,
        password: str | None = None,
    ):
        if token_dir:
            self.token_dir = Path(token_dir).expanduser().resolve()
        else:
            env_token_dir = os.getenv("GARMIN_TOKEN_DIR")
            self.token_dir = (
                Path(env_token_dir).expanduser().resolve() if env_token_dir else DEFAULT_TOKEN_DIR
            )

        self.email = email or os.getenv("GARMIN_EMAIL")
        self.password = password or os.getenv("GARMIN_PASSWORD")
        self.client: Garmin | None = None

    def has_cached_tokens(self) -> bool:
        """Checks if token files exist in the token directory."""
        if not self.token_dir.exists() or not self.token_dir.is_dir():
            return False
        # garth stores oauth1_token.json and oauth2_token.json
        token_files = list(self.token_dir.glob("*.json"))
        return len(token_files) > 0

    def login(self, force_reauth: bool = False) -> Garmin:
        """Logs into Garmin Connect, preferring cached tokens and prompting if necessary."""
        self.token_dir.mkdir(parents=True, exist_ok=True)
        tokenstore_str = str(self.token_dir)

        # 1. Try using cached tokens if available and not forcing reauth
        if self.has_cached_tokens() and not force_reauth:
            try:
                console.print(f"[dim]Loading cached session from: {self.token_dir}[/dim]")
                client = Garmin()
                client.login(tokenstore=tokenstore_str)
                self.client = client
                console.print(
                    f"[green]✓ Authenticated via token cache[/green] (User: [bold]{client.display_name}[/bold])"
                )
                return client
            except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError) as err:
                console.print(
                    f"[yellow]Cached session expired or invalid ({err}). Re-authenticating...[/yellow]"
                )
            except (GarminConnectConnectionError, OSError, ValueError, KeyError) as e:
                console.print(
                    f"[yellow]Session cache load failed ({e}). Re-authenticating...[/yellow]"
                )

        # 2. Prompt for credentials if missing
        email = self.email
        password = self.password

        if not email:
            email = typer.prompt("Garmin Connect Email")
        if not password:
            password = getpass.getpass("Garmin Connect Password: ")

        if not email or not password:
            raise GarminConnectAuthenticationError("Email and password are required to log in.")

        def prompt_mfa_callback() -> str:
            console.print(
                "[cyan]A Two-Factor Authentication (MFA) code was sent to your email or SMS.[/cyan]"
            )
            return typer.prompt("Enter Garmin MFA Code")

        try:
            client = Garmin(
                email=email,
                password=password,
                prompt_mfa=prompt_mfa_callback,
            )
            client.login(tokenstore=tokenstore_str)
            self.client = client
            console.print(
                f"[green]✓ Successfully logged in and tokens saved to {self.token_dir}[/green] "
                f"(User: [bold]{client.display_name}[/bold])"
            )
            return client
        except GarminConnectTooManyRequestsError:
            console.print(
                "[red]Error: Garmin rate limit hit (429 Too Many Requests). "
                "Please wait 10-15 minutes before attempting to log in again.[/red]"
            )
            raise
        except GarminConnectAuthenticationError as e:
            console.print(f"[red]Authentication failed: {e}[/red]")
            raise
        except GarminConnectConnectionError as e:
            console.print(f"[red]Network connection error: {e}[/red]")
            raise


def get_authenticated_client(
    token_dir: Path | None = None,
    email: str | None = None,
    password: str | None = None,
    force_reauth: bool = False,
) -> Garmin:
    """Initializes GarminAuth and returns authenticated Garmin client."""
    auth = GarminAuth(token_dir=token_dir, email=email, password=password)
    return auth.login(force_reauth=force_reauth)

