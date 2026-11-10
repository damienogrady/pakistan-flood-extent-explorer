from datetime import date, timedelta

import pandas as pd
import pytest

from flood_mapper.aoi import DEFAULT_AOI, aoi_to_geodataframe
from flood_mapper.app import _suggested_labels
from flood_mapper.dates import (
    MIN_COMPARISON_GAP_DAYS,
    MOSAIC_WINDOW_DAYS,
    comparison_dates_are_valid,
    mosaic_window_start,
)
from flood_mapper.gee import comparison_layers


def test_accepts_a_geojson_feature_polygon():
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[152.9, -27.6], [153.0, -27.6], [153.0, -27.5],
                             [152.9, -27.5], [152.9, -27.6]]],
        },
    }

    result = aoi_to_geodataframe(feature)

    assert result.crs.to_string() == "EPSG:4326"
    assert result.geometry.iloc[0].geom_type == "Polygon"


def test_default_area_matches_supplied_region():
    result = aoi_to_geodataframe(DEFAULT_AOI)

    assert result.total_bounds == pytest.approx(
        [67.88989359151196, 24.420583865433088, 68.07142062478411, 24.559922523056073]
    )


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [153.0, -27.5]},
        {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
        },
    ],
)
def test_rejects_non_polygons_and_invalid_polygons(geometry):
    with pytest.raises(ValueError):
        aoi_to_geodataframe(geometry)


def test_rejects_coordinates_outside_longitude_latitude():
    polygon = {
        "type": "Polygon",
        "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 1], [200, 0]]],
    }

    with pytest.raises(ValueError, match="longitude/latitude"):
        aoi_to_geodataframe(polygon)


def test_mosaic_window_includes_exactly_sixty_calendar_days():
    window_end = date(2022, 3, 2)

    window_start = mosaic_window_start(window_end)

    assert (window_end - window_start).days + 1 == MOSAIC_WINDOW_DAYS


def test_comparison_windows_must_be_separated_by_at_least_sixty_days():
    first_end = date(2022, 1, 1)

    assert comparison_dates_are_valid(
        first_end,
        first_end + timedelta(days=MIN_COMPARISON_GAP_DAYS),
    )
    assert not comparison_dates_are_valid(
        first_end,
        first_end + timedelta(days=MIN_COMPARISON_GAP_DAYS - 1),
    )
    assert not comparison_dates_are_valid(first_end, first_end)


def test_comparison_rejects_overlapping_mosaic_windows():
    aoi = aoi_to_geodataframe(
        {
            "type": "Polygon",
            "coordinates": [
                [[152.9, -27.6], [153.0, -27.6], [153.0, -27.5],
                 [152.9, -27.5], [152.9, -27.6]]
            ],
        }
    )
    first = {"date": "2022-01-01", "pass": "ASCENDING", "orbit": 12}
    second = {"date": "2022-03-01", "pass": "ASCENDING", "orbit": 12}

    with pytest.raises(ValueError, match="at least 60 days apart"):
        comparison_layers(aoi, first, second)


def test_suggested_pair_prefers_dates_near_the_2022_pakistan_flood_period():
    acquisitions = pd.DataFrame(
        [
            {"date": date(2022, 3, 10), "pass": "ASCENDING", "orbit": 12, "label": "early"},
            {"date": date(2022, 5, 12), "pass": "ASCENDING", "orbit": 12, "label": "baseline"},
            {"date": date(2022, 9, 7), "pass": "ASCENDING", "orbit": 12, "label": "flood"},
            {"date": date(2022, 10, 1), "pass": "ASCENDING", "orbit": 12, "label": "late"},
        ]
    )

    assert _suggested_labels(acquisitions) == ("baseline", "flood")
