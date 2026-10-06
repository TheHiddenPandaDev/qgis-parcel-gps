from __future__ import annotations

import pytest
from conftest import json_response
from fixtures import (
    PARCEL_WITHOUT_OUTLINE,
    POINT_RESULT,
    QUOTA_EXHAUSTED,
    SPANISH_PARCEL,
    SPANISH_POLYGON,
    UNAUTHORIZED,
)

from parcel_gps.core.errors import AuthenticationError, NoOutlineError, NotFoundError, QuotaExceededError
from parcel_gps.core.service import ParcelService


def test_by_reference_uses_outline_from_parcel(make_client):
    client, transport = make_client(json_response(200, SPANISH_PARCEL))

    record = ParcelService(client).by_reference(" 9872023VH5797S0001WX ", "es")

    assert record.has_outline
    assert len(transport.calls) == 1
    assert transport.urls[0].endswith("/api/catastro/9872023VH5797S0001WX?country=ES")


def test_by_reference_falls_back_to_polygon_endpoint(make_client):
    client, transport = make_client(json_response(200, PARCEL_WITHOUT_OUTLINE), json_response(200, SPANISH_POLYGON))

    record = ParcelService(client).by_reference("10194A00110004")

    assert record.municipality == "CACERES"
    assert record.area_m2 == 45210.0
    assert record.has_outline
    assert transport.urls[1].endswith("/api/catastro/10194A00110004/polygon?country=ES")


def test_by_reference_without_any_outline(make_client):
    client, _ = make_client(json_response(200, PARCEL_WITHOUT_OUTLINE), json_response(200, {"data": {}}))

    with pytest.raises(NoOutlineError) as caught:
        ParcelService(client).by_reference("10194A00110004")

    assert caught.value.kind == "no_outline"


def test_by_reference_propagates_auth_error(make_client):
    client, _ = make_client(json_response(401, UNAUTHORIZED))

    with pytest.raises(AuthenticationError):
        ParcelService(client).by_reference("X1")


def test_at_point_resolves_reference_then_fetches_outline(make_client):
    client, transport = make_client(json_response(200, POINT_RESULT), json_response(200, SPANISH_PARCEL))
    service = ParcelService(client)

    record = service.at_point(40.4237, -3.6789)

    assert service.client is client
    assert record.reference == "9872023VH5797S0001WX"
    assert record.has_outline
    assert transport.urls[1].endswith("/api/catastro/9872023VH5797S?country=ES")


def test_at_point_uses_outline_when_point_answer_has_one(make_client):
    client, transport = make_client(json_response(200, SPANISH_PARCEL))

    record = ParcelService(client).at_point(40.4237, -3.6789, "ES")

    assert record.has_outline
    assert len(transport.calls) == 1
    assert "country=ES" in transport.urls[0]


def test_at_point_nothing_found(make_client):
    client, _ = make_client(json_response(200, {"success": True, "data": {}}))

    with pytest.raises(NotFoundError):
        ParcelService(client).at_point(1.0, 1.0)


def test_at_point_in_coordinates_only_country(make_client):
    client, transport = make_client(json_response(200, {"data": {"referenciaCatastral": "AB123", "pais": "UK"}}))

    with pytest.raises(NoOutlineError) as caught:
        ParcelService(client).at_point(55.95, -3.19)

    assert caught.value.details["country"] == "UK"
    assert len(transport.calls) == 1


def test_at_point_uses_requested_country_when_answer_has_none(make_client):
    client, transport = make_client(
        json_response(200, {"data": {"referenciaCatastral": "0745901TG4304N"}}), json_response(200, SPANISH_PARCEL)
    )

    ParcelService(client).at_point(40.0, -3.0, "ES")

    assert transport.urls[1].endswith("country=ES")


def test_at_point_quota_error_propagates(make_client):
    client, _ = make_client(json_response(429, QUOTA_EXHAUSTED))

    with pytest.raises(QuotaExceededError):
        ParcelService(client).at_point(40.0, -3.0)
