from __future__ import annotations

import pytest
from fixtures import FRENCH_PARCEL, PARCEL_WITHOUT_OUTLINE, POINT_RESULT, SPANISH_PARCEL, SPANISH_POLYGON

from parcel_gps.core.parsing import ParcelRecord, parse_parcel, reference_at_point


def test_spanish_parcel_converts_lat_lng_outline_to_lng_lat_ring():
    record = parse_parcel(SPANISH_PARCEL["data"])

    assert record.reference == "9872023VH5797S0001WX"
    assert record.country == "ES"
    assert record.area_m2 == 812.0
    assert record.municipality == "MADRID"
    assert record.province == "MADRID"
    assert record.address == "CL PRINCIPE DE VERGARA 1"
    assert (record.latitude, record.longitude) == (40.4237, -3.6789)
    ring = record.polygons[0][0]
    assert ring[0] == (-3.679, 40.4236)
    assert ring[0] == ring[-1]
    assert len(ring) == 5
    assert record.to_wkt() == (
        "POLYGON ((-3.679 40.4236, -3.679 40.4238, -3.6788 40.4238, -3.6788 40.4236, -3.679 40.4236))"
    )


def test_closed_input_ring_is_not_closed_twice():
    record = parse_parcel(FRENCH_PARCEL["data"])

    assert len(record.polygons[0][0]) == 5


def test_api_attribution_is_used_when_present():
    record = parse_parcel(FRENCH_PARCEL["data"])

    assert record.attribution == "DGFiP - Cadastre, BDNB (CSTB)"
    assert record.source_text() == "DGFiP - Cadastre, BDNB (CSTB)"


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"attribution": " EGMS "}, "EGMS"),
        ({"source": {"attribution": "Copernicus"}}, "Copernicus"),
        ({"source": {"name": "BEV"}}, "BEV"),
        ({"source": "Kartverket"}, "Kartverket"),
        ({"source": "  "}, None),
        ({"source": 3}, None),
    ],
)
def test_attribution_variants(payload, expected):
    assert parse_parcel(payload).attribution == expected


def test_source_text_falls_back_to_country_then_generic():
    assert parse_parcel({"pais": "PV"}).source_text() == "Official cadastre of Spain - Basque Country, via Parcel GPS"
    assert parse_parcel({}).source_text() == "Official cadastre, via Parcel GPS"


def test_geojson_feature_from_polygon_endpoint():
    record = parse_parcel(SPANISH_POLYGON["data"], "fallback", "ES")

    assert record.reference == "10194A00110004"
    assert record.area_m2 == 45210.0
    assert (record.latitude, record.longitude) == (39.47, -6.37)
    assert record.polygons[0][0][0] == (-6.371, 39.469)


def test_multipolygon_and_holes_to_wkt():
    geojson = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], [[1, 1], [2, 1], [2, 2], [1, 1]]],
            [[[10, 10], [11, 10], [11, 11], [10, 10]]],
            [[[5, 5], [5, 5]]],
            "junk",
        ],
    }

    record = parse_parcel({"geometry": geojson})

    assert len(record.polygons) == 2
    assert len(record.polygons[0]) == 2
    assert record.to_wkt().startswith("MULTIPOLYGON (((0 0, 4 0, 4 4, 0 4, 0 0), (1 1, 2 1, 2 2, 1 1)), ((10 10")


def test_feature_collection_is_flattened():
    square = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}
    collection = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": square}, {"type": "Point"}]}

    record = parse_parcel({"geojson": collection})

    assert len(record.polygons) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"poligono": [[1, 1], [1, 1], [2, 2]]},
        {"poligono": "not a list"},
        {"poligono": [[1], ["a", "b"], None]},
        {"geojson": {"type": "Polygon", "coordinates": "x"}},
        {"geojson": {"type": "Polygon", "coordinates": []}},
        {"geojson": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]], [[0, 0], [1, 0], [1, 1]]]}},
        {"geojson": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}},
        {"geojson": "string"},
        {},
    ],
)
def test_unusable_geometry_gives_no_outline(payload):
    record = parse_parcel(payload)

    assert not record.has_outline
    assert record.to_wkt() is None


def test_numbers_as_text_and_bad_values():
    record = parse_parcel({"superficieParcela": "1234,5", "latitud": "40.1", "longitud": "-3.2"})
    assert record.area_m2 == 1234.5
    assert (record.latitude, record.longitude) == (40.1, -3.2)

    odd = parse_parcel({"superficieParcela": "abc", "area": True, "superficie": 0, "latitud": float("inf")})
    assert odd.area_m2 is None
    assert odd.latitude is None

    assert parse_parcel({"area": "nan"}).area_m2 is None
    assert parse_parcel({"area": None}).area_m2 is None


def test_zero_centroid_is_ignored_in_favour_of_next_candidate():
    record = parse_parcel({"latitud": 0, "longitud": 0, "coordenadas": {"latitud": 41.0, "longitud": 2.0}})

    assert (record.latitude, record.longitude) == (41.0, 2.0)


def test_fallbacks_for_reference_and_country():
    record = parse_parcel({"pais": "zz"}, "REF-1", "gb")

    assert record.reference == "REF-1"
    assert record.country == "UK"


def test_reference_at_point():
    assert reference_at_point(POINT_RESULT["data"]) == ("9872023VH5797S", "ES")
    assert reference_at_point({}) == (None, None)


def test_merge_keeps_own_values_and_fills_gaps():
    detailed = parse_parcel(PARCEL_WITHOUT_OUTLINE["data"])
    outline = parse_parcel(SPANISH_POLYGON["data"])

    merged = detailed.merged_with(outline)

    assert merged.municipality == "CACERES"
    assert merged.area_m2 == 45210.0
    assert merged.has_outline
    assert merged.latitude == 39.47


def test_record_defaults():
    record = ParcelRecord("X")

    assert record.polygons == []
    assert record.country is None
