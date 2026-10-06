from __future__ import annotations

SPANISH_PARCEL = {
    "success": True,
    "data": {
        "refCatastral": "9872023VH5797S0001WX",
        "pais": "ES",
        "direccion": "CL PRINCIPE DE VERGARA 1",
        "municipio": "MADRID",
        "provincia": "MADRID",
        "latitud": 40.4237,
        "longitud": -3.6789,
        "googleMapsUrl": "https://maps.google.com/?q=40.4237,-3.6789",
        "superficieParcela": 812,
        "poligono": [[40.4236, -3.679], [40.4238, -3.679], [40.4238, -3.6788], [40.4236, -3.6788]],
    },
    "searchesRemaining": 249,
}

FRENCH_PARCEL = {
    "success": True,
    "data": {
        "refCatastral": "750560000AB0001",
        "pais": "FR",
        "municipio": "Paris",
        "latitud": 48.85,
        "longitud": 2.35,
        "superficieParcela": 1500,
        "fuenteDatos": "DGFiP - Cadastre, BDNB (CSTB)",
        "poligono": [[48.85, 2.35], [48.851, 2.35], [48.851, 2.351], [48.85, 2.351], [48.85, 2.35]],
    },
}

PARCEL_WITHOUT_OUTLINE = {
    "success": True,
    "data": {
        "refCatastral": "10194A00110004",
        "pais": "ES",
        "municipio": "CACERES",
        "latitud": 39.47,
        "longitud": -6.37,
    },
}

SPANISH_POLYGON = {
    "success": True,
    "data": {
        "refcat": "10194A00110004",
        "geojson": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[-6.371, 39.469], [-6.369, 39.469], [-6.369, 39.471], [-6.371, 39.471], [-6.371, 39.469]]
                ],
            },
        },
        "centroid": {"latitude": 39.47, "longitude": -6.37},
        "area": 45210,
    },
}

POINT_RESULT = {
    "success": True,
    "data": {
        "referenciaCatastral": "9872023VH5797S",
        "refCat14": "9872023VH5797S",
        "municipio": "MADRID",
        "coordenadas": {"latitud": 40.4237, "longitud": -3.6789},
        "pais": "ES",
    },
}

UNAUTHORIZED = {"success": False, "code": "KEY_AUTH_001", "error": "Invalid API key"}
QUOTA_EXHAUSTED = {"success": False, "code": "KEY_AUTH_004", "error": "Monthly quota exhausted"}
BURST_LIMITED = {"success": False, "code": "RATE_LIMIT", "error": "Too many requests"}
COVERAGE = {
    "success": False,
    "code": "CNV_COVERAGE",
    "error": "This reference is in a country we do not cover yet",
    "data": {"country": "US", "reference": "X1", "supported": False},
}
AMBIGUOUS = {
    "success": False,
    "code": "CNV_AMBIGUOUS",
    "error": "This reference could belong to several countries",
    "data": {
        "reference": "05102200100005",
        "candidates": [
            {"country": "ES", "confidence": 0.6, "supported": True},
            {"country": "IT", "confidence": 0.3, "supported": True},
            {"country": "ES", "confidence": 0.1, "supported": True},
            "garbage",
        ],
    },
}
SERVER_ERROR = {"success": False, "code": "INTERNAL", "error": "Internal error"}

URBAN_PARCEL = {
    "success": True,
    "data": {
        "refCatastral": "9872023VH5797S0001WX",
        "pais": "ES",
        "municipio": "SANTA CRUZ DE MUDELA",
        "provincia": "CIUDAD REAL",
        "latitud": 38.6402423,
        "longitud": -3.4632872,
        "superficieParcela": 424,
        "poligono": [
            [38.6401335, -3.4633967],
            [38.6401462, -3.4631766],
            [38.6403511, -3.4631946],
            [38.6403328, -3.4633994],
            [38.6402683, -3.4633985],
            [38.6402676, -3.4634075],
            [38.6402121, -3.4634057],
            [38.6401335, -3.4633967],
        ],
    },
}
