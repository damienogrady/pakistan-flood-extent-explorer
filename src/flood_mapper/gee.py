"""Google Earth Engine queries, Sentinel-1 composites, and small exports."""

from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from typing import Any
import zipfile

import ee
import geopandas as gpd
import pandas as pd
import rasterio
import requests

from flood_mapper.dates import (
    MOSAIC_WINDOW_DAYS,
    comparison_dates_are_valid,
    mosaic_window_start,
)

COLLECTION_ID = "COPERNICUS/S1_GRD"
DEFAULT_START = date(2022, 3, 1)
DEFAULT_END = date(2022, 10, 31)
PRE_FLOOD_TARGET_DATE = date(2022, 5, 15)
FLOOD_TARGET_DATE = date(2022, 9, 5)


def initialize_earth_engine(project: str) -> None:
    """Initialize the Earth Engine client for the selected Cloud project."""
    if not project.strip():
        raise ValueError("Enter the Google Cloud project ID registered for Earth Engine.")
    ee.Initialize(project=project.strip())


def aoi_geometry(aoi: gpd.GeoDataFrame) -> ee.Geometry:
    """Convert the validated WGS 84 area to an Earth Engine geometry."""
    return ee.Geometry(aoi.geometry.iloc[0].__geo_interface__)


def _dual_pol_collection(
    aoi: gpd.GeoDataFrame,
    start_date: date,
    end_date: date,
) -> ee.ImageCollection:
    if end_date < start_date:
        raise ValueError("The end date must be on or after the start date.")
    return (
        ee.ImageCollection(COLLECTION_ID)
        .filterBounds(aoi_geometry(aoi))
        .filterDate(start_date.isoformat(), (end_date + timedelta(days=1)).isoformat())
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    )


def find_acquisitions(
    aoi: gpd.GeoDataFrame,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Return eligible mosaic end dates and orbit metadata."""
    collection = _dual_pol_collection(aoi, start_date, end_date)

    def add_record(image: ee.Image) -> ee.Image:
        record = ee.Dictionary(
            {
                "date": image.date().format("YYYY-MM-dd"),
                "pass": image.get("orbitProperties_pass"),
                "orbit": image.get("relativeOrbitNumber_start"),
            }
        )
        return image.set("acquisition_record", record)

    records = collection.map(add_record).aggregate_array("acquisition_record").getInfo()
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return pd.DataFrame(columns=["date", "pass", "orbit", "label"])

    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame["orbit"] = pd.to_numeric(frame["orbit"], errors="raise").astype(int)
    frame = frame.drop_duplicates(["date", "pass", "orbit"])
    frame["label"] = frame.apply(
        lambda row: (
            f"{row['date'].isoformat()} mosaic · {row['pass'].title()} "
            f"· orbit {row['orbit']}"
        ),
        axis=1,
    )
    return frame.sort_values(["date", "pass", "orbit"]).reset_index(drop=True)


def _selected_mosaic(
    aoi: gpd.GeoDataFrame,
    mosaic_end: dict[str, Any],
) -> ee.Image:
    end_date = date.fromisoformat(mosaic_end["date"])
    start_date = mosaic_window_start(end_date)
    collection = (
        _dual_pol_collection(aoi, start_date, end_date)
        .filter(ee.Filter.eq("orbitProperties_pass", mosaic_end["pass"]))
        .filter(
            ee.Filter.eq(
                "relativeOrbitNumber_start",
                int(mosaic_end["orbit"]),
            )
        )
        .sort("system:time_start")
    )
    image = collection.mosaic()
    vv = image.select("VV")
    vh = image.select("VH")
    ratio = ee.Image.constant(10).pow(vh.subtract(vv).divide(10)).rename("VH_VV_ratio")
    return vv.addBands(vh).addBands(ratio).clip(aoi_geometry(aoi))


def comparison_layers(
    aoi: gpd.GeoDataFrame,
    first: dict[str, Any],
    second: dict[str, Any],
) -> tuple[ee.Image, ee.Image]:
    """Build clipped, three-band mosaics for two non-overlapping date windows."""
    first_end = date.fromisoformat(first["date"])
    second_end = date.fromisoformat(second["date"])
    if not comparison_dates_are_valid(first_end, second_end):
        raise ValueError(
            f"Choose window end dates at least {MOSAIC_WINDOW_DAYS} days apart, "
            "with the first date earlier."
        )
    for key in ("pass", "orbit"):
        if first[key] != second[key]:
            raise ValueError(
                "Choose mosaics with the same orbit direction and relative orbit number."
            )
    return _selected_mosaic(aoi, first), _selected_mosaic(aoi, second)


def _download_geotiff(image: ee.Image, aoi: gpd.GeoDataFrame, name: str) -> bytes:
    url = image.getDownloadURL(
        {
            "name": name,
            "scale": 10,
            "region": aoi_geometry(aoi),
            "filePerBand": False,
            "format": "GEO_TIFF",
        }
    )
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    payload = response.content

    if zipfile.is_zipfile(BytesIO(payload)):
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            tif_name = next(
                (member for member in archive.namelist() if member.lower().endswith(".tif")),
                None,
            )
            if tif_name is None:
                raise ValueError("Earth Engine's export did not contain a GeoTIFF.")
            payload = archive.read(tif_name)

    with rasterio.MemoryFile(payload) as memory_file:
        with memory_file.open() as dataset:
            if dataset.count != 3:
                raise ValueError(
                    f"Expected a three-band composite, received {dataset.count} bands."
                )
    return payload


def export_comparison_zip(
    aoi: gpd.GeoDataFrame,
    first: dict[str, Any],
    second: dict[str, Any],
) -> bytes:
    """Download both selected composites and package rasters plus metadata."""
    images = comparison_layers(aoi, first, second)
    output = BytesIO()
    metadata: list[dict[str, Any]] = []
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for acquisition, image in zip((first, second), images, strict=True):
            window_end = date.fromisoformat(acquisition["date"])
            window_start = mosaic_window_start(window_end)
            file_stem = (
                f"sentinel1_mosaic_{window_start}_{window_end}_"
                f"{acquisition['pass'].lower()}_orbit_{acquisition['orbit']}"
            )
            tif_bytes = _download_geotiff(image, aoi, file_stem)
            archive.writestr(f"{file_stem}.tif", tif_bytes)
            with rasterio.MemoryFile(tif_bytes) as memory_file:
                with memory_file.open() as dataset:
                    metadata.append(
                        {
                            "window_start": window_start,
                            "window_end": window_end,
                            "pass": acquisition["pass"],
                            "relative_orbit": acquisition["orbit"],
                            "mosaic_method": "latest valid pixel, sorted by acquisition time",
                            "window_days": MOSAIC_WINDOW_DAYS,
                            "width_pixels": dataset.width,
                            "height_pixels": dataset.height,
                            "band_count": dataset.count,
                            "crs": str(dataset.crs),
                            "bands": "VV_dB,VH_dB,VH_VV_ratio",
                        }
                    )
        archive.writestr("metadata.csv", pd.DataFrame(metadata).to_csv(index=False))
    return output.getvalue()
