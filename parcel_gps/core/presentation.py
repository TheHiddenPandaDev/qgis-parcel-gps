from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .parsing import ParcelRecord

SQUARE_METRES_PER_HECTARE = 10_000
HECTARE_DECIMALS = 2
COORDINATE_DECIMALS = 6
ZOOM_MARGIN_RATIO = 0.3
SPAIN = "ES"

BRAND_BLUE = "#1e40af"
FILL_ALPHA = 64
OUTLINE_WIDTH_MM = 0.6
OUTLINE_HALO_COLOR = "#ffffff"
OUTLINE_HALO_ALPHA = 150
OUTLINE_HALO_WIDTH_MM = 1.2
LABEL_COLOR = "#0f172a"
LABEL_SIZE_PT = 10.0
LABEL_HALO_COLOR = "#ffffff"
LABEL_HALO_SIZE_MM = 1.0
LABEL_HALO_OPACITY = 0.85
LABEL_MAX_SCALE_DENOMINATOR = 50_000
STYLE_VERSION = 2

BASEMAP_SATELLITE = "satellite"
BASEMAP_STREETS = "streets"
BASEMAP_NONE = "none"
DEFAULT_BASEMAP = BASEMAP_SATELLITE
BASEMAP_PROVIDERS = frozenset({"wms", "xyz", "arcgismapserver", "arcgisimageserver", "wcs", "mbtilesvectortiles"})
BASEMAP_LAYER_KINDS = frozenset({"raster", "vectortile"})

CADASTRE_WMS_URL = "https://ovc.catastro.meh.es/cartografia/INSPIRE/spadgcwms.aspx"
CADASTRE_WMS_LAYER = "CP.CadastralParcel"
CADASTRE_WMS_CRS = "EPSG:3857"
CADASTRE_WMS_FORMAT = "image/png"
CADASTRE_ATTRIBUTION = "Dirección General del Catastro"


@dataclass(frozen=True)
class Basemap:
    key: str
    name: str
    url: str
    attribution: str
    max_zoom: int


BASEMAPS = {
    BASEMAP_SATELLITE: Basemap(
        BASEMAP_SATELLITE,
        "Satellite (Esri World Imagery)",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Esri, Maxar, Earthstar Geographics",
        19,
    ),
    BASEMAP_STREETS: Basemap(
        BASEMAP_STREETS,
        "OpenStreetMap",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "© OpenStreetMap contributors",
        19,
    ),
}
BASEMAP_CHOICES = (BASEMAP_SATELLITE, BASEMAP_STREETS, BASEMAP_NONE)


@dataclass(frozen=True)
class LayerInfo:
    kind: str
    provider: str
    owned_overlay: bool = False


def normalize_basemap_choice(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in BASEMAP_CHOICES else DEFAULT_BASEMAP


def basemap_for(choice: object) -> Basemap | None:
    return BASEMAPS.get(normalize_basemap_choice(choice))


def is_basemap(layer: LayerInfo) -> bool:
    if layer.owned_overlay:
        return False
    return layer.kind in BASEMAP_LAYER_KINDS or layer.provider.lower() in BASEMAP_PROVIDERS


def has_basemap(layers: Iterable[LayerInfo]) -> bool:
    return any(is_basemap(layer) for layer in layers)


def xyz_uri(basemap: Basemap) -> str:
    url = basemap.url.replace("{", "%7B").replace("}", "%7D")
    return f"type=xyz&url={url}&zmin=0&zmax={basemap.max_zoom}"


def cadastre_wms_uri() -> str:
    return (
        f"contextualWMSLegend=0&crs={CADASTRE_WMS_CRS}&dpiMode=7&format={CADASTRE_WMS_FORMAT}"
        f"&layers={CADASTRE_WMS_LAYER}&styles=&url={CADASTRE_WMS_URL}"
    )


def offers_cadastre_overlay(country: str | None) -> bool:
    return (country or "").upper() == SPAIN


def format_area(area_m2: float | None, decimal_point: str = ".") -> str:
    if area_m2 is None:
        return ""
    if area_m2 >= SQUARE_METRES_PER_HECTARE:
        hectares = f"{area_m2 / SQUARE_METRES_PER_HECTARE:.{HECTARE_DECIMALS}f}"
        return f"{hectares.replace('.', decimal_point)} ha"
    return f"{area_m2:.0f} m²"


def label_expression() -> str:
    return (
        '"reference" || CASE '
        "WHEN \"area_m2\" IS NULL THEN '' "
        f'WHEN "area_m2" >= {SQUARE_METRES_PER_HECTARE} '
        f"THEN '\\n' || format_number(\"area_m2\" / {SQUARE_METRES_PER_HECTARE}, {HECTARE_DECIMALS}) || ' ha' "
        "ELSE '\\n' || format_number(\"area_m2\", 0) || ' m²' END"
    )


def fill_symbol_properties() -> dict[str, str]:
    return {
        "color": rgba(BRAND_BLUE, FILL_ALPHA),
        "outline_style": "no",
    }


def outline_layers_properties() -> list[dict[str, str]]:
    return [
        _line_properties(OUTLINE_HALO_COLOR, OUTLINE_HALO_ALPHA, OUTLINE_HALO_WIDTH_MM),
        _line_properties(BRAND_BLUE, 255, OUTLINE_WIDTH_MM),
    ]


def _line_properties(color: str, alpha: int, width_mm: float) -> dict[str, str]:
    return {
        "line_color": rgba(color, alpha),
        "line_width": str(width_mm),
        "line_width_unit": "MM",
        "joinstyle": "round",
        "capstyle": "round",
    }


def rgba(color: str, alpha: int) -> str:
    red, green, blue = hex_to_rgb(color)
    return f"{red},{green},{blue},{alpha}"


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def padded_extent(
    xmin: float, ymin: float, xmax: float, ymax: float, minimum_half_size: float, ratio: float = ZOOM_MARGIN_RATIO
) -> tuple[float, float, float, float]:
    half_width = max((xmax - xmin) / 2 * (1 + 2 * ratio), minimum_half_size)
    half_height = max((ymax - ymin) / 2 * (1 + 2 * ratio), minimum_half_size)
    center_x, center_y = (xmin + xmax) / 2, (ymin + ymax) / 2
    return center_x - half_width, center_y - half_height, center_x + half_width, center_y + half_height


def detail_rows(record: ParcelRecord, decimal_point: str = ".") -> list[tuple[str, str]]:
    rows = [("reference", record.reference)]
    place = ", ".join(part for part in (record.municipality, record.province) if part)
    if place:
        rows.append(("municipality", place))
    if record.area_m2 is not None:
        rows.append(("area", format_area(record.area_m2, decimal_point)))
    if record.latitude is not None and record.longitude is not None:
        rows.append(("centroid", f"{_coordinate(record.latitude)}, {_coordinate(record.longitude)}"))
    return rows


def _coordinate(value: float) -> str:
    return f"{value:.{COORDINATE_DECIMALS}f}"
