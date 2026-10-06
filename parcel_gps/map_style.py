from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsFillSymbol,
    QgsPalLayerSettings,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont

from .core.presentation import (
    LABEL_COLOR,
    LABEL_HALO_COLOR,
    LABEL_HALO_OPACITY,
    LABEL_HALO_SIZE_MM,
    LABEL_MAX_SCALE_DENOMINATOR,
    LABEL_SIZE_PT,
    STYLE_VERSION,
    fill_symbol_properties,
    label_expression,
    outline_layers_properties,
)

STYLE_MARKER = "parcel_gps/style_version"


def needs_style(layer: QgsVectorLayer) -> bool:
    return str(layer.customProperty(STYLE_MARKER, "")) != str(STYLE_VERSION)


def apply_parcel_style(layer: QgsVectorLayer) -> None:
    layer.setRenderer(QgsSingleSymbolRenderer(parcel_symbol()))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings()))
    layer.setLabelsEnabled(True)
    layer.setCustomProperty(STYLE_MARKER, str(STYLE_VERSION))
    layer.triggerRepaint()


def parcel_symbol() -> QgsFillSymbol:
    symbol = QgsFillSymbol()
    symbol.deleteSymbolLayer(0)
    symbol.appendSymbolLayer(QgsSimpleFillSymbolLayer.create(fill_symbol_properties()))
    for properties in outline_layers_properties():
        symbol.appendSymbolLayer(QgsSimpleLineSymbolLayer.create(properties))
    return symbol


def label_settings() -> QgsPalLayerSettings:
    settings = QgsPalLayerSettings()
    settings.fieldName = label_expression()
    settings.isExpression = True
    settings.setFormat(text_format())
    settings.scaleVisibility = True
    settings.minimumScale = LABEL_MAX_SCALE_DENOMINATOR
    settings.maximumScale = 0
    placement = getattr(Qgis, "LabelPlacement", None)
    if placement is not None:
        settings.placement = placement.OverPoint
    alignment = getattr(Qgis, "LabelMultiLineAlignment", None)
    if alignment is not None:
        settings.multilineAlign = alignment.Center
    return settings


def text_format() -> QgsTextFormat:
    text = QgsTextFormat()
    font = QFont()
    font.setBold(True)
    text.setFont(font)
    text.setSize(LABEL_SIZE_PT)
    text.setColor(QColor(LABEL_COLOR))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(LABEL_HALO_SIZE_MM)
    buffer.setColor(QColor(LABEL_HALO_COLOR))
    buffer.setOpacity(LABEL_HALO_OPACITY)
    text.setBuffer(buffer)
    return text
