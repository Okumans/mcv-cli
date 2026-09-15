from __future__ import annotations

import sys

import typer

from ...runtime.models import AuthLoginPayload, AuthProvider, AuthStatusPayload, LogoutPayload
from ..context import make_manager, run
from ..errors import UsageError


def register(app: typer.Typer) -> None:
    app.command("login")(login)
    app.command("status")(status)
    app.command("logout")(logout)


def login(
    ctx: typer.Context,
    provider: AuthProvider = typer.Option(
        ..., "--type", case_sensitive=False, help="Account provider to use for login."
    ),
    username: str | None = typer.Option(None, "--username", "-u"),
    email: bool = typer.Option(
        False, "--email", help="Treat the platform login value as an email address."
    ),
    password_stdin: bool = typer.Option(
        False,
        "--password-stdin",
        help="Read the password from stdin without echoing it (for automation).",
    ),
) -> None:
    def action() -> AuthLoginPayload:
        selected = provider
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
        if password_stdin:
            password_value = sys.stdin.readline().rstrip("\r\n")
            if not password_value:
                raise UsageError("--password-stdin received an empty password.")
        else:
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
    def action() -> AuthStatusPayload:
        manager = make_manager()
        profile = manager.profile()
        if profile is None or not profile.cookies:
            return {"authenticated": False}
        try:
            manager.check_session()
        except Exception as error:
            from mcv_api.core.errors import APIError

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
    def action() -> LogoutPayload:
        make_manager().logout()
        return {"logged_out": True}

    run(ctx, action)
