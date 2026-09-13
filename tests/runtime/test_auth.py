from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from mcv_cli.api.core.constants import (
    BASE_URL,
    CHULA_LOGIN_URL,
    PLATFORM_LOGIN_URL,
    PUBLIC_AUTHORIZATION_URL,
)
from mcv_cli.api.core.errors import AuthenticationError
from mcv_cli.runtime.auth import AuthManager, build_public_authorization_url
from mcv_cli.runtime.errors import ConfigurationError
from mcv_cli.runtime.models import AuthProvider


def _form_page(action: str, token: str, field: str) -> str:
    return f"""
    <html><body>
      <form method="POST" action="{action}">
        <input type="hidden" name="_token" value="{token}">
        <input type="{field}" name="{field}">
        <input type="password" name="password">
      </form>
    </body></html>
    """


def test_public_authorization_url_uses_the_site_client_and_provider_hint() -> None:
    platform_query = parse_qs(urlparse(build_public_authorization_url(AuthProvider.PLATFORM)).query)
    chula_query = parse_qs(urlparse(build_public_authorization_url(AuthProvider.CHULA)).query)

    assert platform_query["client_id"] == ["mycourseville.com"]
    assert platform_query["redirect_uri"] == [BASE_URL]
    assert "login_page" not in platform_query
    assert chula_query["login_page"] == ["itchula"]


@respx.mock
def test_chula_login_posts_credentials_and_persists_session(file_store) -> None:
    authorize = respx.get(PUBLIC_AUTHORIZATION_URL).mock(
        return_value=httpx.Response(302, headers={"location": CHULA_LOGIN_URL})
    )
    respx.get(CHULA_LOGIN_URL).mock(
        return_value=httpx.Response(
            200,
            text=_form_page(CHULA_LOGIN_URL, "chula-csrf", "username"),
            headers={"set-cookie": "laravel_session=initial; Path=/"},
        )
    )
    login = respx.post(CHULA_LOGIN_URL).mock(
        return_value=httpx.Response(
            302,
            headers={
                "location": BASE_URL,
                "set-cookie": "SESS_example=session-key; Path=/",
            },
        )
    )
    respx.get(f"{BASE_URL}/").mock(return_value=httpx.Response(200, text="logout"))

    manager = AuthManager(store=file_store, settings=file_store.settings)
    profile = manager.login(
        AuthProvider.CHULA,
        username="2300000000",
        password="secret-password",
    )

    assert authorize.called
    body = parse_qs(login.calls[0].request.content.decode("utf-8"))
    assert body["_token"] == ["chula-csrf"]
    assert body["username"] == ["2300000000"]
    assert body["password"] == ["secret-password"]
    assert profile.provider is AuthProvider.CHULA
    assert profile.cookies == {
        "laravel_session": "initial",
        "SESS_example": "session-key",
    }
    assert file_store.load() == profile


@respx.mock
def test_platform_login_can_use_email_field(file_store) -> None:
    respx.get(PUBLIC_AUTHORIZATION_URL).mock(
        return_value=httpx.Response(302, headers={"location": PLATFORM_LOGIN_URL})
    )
    respx.get(PLATFORM_LOGIN_URL).mock(
        return_value=httpx.Response(
            200,
            text=_form_page(PLATFORM_LOGIN_URL, "platform-csrf", "name"),
            headers={"set-cookie": "laravel_session=initial; Path=/"},
        )
    )
    login = respx.post(PLATFORM_LOGIN_URL).mock(
        return_value=httpx.Response(
            302,
            headers={
                "location": BASE_URL,
                "set-cookie": "SESS_platform=session-key; Path=/",
            },
        )
    )
    respx.get(f"{BASE_URL}/").mock(return_value=httpx.Response(200, text="logout"))

    manager = AuthManager(store=file_store, settings=file_store.settings)
    manager.login(
        AuthProvider.PLATFORM,
        username="student@example.com",
        password="secret-password",
        login_field="email",
    )

    body = parse_qs(login.calls[0].request.content.decode("utf-8"))
    assert body["loginfield"] == ["email"]
    assert body["name"] == ["student@example.com"]


@respx.mock
def test_login_rejects_invalid_session(file_store) -> None:
    respx.get(PUBLIC_AUTHORIZATION_URL).mock(
        return_value=httpx.Response(302, headers={"location": CHULA_LOGIN_URL})
    )
    respx.get(CHULA_LOGIN_URL).mock(
        return_value=httpx.Response(
            200,
            text=_form_page(CHULA_LOGIN_URL, "chula-csrf", "username"),
        )
    )
    respx.post(CHULA_LOGIN_URL).mock(
        return_value=httpx.Response(302, headers={"location": f"{BASE_URL}/chulalogin"})
    )
    respx.get(f"{BASE_URL}/chulalogin").mock(return_value=httpx.Response(200, text="error"))
    respx.get(f"{BASE_URL}/").mock(return_value=httpx.Response(200, text="login"))

    manager = AuthManager(store=file_store, settings=file_store.settings)
    with pytest.raises(AuthenticationError, match="did not establish"):
        manager.login(AuthProvider.CHULA, username="bad", password="bad")

    assert file_store.load() is None


@respx.mock
def test_login_surfaces_server_message_for_bad_request(file_store) -> None:
    respx.get(PUBLIC_AUTHORIZATION_URL).mock(
        return_value=httpx.Response(302, headers={"location": CHULA_LOGIN_URL})
    )
    respx.get(CHULA_LOGIN_URL).mock(
        return_value=httpx.Response(
            200,
            text=_form_page(CHULA_LOGIN_URL, "chula-csrf", "username"),
        )
    )
    respx.post(CHULA_LOGIN_URL).mock(
        return_value=httpx.Response(
            400,
            json={"message": "The login form token is invalid."},
        )
    )

    manager = AuthManager(store=file_store, settings=file_store.settings)
    with pytest.raises(AuthenticationError, match="The login form token is invalid") as caught:
        manager.login(AuthProvider.CHULA, username="user", password="password")

    assert caught.value.details == {
        "status_code": 400,
        "endpoint": "/api/chulalogin",
        "server_message": "The login form token is invalid.",
    }


def test_google_login_requires_oauth_registration(file_store) -> None:
    manager = AuthManager(store=file_store, settings=file_store.settings)

    with pytest.raises(ConfigurationError, match="Google login"):
        manager.login(AuthProvider.GOOGLE, username="ignored", password="ignored")


def test_logout_deletes_the_stored_profile(file_store, profile) -> None:
    file_store.save(profile)
    manager = AuthManager(store=file_store, settings=file_store.settings)

    manager.logout()

    assert file_store.load() is None
    assert not file_store.file_path.exists()
