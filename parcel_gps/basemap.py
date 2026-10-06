from __future__ import annotations

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorTileLayer,
)

from .core.presentation import (
    CADASTRE_ATTRIBUTION,
    LayerInfo,
    basemap_for,
    cadastre_wms_uri,
    has_basemap,
    padded_extent,
    xyz_uri,
)

BASEMAP_MARKER = "parcel_gps/basemap"
CADASTRE_MARKER = "parcel_gps/cadastre"
CADASTRE_LAYER_NAME = "Catastro (Spain)"
CADASTRE_OPACITY = 0.85
WEB_MERCATOR = "EPSG:3857"
WGS84 = "EPSG:4326"
MINIMUM_HALF_SIZE_METRES = 45.0
MINIMUM_HALF_SIZE_DEGREES = 0.0004


def layer_infos(project: QgsProject) -> list[LayerInfo]:
    return [_layer_info(layer) for layer in project.mapLayers().values()]


def _layer_info(layer: QgsMapLayer) -> LayerInfo:
    if isinstance(layer, QgsRasterLayer):
        kind = "raster"
    elif isinstance(layer, QgsVectorTileLayer):
        kind = "vectortile"
    else:
        kind = "vector"
    return LayerInfo(kind, layer.providerType() or "", bool(layer.customProperty(CADASTRE_MARKER)))


def owned_layer(project: QgsProject, marker: str) -> QgsMapLayer | None:
    for layer in project.mapLayers().values():
        if layer.customProperty(marker):
            return layer
    return None


def ensure_basemap(project: QgsProject, choice: str) -> QgsRasterLayer | None:
    if has_basemap(layer_infos(project)):
        return None
    return _add_basemap(project, choice)


def replace_basemap(project: QgsProject, choice: str) -> QgsRasterLayer | None:
    current = owned_layer(project, BASEMAP_MARKER)
    if current is not None:
        project.removeMapLayer(current.id())
    return ensure_basemap(project, choice)


def _add_basemap(project: QgsProject, choice: str) -> QgsRasterLayer | None:
    basemap = basemap_for(choice)
    if basemap is None:
        return None
    layer = QgsRasterLayer(xyz_uri(basemap), basemap.name, "wms")
    if not layer.isValid():
        return None
    _set_attribution(layer, basemap.attribution)
    layer.setCustomProperty(BASEMAP_MARKER, basemap.key)
    project.addMapLayer(layer, False)
    project.layerTreeRoot().addLayer(layer)
    return layer


def add_cadastre_overlay(project: QgsProject, above: QgsMapLayer | None) -> QgsRasterLayer | None:
    existing = owned_layer(project, CADASTRE_MARKER)
    if existing is not None:
        return existing
    layer = QgsRasterLayer(cadastre_wms_uri(), CADASTRE_LAYER_NAME, "wms")
    if not layer.isValid():
        return None
    _set_attribution(layer, CADASTRE_ATTRIBUTION)
    layer.setCustomProperty(CADASTRE_MARKER, True)
    layer.setOpacity(CADASTRE_OPACITY)
    project.addMapLayer(layer, False)
    root = project.layerTreeRoot()
    node = root.findLayer(above.id()) if above is not None else None
    if node is None:
        root.insertLayer(0, layer)
    else:
        parent = node.parent()
        parent.insertLayer(parent.children().index(node) + 1, layer)
    return layer


def remove_cadastre_overlay(project: QgsProject) -> None:
    layer = owned_layer(project, CADASTRE_MARKER)
    if layer is not None:
        project.removeMapLayer(layer.id())


def use_web_mercator(project: QgsProject, canvas) -> None:
    crs = QgsCoordinateReferenceSystem(WEB_MERCATOR)
    project.setCrs(crs)
    if canvas is not None:
        canvas.setDestinationCrs(crs)


def framed_extent(project: QgsProject, extent: QgsRectangle, crs: QgsCoordinateReferenceSystem) -> QgsRectangle:
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(WGS84), crs, project)
    target = transform.transformBoundingBox(extent)
    minimum = MINIMUM_HALF_SIZE_DEGREES if crs.isGeographic() else MINIMUM_HALF_SIZE_METRES
    return QgsRectangle(
        *padded_extent(target.xMinimum(), target.yMinimum(), target.xMaximum(), target.yMaximum(), minimum)
    )


def _set_attribution(layer: QgsMapLayer, attribution: str) -> None:
    metadata = layer.metadata()
    metadata.setRights([attribution])
    layer.setMetadata(metadata)
    server_properties = getattr(layer, "serverProperties", None)
    properties = server_properties() if callable(server_properties) else None
    if properties is not None and hasattr(properties, "setAttribution"):
        properties.setAttribution(attribution)
    else:
        layer.setAttribution(attribution)
