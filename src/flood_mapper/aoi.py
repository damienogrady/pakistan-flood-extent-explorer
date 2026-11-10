"""Area-of-interest validation and conversion helpers."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
from shapely.geometry import shape

DEFAULT_AOI = {
    "type": "Polygon",
    "coordinates": [
        [
            [67.88989359151196, 24.559922523056073],
            [68.07142062478411, 24.559922523056073],
            [68.07142062478411, 24.420583865433088],
            [67.88989359151196, 24.420583865433088],
            [67.88989359151196, 24.559922523056073],
        ]
    ],
}
DEFAULT_CENTER = [24.49025319424458, 67.98065710814804]


def aoi_to_geodataframe(geojson: dict[str, Any]) -> gpd.GeoDataFrame:
    """Validate a drawn GeoJSON polygon and return it in WGS 84."""
    geometry_data = geojson.get("geometry", geojson)
    if not isinstance(geometry_data, dict):
        raise ValueError("Draw a polygon or rectangle on the map.")

    geometry = shape(geometry_data)
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("The area of interest must be a polygon or rectangle.")
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("The drawn area is empty or invalid; redraw the polygon.")
    min_x, min_y, max_x, max_y = geometry.bounds
    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
        raise ValueError("The drawn area must use longitude/latitude coordinates.")

    return gpd.GeoDataFrame(geometry=[geometry], crs="EPSG:4326")
