from __future__ import annotations

import pytest
from conftest import API_KEY, json_response
from fixtures import (
    AMBIGUOUS,
    BURST_LIMITED,
    COVERAGE,
    QUOTA_EXHAUSTED,
    SERVER_ERROR,
    SPANISH_PARCEL,
    UNAUTHORIZED,
)

from parcel_gps.core.client import DEFAULT_BASE_URL, ParcelGpsClient, read_quota
from parcel_gps.core.errors import (
    AmbiguousReferenceError,
    AuthenticationError,
    CoverageError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    ParcelGpsError,
    PlaceNameError,
    QuotaExceededError,
    RateLimitError,
    RequestTimeoutError,
    ServerError,
    ServiceUnavailableError,
    ValidationError,
)
from parcel_gps.core.transport import HttpResponse, TransportFailure, TransportTimeout

QUOTA_HEADERS = {
    "X-Quota-Tier": "free",
    "X-Quota-Limit": "250",
    "X-Quota-Remaining": "249",
    "X-Quota-Reset": "2026-11-01T00:00:00Z",
    "X-RateLimit-Limit": "10",
    "X-RateLimit-Remaining": "9",
    "X-RateLimit-Reset": "42",
}


def test_get_parcel_sends_key_and_unwraps_data(make_client):
    client, transport = make_client(json_response(200, SPANISH_PARCEL, QUOTA_HEADERS))

    data = client.get_parcel("9872023VH5797S0001WX", "ES")

    assert data["refCatastral"] == "9872023VH5797S0001WX"
    call = transport.calls[0]
    assert call["url"] == f"{DEFAULT_BASE_URL}/api/catastro/9872023VH5797S0001WX?country=ES"
    assert call["headers"]["X-API-Key"] == API_KEY
    assert call["headers"]["User-Agent"].startswith("parcel-gps-qgis/")
    assert client.last_quota == {
        "plan": "free",
        "limit": 250,
        "remaining": 249,
        "resets_at": "2026-11-01T00:00:00Z",
        "rate_limit": 10,
        "rate_remaining": 9,
        "rate_reset_seconds": 42,
    }


def test_get_parcel_without_country_omits_query_and_escapes_reference(make_client):
    client, transport = make_client(json_response(200, SPANISH_PARCEL))

    client.get_parcel("  21004C0123/00  ")

    assert transport.urls == [f"{DEFAULT_BASE_URL}/api/catastro/21004C0123%2F00"]


def test_polygon_and_point_paths(make_client):
    client, transport = make_client(json_response(200, {"data": {}}), json_response(200, {"data": {}}))

    client.get_polygon("10194A00110004", "ES")
    client.parcel_at(40.41998, -3.70377)

    assert transport.urls == [
        f"{DEFAULT_BASE_URL}/api/catastro/10194A00110004/polygon?country=ES",
        f"{DEFAULT_BASE_URL}/api/search/coordinates?lat=40.4199800&lng=-3.7037700",
    ]


def test_custom_base_url_is_trimmed(make_client):
    client, transport = make_client(json_response(200, {"data": {}}), base_url="https://api.catastrogps.es/")

    client.get_parcel("X1", "PL")

    assert transport.urls[0].startswith("https://api.catastrogps.es/api/catastro/X1")


@pytest.mark.parametrize("key", ["", "   ", None])
def test_missing_key_is_rejected(key):
    with pytest.raises(ValidationError):
        ParcelGpsClient(key)


def test_repr_never_shows_the_key():
    client = ParcelGpsClient(API_KEY)

    assert API_KEY not in repr(client)
    assert "***" in repr(client)


@pytest.mark.parametrize("reference", ["", "   ", "x" * 65])
def test_invalid_reference_is_rejected_before_any_request(make_client, reference):
    client, transport = make_client()

    with pytest.raises(ValidationError):
        client.get_parcel(reference)
    assert transport.calls == []


@pytest.mark.parametrize("lat,lng", [(91, 0), (0, 181), (float("nan"), 1), (True, 1), ("40", "3")])
def test_invalid_point_is_rejected(make_client, lat, lng):
    client, transport = make_client()

    with pytest.raises(ValidationError):
        client.parcel_at(lat, lng)
    assert transport.calls == []


def test_401_raises_authentication_error(make_client):
    client, _ = make_client(json_response(401, UNAUTHORIZED))

    with pytest.raises(AuthenticationError) as caught:
        client.get_parcel("X1")

    assert caught.value.status == 401
    assert caught.value.kind == "auth"
    assert API_KEY not in str(caught.value)


def test_429_quota_exhausted_is_not_retried(make_client, sleeps):
    client, transport = make_client(json_response(429, QUOTA_EXHAUSTED, {"X-Quota-Remaining": "0"}))

    with pytest.raises(QuotaExceededError) as caught:
        client.get_parcel("X1")

    assert caught.value.kind == "quota"
    assert len(transport.calls) == 1
    assert sleeps == []
    assert client.last_quota == {"remaining": 0}


def test_429_burst_limit_carries_retry_after(make_client):
    client, _ = make_client(json_response(429, BURST_LIMITED, {"Retry-After": "7"}))

    with pytest.raises(RateLimitError) as caught:
        client.get_parcel("X1")

    assert caught.value.retry_after == 7.0


def test_429_burst_limit_falls_back_to_rate_limit_reset(make_client):
    client, _ = make_client(json_response(429, BURST_LIMITED, {"X-RateLimit-Reset": "12", "Retry-After": "nope"}))

    with pytest.raises(RateLimitError) as caught:
        client.get_parcel("X1")

    assert caught.value.retry_after == 12.0


def test_500_is_not_retried(make_client, sleeps):
    client, transport = make_client(json_response(500, SERVER_ERROR))

    with pytest.raises(ServerError) as caught:
        client.get_parcel("X1")

    assert caught.value.status == 500
    assert len(transport.calls) == 1
    assert sleeps == []


def test_502_is_retried_with_backoff_then_succeeds(make_client, sleeps):
    client, transport = make_client(
        json_response(502, {}),
        json_response(503, SERVER_ERROR, {"Retry-After": "3"}),
        json_response(200, SPANISH_PARCEL),
    )

    data = client.get_parcel("X1")

    assert data["municipio"] == "MADRID"
    assert len(transport.calls) == 3
    assert sleeps == [1.0, 3.0]


def test_503_gives_up_after_max_retries(make_client, sleeps):
    client, transport = make_client(*[json_response(503, SERVER_ERROR) for _ in range(3)])

    with pytest.raises(ServiceUnavailableError):
        client.get_parcel("X1")

    assert len(transport.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_timeout_is_retried_then_raised(make_client, sleeps):
    client, transport = make_client(TransportTimeout("slow"), TransportTimeout("slow"), max_retries=1)

    with pytest.raises(RequestTimeoutError) as caught:
        client.get_parcel("X1")

    assert caught.value.kind == "timeout"
    assert len(transport.calls) == 2
    assert sleeps == [1.0]


def test_network_failure_is_retried_then_succeeds(make_client):
    client, _ = make_client(TransportFailure("connection refused"), json_response(200, SPANISH_PARCEL))

    assert client.get_parcel("X1")["pais"] == "ES"


def test_network_failure_without_retries(make_client):
    client, _ = make_client(TransportFailure("dns"), max_retries=0)

    with pytest.raises(NetworkError) as caught:
        client.get_parcel("X1")

    assert "dns" in str(caught.value)


def test_coverage_error_exposes_country(make_client):
    client, _ = make_client(json_response(422, COVERAGE))

    with pytest.raises(CoverageError) as caught:
        client.get_parcel("X1")

    assert caught.value.country == "US"
    assert caught.value.kind == "coverage"


def test_ambiguous_reference_lists_unique_countries(make_client):
    client, _ = make_client(json_response(300, AMBIGUOUS))

    with pytest.raises(AmbiguousReferenceError) as caught:
        client.get_parcel("05102200100005")

    assert caught.value.candidate_countries == ["ES", "IT"]


def test_ambiguous_without_details_has_no_candidates():
    error = AmbiguousReferenceError("x", details=None)

    assert error.candidate_countries == []
    assert CoverageError("x", details=None).country is None


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (422, {"code": "CNV_PLACE_NAME", "error": "place"}, PlaceNameError),
        (403, {"error": "forbidden"}, ForbiddenError),
        (404, {"error": "not found"}, NotFoundError),
        (400, {"error": "bad"}, ValidationError),
        (422, {"error": "bad"}, ValidationError),
        (418, {"error": "teapot"}, ParcelGpsError),
        (504, {}, ServerError),
    ],
)
def test_status_mapping(make_client, status, body, expected):
    client, _ = make_client(*[json_response(status, body) for _ in range(3)])

    with pytest.raises(expected) as caught:
        client.get_parcel("X1")

    assert type(caught.value) is expected


def test_error_without_json_body_uses_status_text(make_client):
    client, _ = make_client(HttpResponse(401, b"<html>nope</html>", {}))

    with pytest.raises(AuthenticationError) as caught:
        client.get_parcel("X1")

    assert caught.value.message == "HTTP 401"


def test_error_message_that_is_not_text_is_replaced(make_client):
    client, _ = make_client(json_response(404, {"error": {"nested": True}}))

    with pytest.raises(NotFoundError) as caught:
        client.get_parcel("X1")

    assert caught.value.message == "HTTP 404"


@pytest.mark.parametrize(
    "response",
    [
        HttpResponse(200, b"", {}),
        HttpResponse(200, b"[1, 2]", {}),
        HttpResponse(200, b"\xff\xfe", {}),
        json_response(200, {"success": True, "data": None}),
        json_response(200, {"success": True, "data": []}),
    ],
)
def test_empty_or_odd_success_bodies_give_empty_dict(make_client, response):
    client, _ = make_client(response)

    assert client.get_parcel("X1") == {}


def test_body_without_envelope_is_returned_as_is(make_client):
    client, _ = make_client(json_response(200, {"refCatastral": "X1"}))

    assert client.get_parcel("X1") == {"refCatastral": "X1"}


def test_read_quota_ignores_junk_headers():
    response = HttpResponse(
        200, b"", {"x-quota-limit": "abc", "X-Quota-Remaining": "inf", "x-ratelimit-remaining": "3"}
    )

    assert read_quota(response) == {"rate_remaining": 3}


def test_last_quota_is_kept_when_response_has_no_headers(make_client):
    client, _ = make_client(json_response(200, SPANISH_PARCEL, QUOTA_HEADERS), json_response(200, SPANISH_PARCEL))

    client.get_parcel("X1")
    client.get_parcel("X1")

    assert client.last_quota["remaining"] == 249
