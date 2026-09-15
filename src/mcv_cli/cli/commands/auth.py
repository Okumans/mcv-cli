from __future__ import annotations

import sys

import typer

from ...runtime.models import AuthLoginPayload, AuthStatusPayload, LogoutPayload
from ..context import make_manager, run
from ..errors import UsageError


def register(app: typer.Typer) -> None:
    app.command("login")(login)
    app.command("status")(status)
    app.command("logout")(logout)


def login(
    ctx: typer.Context,
    username: str | None = typer.Option(None, "--username", "-u"),
    password_stdin: bool = typer.Option(
        False,
        "--password-stdin",
        help="Read the password from stdin without echoing it (for automation).",
    ),
) -> None:
    def action() -> AuthLoginPayload:
        manager = make_manager()
        username_value = (
            username
            or manager.settings.username
            or typer.prompt("Chula username")
        )
        if password_stdin:
            password_value = sys.stdin.readline().rstrip("\r\n")
            if not password_value:
                raise UsageError("--password-stdin received an empty password.")
        else:
            password_value = typer.prompt("MyCourseVille password", hide_input=True)
        manager.login(
            username=username_value,
            password=password_value,
        )
        return {"authenticated": True}

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
                    "session_expired": True,
                }
            raise
        return {"authenticated": True}

    run(ctx, action)


def logout(ctx: typer.Context) -> None:
    def action() -> LogoutPayload:
        make_manager().logout()
        return {"logged_out": True}

    run(ctx, action)
