from __future__ import annotations

from datetime import datetime, timezone

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeature,
    QgsFillSymbol,
    QgsGeometry,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)

from .core.parsing import ParcelRecord

RESULTS_LAYER_NAME = "Parcel GPS"
RESULTS_MARKER = "parcel_gps/results"
WGS84 = "EPSG:4326"
LAYER_URI = (
    "MultiPolygon?crs=EPSG:4326"
    "&field=reference:string(64)"
    "&field=country:string(4)"
    "&field=area_m2:double"
    "&field=municipality:string(128)"
    "&field=province:string(128)"
    "&field=address:string(255)"
    "&field=latitude:double"
    "&field=longitude:double"
    "&field=source:string(255)"
    "&field=fetched_at:string(32)"
    "&index=yes"
)
FILL_STYLE = {
    "color": "255,152,0,70",
    "outline_color": "230,81,0,255",
    "outline_width": "0.6",
}
AREA_DECIMALS = 1


def find_results_layer(project: QgsProject) -> QgsVectorLayer | None:
    for layer in project.mapLayers().values():
        if isinstance(layer, QgsVectorLayer) and layer.customProperty(RESULTS_MARKER) and layer.isValid():
            return layer
    return None


def results_layer(project: QgsProject) -> QgsVectorLayer:
    existing = find_results_layer(project)
    if existing is not None:
        return existing
    layer = QgsVectorLayer(LAYER_URI, RESULTS_LAYER_NAME, "memory")
    layer.setCustomProperty(RESULTS_MARKER, True)
    symbol = QgsFillSymbol.createSimple(FILL_STYLE)
    if symbol is not None and layer.renderer() is not None:
        layer.renderer().setSymbol(symbol)
    project.addMapLayer(layer)
    return layer


def add_records(project: QgsProject, records: list[ParcelRecord]) -> tuple[QgsVectorLayer, QgsRectangle, int]:
    layer = results_layer(project)
    known = _known_keys(layer)
    area = _area_calculator(project)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    features = []
    extent = QgsRectangle()
    extent.setMinimal()
    duplicates = 0
    for record in records:
        wkt = record.to_wkt()
        if not wkt:
            continue
        geometry = QgsGeometry.fromWkt(wkt)
        if geometry is None or geometry.isNull():
            continue
        extent.combineExtentWith(geometry.boundingBox())
        key = (record.reference.upper(), record.country or "")
        if key in known:
            duplicates += 1
            continue
        known.add(key)
        geometry.convertToMultiType()
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        feature.setAttributes(_attributes(record, geometry, area, fetched_at))
        features.append(feature)
    if features:
        layer.dataProvider().addFeatures(features)
        layer.updateExtents()
        layer.triggerRepaint()
    return layer, extent, duplicates


def to_canvas_extent(
    project: QgsProject, extent: QgsRectangle, canvas_crs: QgsCoordinateReferenceSystem
) -> QgsRectangle:
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(WGS84), canvas_crs, project)
    return transform.transformBoundingBox(extent)


def _known_keys(layer: QgsVectorLayer) -> set[tuple[str, str]]:
    keys = set()
    for feature in layer.getFeatures():
        reference = feature["reference"]
        country = feature["country"]
        keys.add((str(reference).upper() if reference else "", str(country) if country else ""))
    return keys


def _area_calculator(project: QgsProject) -> QgsDistanceArea:
    calculator = QgsDistanceArea()
    calculator.setSourceCrs(QgsCoordinateReferenceSystem(WGS84), project.transformContext())
    calculator.setEllipsoid("WGS84")
    return calculator


def _attributes(record: ParcelRecord, geometry: QgsGeometry, area: QgsDistanceArea, fetched_at: str) -> list:
    area_m2 = record.area_m2
    if area_m2 is None:
        area_m2 = round(area.measureArea(geometry), AREA_DECIMALS)
    return [
        record.reference,
        record.country,
        area_m2,
        record.municipality,
        record.province,
        record.address,
        record.latitude,
        record.longitude,
        record.source_text(),
        fetched_at,
    ]
