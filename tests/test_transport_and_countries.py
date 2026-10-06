from __future__ import annotations

import io
import socket
import urllib.error
from email.message import Message

import pytest

from parcel_gps.core import transport
from parcel_gps.core.countries import (
    COORDINATES_ONLY,
    COUNTRY_CODES,
    PUBLIC_COUNTRY_COUNT,
    REFERENCE_COUNTRY_CODES,
    country_label,
    normalize_country,
    supports_reference,
)
from parcel_gps.core.transport import HttpResponse, TransportFailure, TransportTimeout, urllib_transport


class FakeUrlResponse:
    def __init__(self, status, body, headers):
        self.status = status
        self._body = body
        self.headers = headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _headers(**values):
    message = Message()
    for key, value in values.items():
        message[key.replace("_", "-")] = value
    return message


def test_urllib_transport_success(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeUrlResponse(200, b'{"ok": true}', _headers(X_Quota_Limit="250"))

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)

    response = urllib_transport("https://example.test/x", {"X-API-Key": "k"}, 5.0)

    assert response.status == 200
    assert response.body == b'{"ok": true}'
    assert response.header("x-quota-limit") == "250"
    assert captured["timeout"] == 5.0
    assert captured["request"].get_header("X-api-key") == "k"


def test_urllib_transport_http_error_is_a_response(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many", _headers(Retry_After="3"), io.BytesIO(b"{}"))

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)

    response = urllib_transport("https://example.test/x", {}, 5.0)

    assert response.status == 429
    assert response.header("Retry-After") == "3"


def test_urllib_transport_http_error_without_body(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "Boom", None, None)

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)

    response = urllib_transport("https://example.test/x", {}, 5.0)

    assert (response.status, response.body, dict(response.headers)) == (500, b"", {})


@pytest.mark.parametrize(
    "raised,expected",
    [
        (socket.timeout("timed out"), TransportTimeout),
        (urllib.error.URLError(socket.timeout("timed out")), TransportTimeout),
        (urllib.error.URLError("name not resolved"), TransportFailure),
        (ConnectionResetError("reset"), TransportFailure),
    ],
)
def test_urllib_transport_failures(monkeypatch, raised, expected):
    def fake_urlopen(request, timeout):
        raise raised

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(expected):
        urllib_transport("https://example.test/x", {}, 5.0)


def test_http_response_header_missing():
    assert HttpResponse(200).header("X") is None


def test_public_country_count_is_29():
    assert PUBLIC_COUNTRY_COUNT == 29
    assert len(COUNTRY_CODES) == 31
    assert len(REFERENCE_COUNTRY_CODES) == 29
    assert COORDINATES_ONLY.isdisjoint(REFERENCE_COUNTRY_CODES)


@pytest.mark.parametrize(
    "value,expected",
    [(None, None), ("", None), (" es ", "ES"), ("GB", "UK"), ("el", "GR"), ("US", None), (7, None)],
)
def test_normalize_country(value, expected):
    assert normalize_country(value) == expected


def test_supports_reference_and_labels():
    assert supports_reference(None)
    assert supports_reference("ES")
    assert not supports_reference("HR")
    assert country_label("NA") == "Spain - Navarre"
    assert country_label("ZZ") == "ZZ"
    assert country_label(None) == ""
