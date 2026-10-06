from __future__ import annotations

import pytest
from fixtures import FRENCH_PARCEL, PARCEL_WITHOUT_OUTLINE, URBAN_PARCEL

from parcel_gps.core.parsing import ParcelRecord, parse_parcel
from parcel_gps.core.presentation import (
    BASEMAP_NONE,
    BASEMAP_SATELLITE,
    BASEMAP_STREETS,
    BASEMAPS,
    BRAND_BLUE,
    DEFAULT_BASEMAP,
    FILL_ALPHA,
    OUTLINE_WIDTH_MM,
    LayerInfo,
    basemap_for,
    cadastre_wms_uri,
    detail_rows,
    fill_symbol_properties,
    format_area,
    has_basemap,
    hex_to_rgb,
    is_basemap,
    label_expression,
    normalize_basemap_choice,
    offers_cadastre_overlay,
    outline_layers_properties,
    padded_extent,
    rgba,
    xyz_uri,
)


@pytest.mark.parametrize(
    ("area", "expected"),
    [
        (None, ""),
        (0, "0 m²"),
        (424, "424 m²"),
        (812.4, "812 m²"),
        (9999.4, "9999 m²"),
        (10_000, "1.00 ha"),
        (45_210, "4.52 ha"),
        (1_234_567, "123.46 ha"),
    ],
)
def test_format_area_switches_to_hectares_from_ten_thousand_square_metres(area, expected):
    assert format_area(area) == expected


def test_format_area_uses_the_given_decimal_point():
    assert format_area(45_210, ",") == "4,52 ha"
    assert format_area(424, ",") == "424 m²"


def test_label_expression_shows_reference_and_area_with_the_hectare_threshold():
    expression = label_expression()

    assert expression.startswith('"reference" || CASE')
    assert '"area_m2" IS NULL' in expression
    assert '"area_m2" >= 10000' in expression
    assert 'format_number("area_m2" / 10000, 2)' in expression
    assert "' ha'" in expression and "' m²'" in expression
    assert expression.count("'\\n'") == 2


def test_fill_is_translucent_brand_blue_without_its_own_outline():
    properties = fill_symbol_properties()

    assert properties["color"] == f"30,64,175,{FILL_ALPHA}"
    assert properties["outline_style"] == "no"
    assert 0.2 <= FILL_ALPHA / 255 <= 0.3


def test_outline_is_a_brand_blue_line_over_a_white_halo():
    halo, line = outline_layers_properties()

    assert line["line_color"] == "30,64,175,255"
    assert line["line_width"] == str(OUTLINE_WIDTH_MM)
    assert halo["line_color"].startswith("255,255,255,")
    assert float(halo["line_width"]) > float(line["line_width"])
    assert {halo["line_width_unit"], line["line_width_unit"]} == {"MM"}


def test_colour_helpers():
    assert hex_to_rgb(BRAND_BLUE) == (30, 64, 175)
    assert hex_to_rgb("ffffff") == (255, 255, 255)
    assert rgba("#000000", 10) == "0,0,0,10"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("satellite", BASEMAP_SATELLITE),
        (" Streets ", BASEMAP_STREETS),
        ("none", BASEMAP_NONE),
        ("", DEFAULT_BASEMAP),
        (None, DEFAULT_BASEMAP),
        ("google", DEFAULT_BASEMAP),
        (3, DEFAULT_BASEMAP),
    ],
)
def test_normalize_basemap_choice(value, expected):
    assert normalize_basemap_choice(value) == expected


def test_default_basemap_is_satellite():
    assert DEFAULT_BASEMAP == BASEMAP_SATELLITE


def test_basemap_for_returns_the_catalogue_entry_or_nothing():
    assert basemap_for("satellite") is BASEMAPS[BASEMAP_SATELLITE]
    assert basemap_for("streets") is BASEMAPS[BASEMAP_STREETS]
    assert basemap_for("none") is None
    assert basemap_for("unknown") is BASEMAPS[BASEMAP_SATELLITE]


def test_basemaps_carry_their_attribution():
    assert BASEMAPS[BASEMAP_SATELLITE].attribution == "Esri, Maxar, Earthstar Geographics"
    assert BASEMAPS[BASEMAP_STREETS].attribution == "© OpenStreetMap contributors"
    assert "World_Imagery" in BASEMAPS[BASEMAP_SATELLITE].url
    assert BASEMAPS[BASEMAP_STREETS].url.startswith("https://tile.openstreetmap.org/")


def test_xyz_uri_encodes_the_tile_placeholders():
    uri = xyz_uri(BASEMAPS[BASEMAP_SATELLITE])

    assert uri.startswith("type=xyz&url=https://server.arcgisonline.com/")
    assert "%7Bz%7D/%7By%7D/%7Bx%7D" in uri
    assert "{" not in uri
    assert uri.endswith("&zmin=0&zmax=19")


def test_cadastre_wms_uri_targets_the_inspire_parcel_layer():
    uri = cadastre_wms_uri()

    assert "layers=CP.CadastralParcel" in uri
    assert "url=https://ovc.catastro.meh.es/cartografia/INSPIRE/spadgcwms.aspx" in uri
    assert "crs=EPSG:3857" in uri
    assert "format=image/png" in uri


@pytest.mark.parametrize(
    ("layer", "expected"),
    [
        (LayerInfo("raster", "wms"), True),
        (LayerInfo("raster", "gdal"), True),
        (LayerInfo("vectortile", "xyzvectortiles"), True),
        (LayerInfo("vector", "WMS"), True),
        (LayerInfo("vector", "arcgismapserver"), True),
        (LayerInfo("vector", "memory"), False),
        (LayerInfo("vector", "ogr"), False),
        (LayerInfo("raster", "wms", owned_overlay=True), False),
    ],
)
def test_is_basemap(layer, expected):
    assert is_basemap(layer) is expected


def test_has_basemap_ignores_vectors_and_the_cadastre_overlay():
    assert has_basemap([]) is False
    assert has_basemap([LayerInfo("vector", "memory"), LayerInfo("raster", "wms", owned_overlay=True)]) is False
    assert has_basemap([LayerInfo("vector", "memory"), LayerInfo("raster", "wms")]) is True


@pytest.mark.parametrize(
    ("country", "expected"), [("ES", True), ("es", True), ("PT", False), ("PV", False), (None, False)]
)
def test_cadastre_overlay_is_offered_only_for_spain(country, expected):
    assert offers_cadastre_overlay(country) is expected


def test_padded_extent_adds_thirty_percent_on_each_side():
    assert padded_extent(0, 0, 100, 50, 1) == pytest.approx((-30, -15, 130, 65))


def test_padded_extent_respects_a_minimum_half_size():
    assert padded_extent(10, 20, 10, 20, 45) == pytest.approx((-35, -25, 55, 65))
    assert padded_extent(0, 0, 100, 2, 10) == pytest.approx((-30, -9, 130, 11))


def test_padded_extent_accepts_a_custom_ratio():
    assert padded_extent(0, 0, 10, 10, 0, ratio=0) == pytest.approx((0, 0, 10, 10))


def test_detail_rows_for_a_full_record():
    record = parse_parcel(URBAN_PARCEL["data"])

    assert detail_rows(record) == [
        ("reference", "9872023VH5797S0001WX"),
        ("municipality", "SANTA CRUZ DE MUDELA, CIUDAD REAL"),
        ("area", "424 m²"),
        ("centroid", "38.640242, -3.463287"),
    ]


def test_detail_rows_with_hectares_and_decimal_comma():
    record = parse_parcel(FRENCH_PARCEL["data"])
    rows = dict(detail_rows(ParcelRecord(**{**record.__dict__, "area_m2": 15_000.0}), ","))

    assert rows["municipality"] == "Paris"
    assert rows["area"] == "1,50 ha"


def test_detail_rows_skip_missing_values():
    assert detail_rows(ParcelRecord(reference="X1")) == [("reference", "X1")]
    rows = detail_rows(parse_parcel(PARCEL_WITHOUT_OUTLINE["data"]))

    assert [key for key, _ in rows] == ["reference", "municipality", "centroid"]


def test_urban_fixture_has_an_outline_in_spain():
    record = parse_parcel(URBAN_PARCEL["data"])

    assert record.has_outline
    assert record.country == "ES"
    assert record.to_wkt().startswith("POLYGON ((-3.4633967 38.6401335")
