"""Tests for the runtime-settings SSRF allow-list (app/settings.py).

This is the highest-priority surface: a regression in normalize_base_url /
allowed_base_url_hosts is a security regression (it gates which hosts the
OpenAI-compatible backend will talk to).
"""

import pytest

from app import settings
from app.settings import (
    REASONING_EFFORTS,
    SettingsError,
    allowed_base_url_hosts,
    normalize_base_url,
    normalize_effort,
)


@pytest.fixture(autouse=True)
def _clear_allowlist_env(monkeypatch):
    """Start every test from a known allow-list: only the built-in defaults
    (localhost, 127.0.0.1, ::1, api.openai.com) plus the env-seeded base URL
    host. Tests opt extra hosts in explicitly."""
    monkeypatch.delenv("PROMPTGEN_ALLOWED_BASE_URL_HOSTS", raising=False)


# --- allowed_base_url_hosts -------------------------------------------------

def test_allowed_hosts_includes_builtin_defaults():
    hosts = allowed_base_url_hosts()
    assert {"localhost", "127.0.0.1", "::1", "api.openai.com"} <= hosts


def test_allowed_hosts_includes_seeded_base_url_host():
    # config.OPENAI_BASE_URL defaults to http://localhost:11434/v1, so its
    # host (localhost) is folded in.
    assert "localhost" in allowed_base_url_hosts()


def test_allowed_hosts_picks_up_env_extra_hosts(monkeypatch):
    monkeypatch.setenv(
        "PROMPTGEN_ALLOWED_BASE_URL_HOSTS",
        "https://my.endpoint.com:8443/v1, bare.example.com ,",
    )
    hosts = allowed_base_url_hosts()
    # Hosts are extracted from both full URLs and bare host[:port] strings,
    # lowercased, and blank entries are dropped.
    assert "my.endpoint.com" in hosts
    assert "bare.example.com" in hosts
    # The trailing empty entry after the last comma must not add "".
    assert "" not in hosts


def test_allowed_hosts_lowercases_env_hosts(monkeypatch):
    monkeypatch.setenv("PROMPTGEN_ALLOWED_BASE_URL_HOSTS", "API.Example.COM")
    assert "api.example.com" in allowed_base_url_hosts()


# --- normalize_base_url: accepted ------------------------------------------

def test_normalize_accepts_on_allowlist_default_host():
    assert normalize_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_normalize_accepts_localhost():
    assert normalize_base_url("http://localhost:11434/v1") == "http://localhost:11434/v1"


def test_normalize_accepts_env_added_host(monkeypatch):
    monkeypatch.setenv("PROMPTGEN_ALLOWED_BASE_URL_HOSTS", "my.endpoint.com")
    assert normalize_base_url("https://my.endpoint.com/v1") == "https://my.endpoint.com/v1"


def test_normalize_host_match_is_case_insensitive():
    # The host comparison lowercases, but the returned string preserves the
    # caller's original casing (only trailing slashes are stripped).
    assert normalize_base_url("https://API.OPENAI.COM/v1") == "https://API.OPENAI.COM/v1"


# --- normalize_base_url: trailing-slash + empty normalization --------------

def test_normalize_strips_trailing_slash():
    assert normalize_base_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"


def test_normalize_strips_multiple_trailing_slashes():
    assert normalize_base_url("https://api.openai.com/v1///") == "https://api.openai.com/v1"


@pytest.mark.parametrize("value", ["", "   ", "/", "///"])
def test_normalize_empty_returns_empty_string(value):
    # An empty (or slash-only) endpoint normalizes to "" without raising — the
    # backend treats "" as "no endpoint configured".
    assert normalize_base_url(value) == ""


# --- normalize_base_url: rejections ----------------------------------------

def test_normalize_rejects_off_allowlist_host():
    with pytest.raises(SettingsError):
        normalize_base_url("https://evil.example.com/v1")


def test_normalize_rejection_message_names_the_host():
    with pytest.raises(SettingsError, match="evil.example.com"):
        normalize_base_url("https://evil.example.com/v1")


@pytest.mark.parametrize(
    "value",
    [
        "ftp://api.openai.com/v1",
        "gopher://api.openai.com",
        "ws://api.openai.com",
    ],
)
def test_normalize_rejects_non_http_schemes(value):
    with pytest.raises(SettingsError):
        normalize_base_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "file:///etc/passwd",
        "http:///v1",  # scheme + path but no host/netloc
    ],
)
def test_normalize_rejects_missing_host(value):
    with pytest.raises(SettingsError):
        normalize_base_url(value)


def test_normalize_rejects_query_string():
    with pytest.raises(SettingsError, match="query string or fragment"):
        normalize_base_url("https://api.openai.com/v1?token=abc")


def test_normalize_rejects_fragment():
    with pytest.raises(SettingsError, match="query string or fragment"):
        normalize_base_url("https://api.openai.com/v1#section")


def test_normalize_off_allowlist_takes_precedence_only_after_scheme_check():
    # A non-http scheme is rejected regardless of host allow-listing.
    with pytest.raises(SettingsError):
        normalize_base_url("ftp://localhost/v1")


# --- normalize_effort: reasoning-effort selector ---------------------------

@pytest.mark.parametrize("value", REASONING_EFFORTS)
def test_normalize_effort_accepts_all_allowed_values(value):
    assert normalize_effort(value) == value


def test_normalize_effort_is_case_insensitive_and_trims():
    assert normalize_effort("  HIGH ") == "high"


@pytest.mark.parametrize("value", ["", "   ", "bogus", "off", "true", "1"])
def test_normalize_effort_falls_back_to_default(value):
    # A blank/unrecognized value (stale file or tampered request) coerces to
    # "default" rather than raising — the input is a constrained <select>.
    assert normalize_effort(value) == "default"


def test_reasoning_efforts_set_is_stable():
    # The settings dropdown (app/main.py REASONING_EFFORT_OPTIONS) and the
    # openai backend depend on this exact set/order.
    assert REASONING_EFFORTS == ("default", "none", "low", "medium", "high")
