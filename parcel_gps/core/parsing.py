from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any
from collections.abc import Iterable

from .countries import country_label, normalize_country

MIN_RING_POINTS = 3
Point = tuple[float, float]
Ring = list[Point]
Polygon = list[Ring]


@dataclass(frozen=True)
class ParcelRecord:
    reference: str
    country: str | None = None
    area_m2: float | None = None
    municipality: str | None = None
    province: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    polygons: list[Polygon] = field(default_factory=list)
    attribution: str | None = None

    @property
    def has_outline(self) -> bool:
        return bool(self.polygons)

    def to_wkt(self) -> str | None:
        if not self.polygons:
            return None
        bodies = [_polygon_body(polygon) for polygon in self.polygons]
        if len(bodies) == 1:
            return f"POLYGON {bodies[0]}"
        return f"MULTIPOLYGON ({', '.join(bodies)})"

    def source_text(self) -> str:
        if self.attribution:
            return self.attribution
        if self.country:
            return f"Official cadastre of {country_label(self.country)}, via Parcel GPS"
        return "Official cadastre, via Parcel GPS"

    def merged_with(self, other: ParcelRecord) -> ParcelRecord:
        return replace(
            self,
            country=self.country or other.country,
            area_m2=self.area_m2 if self.area_m2 is not None else other.area_m2,
            municipality=self.municipality or other.municipality,
            province=self.province or other.province,
            address=self.address or other.address,
            latitude=self.latitude if self.latitude is not None else other.latitude,
            longitude=self.longitude if self.longitude is not None else other.longitude,
            polygons=self.polygons or other.polygons,
            attribution=self.attribution or other.attribution,
        )


def parse_parcel(
    data: dict[str, Any], fallback_reference: str = "", fallback_country: str | None = None
) -> ParcelRecord:
    centroid = _centroid(data)
    return ParcelRecord(
        reference=_text(data, "refCatastral", "referenciaCatastral", "refcat", "reference") or fallback_reference,
        country=normalize_country(data.get("pais") or data.get("country")) or normalize_country(fallback_country),
        area_m2=_area(data),
        municipality=_text(data, "municipio", "municipality"),
        province=_text(data, "provincia", "province"),
        address=_text(data, "direccion", "address"),
        latitude=centroid[0] if centroid else None,
        longitude=centroid[1] if centroid else None,
        polygons=_polygons(data),
        attribution=_attribution(data),
    )


def reference_at_point(data: dict[str, Any]) -> tuple[str | None, str | None]:
    reference = _text(data, "referenciaCatastral", "refCatastral", "refCat14", "refcat")
    return reference, normalize_country(data.get("pais") or data.get("country"))


def _text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.replace(",", "."))
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _area(data: dict[str, Any]) -> float | None:
    for key in ("superficieParcela", "area", "area_m2", "superficie"):
        value = _number(data.get(key))
        if value is not None and value > 0:
            return value
    return None


def _centroid(data: dict[str, Any]) -> tuple[float, float] | None:
    candidates = [
        (data.get("latitud"), data.get("longitud")),
        ((data.get("coordenadas") or {}).get("latitud"), (data.get("coordenadas") or {}).get("longitud")),
        ((data.get("centroid") or {}).get("latitude"), (data.get("centroid") or {}).get("longitude")),
    ]
    for raw_lat, raw_lng in candidates:
        lat, lng = _number(raw_lat), _number(raw_lng)
        if lat is not None and lng is not None and (lat, lng) != (0.0, 0.0):
            return lat, lng
    return None


def _attribution(data: dict[str, Any]) -> str | None:
    direct = _text(data, "attribution", "fuenteDatos")
    if direct:
        return direct
    source = data.get("source")
    if isinstance(source, dict):
        return _text(source, "attribution", "name")
    if isinstance(source, str) and source.strip():
        return source.strip()
    return None


def _polygons(data: dict[str, Any]) -> list[Polygon]:
    from_geojson = _geojson_polygons(data.get("geojson") or data.get("geometry"))
    if from_geojson:
        return from_geojson
    ring = _ring([(point[1], point[0]) for point in _pairs(data.get("poligono"))])
    return [[ring]] if ring else []


def _geojson_polygons(value: Any) -> list[Polygon]:
    if not isinstance(value, dict):
        return []
    kind = value.get("type")
    if kind == "Feature":
        return _geojson_polygons(value.get("geometry"))
    if kind == "FeatureCollection":
        polygons: list[Polygon] = []
        for feature in value.get("features") or []:
            polygons.extend(_geojson_polygons(feature))
        return polygons
    coordinates = value.get("coordinates")
    if kind == "Polygon":
        polygon = _geojson_polygon(coordinates)
        return [polygon] if polygon else []
    if kind == "MultiPolygon" and isinstance(coordinates, list):
        return [polygon for polygon in (_geojson_polygon(part) for part in coordinates) if polygon]
    return []


def _geojson_polygon(rings: Any) -> Polygon:
    if not isinstance(rings, list):
        return []
    parsed = [_ring([(point[0], point[1]) for point in _pairs(ring)]) for ring in rings]
    if not parsed or not parsed[0]:
        return []
    return [ring for ring in parsed if ring]


def _pairs(value: Any) -> Iterable[Point]:
    if not isinstance(value, list):
        return []
    pairs = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            first, second = _number(item[0]), _number(item[1])
            if first is not None and second is not None:
                pairs.append((first, second))
    return pairs


def _ring(points: list[Point]) -> Ring:
    distinct = []
    for point in points:
        if not distinct or distinct[-1] != point:
            distinct.append(point)
    if len(distinct) > 1 and distinct[0] == distinct[-1]:
        distinct.pop()
    if len(set(distinct)) < MIN_RING_POINTS:
        return []
    return [*distinct, distinct[0]]


def _polygon_body(polygon: Polygon) -> str:
    rings = ", ".join("(" + ", ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in ring) + ")" for ring in polygon)
    return f"({rings})"


def _fmt(value: float) -> str:
    return f"{value:.9f}".rstrip("0").rstrip(".")
