from __future__ import annotations

import pytest

from parcel_gps.core.countries import (
    COORDINATES_ONLY,
    COUNTRY_CODES,
    PUBLIC_COUNTRY_COUNT,
    REFERENCE_COUNTRY_CODES,
    country_label,
    normalize_country,
    supports_reference,
)
from parcel_gps.core.transport import HttpResponse


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
