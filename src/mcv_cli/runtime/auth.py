from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx

from .. import __version__
from ..api.core.constants import (
    BASE_URL,
    CHULA_LOGIN_URL,
    PLATFORM_LOGIN_URL,
    PUBLIC_AUTHORIZATION_URL,
    PUBLIC_CLIENT_ID,
    PUBLIC_REDIRECT_URI,
)
from ..api.core.errors import AuthenticationError, AuthenticationRequired
from .completion.state import activate, deactivate
from .config import Settings
from .errors import ConfigurationError
from .models import AuthProvider, StoredProfile
from .storage import CredentialStore

LoginField = Literal["name", "email"]
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MYCOURSEVILLE_HOSTS = {"mycourseville.com", "www.mycourseville.com"}


def build_public_authorization_url(provider: AuthProvider) -> str:
    params = {
        "response_type": "code",
        "client_id": PUBLIC_CLIENT_ID,
        "redirect_uri": PUBLIC_REDIRECT_URI,
    }
    if provider is AuthProvider.CHULA:
        params["login_page"] = "itchula"
    elif provider is AuthProvider.GOOGLE:
        params["login_page"] = "google"
    return str(httpx.URL(PUBLIC_AUTHORIZATION_URL, params=params))


@dataclass(frozen=True)
class LoginForm:
    action: str
    hidden_fields: dict[str, str]


class _LoginPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[LoginForm] = []
        self.oauth_links: list[str] = []
        self._form_action: str | None = None
        self._hidden_fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "form" and self._form_action is None:
            self._form_action = attributes.get("action", "")
            self._hidden_fields = {}
        elif tag.lower() == "input" and self._form_action is not None:
            if attributes.get("type", "text").lower() == "hidden":
                name = attributes.get("name", "")
                if name:
                    self._hidden_fields[name] = attributes.get("value", "")
        elif tag.lower() == "a" and "/api/oauth/authorize" in attributes.get("href", ""):
            self.oauth_links.append(attributes["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._form_action is not None:
            self.forms.append(LoginForm(self._form_action, dict(self._hidden_fields)))
            self._form_action = None
            self._hidden_fields = {}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def _diagnostic_text(value: object) -> str | None:
    if value is None:
        return None
    text = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, (dict, list))
        else str(value)
    )
    text = re.sub(
        r"(?i)((?:[\"']?(?:password|passwd|_?token|csrf|csrf_token|session|"
        r"client_secret|access_token|refresh_token|authorization|cookie)[\"']?\s*[:=]\s*"
        r"[\"']?))"
        r"[^,}\s\"']+",
        r"\1[redacted]",
        text,
    )
    text = " ".join(text.split())
    return text[:500] + ("..." if len(text) > 500 else "") if text else None


def _response_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        parser = _VisibleTextParser()
        parser.feed(response.text)
        return _diagnostic_text(" ".join(parser.parts))
    if isinstance(payload, dict):
        for key in ("error_description", "error", "message", "detail", "errors"):
            if key in payload and payload[key] not in (None, "", [], {}):
                return _diagnostic_text(payload[key])
        return None
    return _diagnostic_text(payload)


def _authentication_http_error(prefix: str, response: httpx.Response) -> AuthenticationError:
    reason = f" {response.reason_phrase}" if response.reason_phrase else ""
    message = f"{prefix} (HTTP {response.status_code}{reason})."
    detail = _response_detail(response)
    if detail:
        message = f"{message} Server message: {detail}"
    details: dict[str, object] = {
        "status_code": response.status_code,
        "endpoint": response.url.path,
    }
    if detail:
        details["server_message"] = detail
    return AuthenticationError(message, details=details)


class AuthManager:
    def __init__(
        self,
        *,
        store: CredentialStore | None = None,
        settings: Settings | None = None,
        output: Callable[[str], None] = print,
    ) -> None:
        self.settings = settings or Settings()
        self.store = store or CredentialStore(settings=self.settings)
        self.output = output

    def profile(self) -> StoredProfile | None:
        return self.store.load()

    def login(
        self,
        provider: AuthProvider,
        *,
        username: str,
        password: str,
        login_field: LoginField = "name",
    ) -> StoredProfile:
        selected = provider
        if selected is AuthProvider.GOOGLE:
            raise ConfigurationError(
                "Google login is not supported by the cookie-login MVP. "
                "It requires a browser OAuth flow and an approved MyCourseVille client."
            )
        if selected is AuthProvider.CHULA and login_field != "name":
            raise ConfigurationError("--email is only supported with platform login.")
        if not username.strip():
            raise AuthenticationError("The MyCourseVille username cannot be empty.")
        if not password:
            raise AuthenticationError("The MyCourseVille password cannot be empty.")

        with httpx.Client(
            timeout=self.settings.timeout,
            follow_redirects=False,
            headers={
                "Accept": "text/html, application/json",
                "User-Agent": f"mcv-cli/{__version__}",
            },
        ) as client:
            form = self._load_login_form(client, selected)
            form_data = dict(form.hidden_fields)
            if selected is AuthProvider.CHULA:
                form_data.update({"username": username, "password": password})
            else:
                form_data.update(
                    {"loginfield": login_field, "name": username, "password": password}
                )
            response = client.post(
                form.action,
                data=form_data,
                follow_redirects=False,
                headers={"Accept": "text/html"},
            )
            if response.status_code >= 400:
                raise _authentication_http_error(
                    "MyCourseVille rejected the login request", response
                )
            if response.status_code == 200:
                redirector = self._find_session_redirect(response)
                if redirector is not None:
                    response = client.get(
                        redirector,
                        follow_redirects=False,
                        headers={"Accept": "text/html"},
                    )
            response = self._follow_internal_redirects(client, response)
            if response.status_code >= 400:
                raise _authentication_http_error(
                    "MyCourseVille rejected the login redirect", response
                )
            self._verify_session(client)
            cookies = self._collect_cookies(client)
        if "laravel_session" not in cookies:
            raise AuthenticationError(
                "MyCourseVille did not return an authenticated session cookie."
            )
        profile = StoredProfile(provider=selected, cookies=cookies)
        self.store.save(profile)
        self._activate_completion(profile)
        return profile

    def check_session(self) -> None:
        cookies = self.get_session_cookies()
        try:
            with httpx.Client(
                timeout=self.settings.timeout,
                follow_redirects=False,
                headers={"Accept": "text/html", "User-Agent": f"mcv-cli/{__version__}"},
                cookies=cookies,
            ) as client:
                self._verify_session(client)
        except httpx.HTTPError as exc:
            raise AuthenticationError("The MyCourseVille session check failed.") from exc
        profile = self.store.load()
        if profile is not None:
            self._activate_completion(profile)

    def get_session_cookies(self) -> dict[str, str]:
        profile = self.store.load()
        if profile is None or not profile.cookies:
            raise AuthenticationRequired()
        return dict(profile.cookies)

    def logout(self) -> None:
        profile = self.store.load()
        if profile is not None:
            self.store.delete()
        try:
            deactivate(self.settings.config_dir)
        except OSError:
            pass

    def _activate_completion(self, profile: StoredProfile) -> None:
        try:
            activate(
                profile_name=self.store.profile_name,
                provider=profile.provider.value,
                config_dir=self.settings.config_dir,
            )
        except OSError:
            # Authentication remains successful if the optional completion
            # marker cannot be written.
            pass

    def _load_login_form(self, client: httpx.Client, provider: AuthProvider) -> LoginForm:
        response = client.get(
            build_public_authorization_url(provider),
            follow_redirects=False,
            headers={"Accept": "text/html"},
        )
        response = self._follow_internal_redirects(client, response)
        if response.status_code >= 400:
            raise _authentication_http_error("MyCourseVille did not open its login page", response)
        parser = _LoginPageParser()
        parser.feed(response.text)
        expected_url = CHULA_LOGIN_URL if provider is AuthProvider.CHULA else PLATFORM_LOGIN_URL
        expected_path = urlparse(expected_url).path
        for form in parser.forms:
            action = urljoin(str(response.url), form.action)
            if urlparse(action).path == expected_path:
                return LoginForm(action, form.hidden_fields)
        raise AuthenticationError("MyCourseVille's login form changed or could not be found.")

    def _verify_session(self, client: httpx.Client) -> None:
        try:
            response = client.get(BASE_URL, follow_redirects=False, headers={"Accept": "text/html"})
        except httpx.HTTPError as exc:
            raise AuthenticationError("The MyCourseVille session check failed.") from exc
        response = self._follow_internal_redirects(client, response)
        if response.status_code in _REDIRECT_STATUSES or response.status_code == 401:
            raise _authentication_http_error(
                "MyCourseVille rejected the credentials or did not establish a session", response
            )
        if response.status_code >= 400:
            raise _authentication_http_error("MyCourseVille could not verify the login", response)
        if "logout" not in response.text.lower():
            raise AuthenticationError(
                "MyCourseVille did not establish an authenticated web session.",
                details={"endpoint": response.url.path},
            )

    def _find_session_redirect(self, response: httpx.Response) -> str | None:
        parser = _LoginPageParser()
        parser.feed(response.text)
        for href in parser.oauth_links:
            return self._safe_internal_url(response.url, href)
        return None

    def _follow_internal_redirects(
        self,
        client: httpx.Client,
        response: httpx.Response,
    ) -> httpx.Response:
        for _ in range(10):
            if response.status_code not in _REDIRECT_STATUSES:
                return response
            location = response.headers.get("location")
            if not location:
                raise AuthenticationError("MyCourseVille returned a redirect without a URL.")
            target = self._safe_internal_url(response.url, location)
            try:
                response = client.get(
                    target,
                    follow_redirects=False,
                    headers={"Accept": "text/html"},
                )
            except httpx.HTTPError as exc:
                raise AuthenticationError("The MyCourseVille login redirect failed.") from exc
        raise AuthenticationError("MyCourseVille returned too many login redirects.")

    @staticmethod
    def _safe_internal_url(current_url: httpx.URL, location: str) -> str:
        target = urljoin(str(current_url), location)
        parsed = urlparse(target)
        host = (parsed.hostname or "").lower()
        if host not in _MYCOURSEVILLE_HOSTS:
            raise AuthenticationError(
                "MyCourseVille login redirected to an unexpected external host."
            )
        if parsed.scheme != "https":
            target = parsed._replace(scheme="https").geturl()
        return target

    @staticmethod
    def _collect_cookies(client: httpx.Client) -> dict[str, str]:
        cookies: dict[str, str] = {}
        for cookie in client.cookies.jar:
            domain = (cookie.domain or "").lstrip(".").lower()
            if (
                not domain or domain == "mycourseville.com" or domain.endswith(".mycourseville.com")
            ) and cookie.value is not None:
                cookies[cookie.name] = cookie.value
        return cookies
