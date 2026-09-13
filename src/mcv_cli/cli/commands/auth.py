from __future__ import annotations

from typing import Any

import typer

from ...runtime.models import AuthProvider
from ..context import make_manager, run
from ..errors import UsageError


def register(app: typer.Typer) -> None:
    app.command("login")(login)
    app.command("status")(status)
    app.command("logout")(logout)


def login(
    ctx: typer.Context,
    provider: AuthProvider | None = typer.Option(None, "--type", case_sensitive=False),
    chula: bool = typer.Option(False, "--chula", help="Use the Chula account login page."),
    platform: bool = typer.Option(
        False, "--platform", help="Use a MyCourseVille platform account login page."
    ),
    google: bool = typer.Option(False, "--google", help="Use the Google login page."),
    username: str | None = typer.Option(None, "--username", "-u"),
    email: bool = typer.Option(
        False, "--email", help="Treat the platform login value as an email address."
    ),
) -> None:
    def action() -> dict[str, Any]:
        aliases = sum((chula, platform, google))
        if aliases > 1:
            raise UsageError("Choose only one of --chula, --platform, or --google.")
        if aliases and provider is not None:
            raise UsageError("Do not combine --type with a login shortcut.")
        selected = (
            AuthProvider.CHULA
            if chula
            else AuthProvider.PLATFORM
            if platform
            else AuthProvider.GOOGLE
            if google
            else provider or AuthProvider.PLATFORM
        )
        if selected is AuthProvider.GOOGLE:
            raise UsageError(
                "Google login is unavailable without an approved MyCourseVille OAuth client. "
                "Use --type chula or --type platform for the credential-based MVP."
            )
        if email and selected is AuthProvider.CHULA:
            raise UsageError("--email is only supported with platform login.")
        manager = make_manager()
        username_value = (
            username
            or manager.settings.username
            or typer.prompt(
                "Chula username" if selected is AuthProvider.CHULA else "MyCourseVille username"
            )
        )
        password_value = typer.prompt("MyCourseVille password", hide_input=True)
        profile = manager.login(
            selected,
            username=username_value,
            password=password_value,
            login_field="email" if email else "name",
        )
        return {"authenticated": True, "provider": profile.provider.value}

    run(ctx, action)


def status(ctx: typer.Context) -> None:
    def action() -> dict[str, Any]:
        manager = make_manager()
        profile = manager.profile()
        if profile is None or not profile.cookies:
            return {"authenticated": False}
        try:
            manager.check_session()
        except Exception as error:
            from ...api.core.errors import APIError

            if isinstance(error, APIError) and error.code in {
                "not_authenticated",
                "authentication_failed",
            }:
                return {
                    "authenticated": False,
                    "provider": profile.provider.value,
                    "session_expired": True,
                }
            raise
        return {"authenticated": True, "provider": profile.provider.value}

    run(ctx, action)


def logout(ctx: typer.Context) -> None:
    def action() -> dict[str, bool]:
        make_manager().logout()
        return {"logged_out": True}

    run(ctx, action)
