"""Unit tests for EGA HTTP caller authentication."""

import pytest
from fastapi import HTTPException

from ega.service import _authenticate_caller


def test_bearer_token_is_accepted_when_configured(monkeypatch):
    monkeypatch.setenv("EGA_API_BEARER_TOKEN", "test-secret")
    _authenticate_caller("Bearer test-secret")


@pytest.mark.parametrize("header", [None, "", "Basic test-secret", "Bearer", "Bearer wrong-secret"])
def test_missing_or_invalid_bearer_token_is_rejected(monkeypatch, header):
    monkeypatch.setenv("EGA_API_BEARER_TOKEN", "test-secret")
    with pytest.raises(HTTPException) as exc_info:
        _authenticate_caller(header)
    assert exc_info.value.status_code == 401


def test_unconfigured_bearer_token_fails_closed(monkeypatch):
    monkeypatch.delenv("EGA_API_BEARER_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        _authenticate_caller("Bearer test-secret")
    assert exc_info.value.status_code == 503
    assert "not configured" in exc_info.value.detail.lower()
