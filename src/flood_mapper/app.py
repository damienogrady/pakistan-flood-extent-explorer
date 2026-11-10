"""Streamlit interface for interactive Sentinel-1 flood-image comparison."""

from __future__ import annotations

from datetime import date, timedelta
import os
import zipfile

import ee
import folium
from folium.plugins import Draw, SideBySideLayers
import geopandas as gpd
import pandas as pd
import requests
import rasterio
import streamlit as st
from streamlit_folium import st_folium

from flood_mapper.aoi import DEFAULT_AOI, DEFAULT_CENTER, aoi_to_geodataframe
from flood_mapper.dates import (
    MIN_COMPARISON_GAP_DAYS,
    MOSAIC_WINDOW_DAYS,
    mosaic_window_start,
)
from flood_mapper.gee import (
    DEFAULT_END,
    DEFAULT_START,
    FLOOD_TARGET_DATE,
    PRE_FLOOD_TARGET_DATE,
    comparison_layers,
    export_comparison_zip,
    find_acquisitions,
    initialize_earth_engine,
)

DEFAULT_MAP_ZOOM = 11
REGION_CONFIG_VERSION = 3
VIS_PARAMS = {"bands": ["VV", "VH", "VH_VV_ratio"], "min": [-25, -32, 0], "max": [0, -5, 1]}

st.set_page_config(
    page_title="Sentinel-1 Flood Extent Explorer",
    page_icon="🌊",
    layout="wide",
)


def _initialize_state() -> None:
    previous_region_config_version = st.session_state.get("region_config_version")
    defaults = {
        "gee_ready": False,
        "gee_project": os.environ.get("GEE_PROJECT", ""),
        "aoi_geojson": None,
        "acquisitions": pd.DataFrame(columns=["date", "pass", "orbit", "label"]),
        "map_center": DEFAULT_CENTER,
        "map_zoom": DEFAULT_MAP_ZOOM,
        "aoi_map_revision": 0,
        "search_start": DEFAULT_START,
        "search_end": DEFAULT_END,
        "acquisition_range": None,
        "region_config_version": REGION_CONFIG_VERSION,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    if previous_region_config_version != REGION_CONFIG_VERSION:
        if st.session_state["aoi_geojson"] is None:
            st.session_state["map_center"] = DEFAULT_CENTER
            st.session_state["map_zoom"] = DEFAULT_MAP_ZOOM
        if (
            st.session_state["search_start"] == date(2022, 1, 1)
            and st.session_state["search_end"] == date(2022, 12, 31)
        ):
            st.session_state["search_start"] = DEFAULT_START
            st.session_state["search_end"] = DEFAULT_END
        st.session_state["acquisitions"] = pd.DataFrame(
            columns=["date", "pass", "orbit", "label"]
        )
        st.session_state["acquisition_range"] = None
        st.session_state["comparison_ready"] = False
        st.session_state["region_config_version"] = REGION_CONFIG_VERSION


def _map_aoi() -> folium.Map:
    map_view = folium.Map(
        location=st.session_state["map_center"],
        zoom_start=st.session_state["map_zoom"],
        tiles="OpenStreetMap",
        control_scale=True,
    )
    default_feature = {"type": "Feature", "properties": {}, "geometry": DEFAULT_AOI}
    folium.GeoJson(
        st.session_state["aoi_geojson"] or default_feature,
        name="Area of interest",
        style_function=lambda _: {"color": "#00a9a5", "weight": 2, "fillOpacity": 0.08},
    ).add_to(map_view)
    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polyline": False,
            "circle": False,
            "circlemarker": False,
            "marker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(map_view)
    return map_view


def _selected_aoi() -> gpd.GeoDataFrame:
    return aoi_to_geodataframe(st.session_state["aoi_geojson"] or DEFAULT_AOI)


def _capture_map_state(result: dict) -> None:
    drawing = result.get("last_active_drawing")
    if drawing and drawing != st.session_state["aoi_geojson"]:
        st.session_state["aoi_geojson"] = drawing
        st.session_state["acquisitions"] = pd.DataFrame(
            columns=["date", "pass", "orbit", "label"]
        )
        st.session_state["acquisition_range"] = None
        st.session_state["comparison_ready"] = False
    center = result.get("center")
    if center:
        st.session_state["map_center"] = [center["lat"], center["lng"]]
    zoom = result.get("zoom")
    if zoom:
        st.session_state["map_zoom"] = zoom


def _acquisition_record(frame: pd.DataFrame, label: str) -> dict:
    record = frame.loc[frame["label"] == label].iloc[0].to_dict()
    record["date"] = record["date"].isoformat()
    record["orbit"] = int(record["orbit"])
    return record


def _suggested_labels(frame: pd.DataFrame) -> tuple[str, str] | None:
    pairs = []
    for _, first in frame.iterrows():
        matching = frame[
            (frame["date"] >= first["date"] + timedelta(days=MIN_COMPARISON_GAP_DAYS))
            & (frame["pass"] == first["pass"])
            & (frame["orbit"] == first["orbit"])
        ]
        for _, second in matching.iterrows():
            target_distance = abs(
                (first["date"] - PRE_FLOOD_TARGET_DATE).days
            ) + abs((second["date"] - FLOOD_TARGET_DATE).days)
            pairs.append((target_distance, first["label"], second["label"]))
    if not pairs:
        return None
    _, first_label, second_label = min(pairs)
    return first_label, second_label


def _tile_layer(image: ee.Image, name: str) -> folium.TileLayer:
    map_id = image.getMapId(VIS_PARAMS)
    return folium.TileLayer(
        tiles=map_id["tile_fetcher"].url_format,
        attr="Google Earth Engine · Copernicus Sentinel-1",
        name=name,
        overlay=True,
        control=False,
        show=True,
    )


def _comparison_map(
    first_image: ee.Image,
    second_image: ee.Image,
    first_label: str,
    second_label: str,
) -> folium.Map:
    map_view = folium.Map(
        location=st.session_state["map_center"],
        zoom_start=st.session_state["map_zoom"],
        tiles="OpenStreetMap",
        control_scale=True,
    )
    first_layer = _tile_layer(first_image, first_label)
    second_layer = _tile_layer(second_image, second_label)
    first_layer.add_to(map_view)
    second_layer.add_to(map_view)
    SideBySideLayers(first_layer, second_layer).add_to(map_view)
    return map_view


def main() -> None:
    _initialize_state()
    st.title("Sentinel-1 Flood Extent Explorer")
    st.markdown(
        "Explore and compare Sentinel-1 radar mosaics for a region of interest "
        "and date range of your choice."
    )
    with st.expander("How it works", expanded=True):
        st.markdown(
            """
            1. **Connect** your Earth Engine account and Google Cloud project.
            2. **Choose an area and dates**; the map searches the live Sentinel-1 archive.
            3. **Compare** two 60-day mosaics with the map's swipe divider.

            Sentinel-1 is radar, so it can collect imagery through cloud. Open water
            often looks dark, but urban structures, vegetation, wind, and viewing
            geometry can all affect its appearance. This is a visual demonstration,
            not an automated flood classification. Each mosaic uses the latest
            available valid pixel in its window; it is not a single-date snapshot.
            """
        )

    st.subheader("1 · Connect to Google Earth Engine")
    st.caption(
        "Earth Engine is Google's geospatial analysis platform. Authenticate once "
        "in your terminal with `earthengine authenticate`, then connect here."
    )
    auth_col, button_col = st.columns([3, 1])
    with auth_col:
        project = st.text_input(
            "Google Cloud project ID",
            key="gee_project",
            help="Use the project registered for Earth Engine and with its API enabled.",
        )
    with button_col:
        st.write("")
        st.write("")
        if st.button("Connect to Earth Engine", type="primary"):
            try:
                initialize_earth_engine(project)
            except ee.EEException as exc:
                st.session_state["gee_ready"] = False
                st.error(
                    f"Earth Engine could not initialize: {exc} "
                    "Check your authentication, project ID, and API access."
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["gee_ready"] = True
                st.success("Connected to Earth Engine.")
    if st.session_state["gee_ready"]:
        st.success(f"Connected project: {st.session_state['gee_project']}")
    else:
        st.info("Connect before searching the Sentinel-1 archive.")

    st.subheader("2 · Choose an area and find mosaic dates")
    st.write(
        "The map starts over your supplied area in Sindh, Pakistan. Pan and "
        "zoom, then draw a rectangle or polygon; otherwise this default area "
        "is used. Each "
        f"selected date becomes the end of a trailing {MOSAIC_WINDOW_DAYS}-day mosaic."
    )
    if st.button("Reset to default area"):
        st.session_state["aoi_geojson"] = None
        st.session_state["map_center"] = DEFAULT_CENTER
        st.session_state["map_zoom"] = DEFAULT_MAP_ZOOM
        st.session_state["aoi_map_revision"] += 1
        st.session_state["acquisitions"] = pd.DataFrame(
            columns=["date", "pass", "orbit", "label"]
        )
        st.session_state["acquisition_range"] = None
        st.session_state["comparison_ready"] = False
    map_result = st_folium(
        _map_aoi(),
        height=470,
        use_container_width=True,
        returned_objects=["last_active_drawing", "center", "zoom"],
        key=f"aoi-map-{st.session_state['aoi_map_revision']}",
    )
    _capture_map_state(map_result)

    date_col, search_col = st.columns([3, 1])
    with date_col:
        chosen_range = st.date_input(
            "Search for mosaic end dates",
            value=(st.session_state["search_start"], st.session_state["search_end"]),
            min_value=date(2014, 10, 3),
            max_value=date.today(),
            help=(
                "The default range covers the 2022 Pakistan flood period. Each mosaic includes "
                "the selected date and the previous "
                f"{MOSAIC_WINDOW_DAYS - 1} days."
            ),
        )
    with search_col:
        st.write("")
        st.write("")
        search_clicked = st.button(
            "Find mosaic dates",
            disabled=not st.session_state["gee_ready"],
        )

    has_complete_range = isinstance(chosen_range, (tuple, list)) and len(chosen_range) == 2
    if has_complete_range:
        st.session_state["search_start"], st.session_state["search_end"] = chosen_range
    if search_clicked:
        st.session_state["comparison_ready"] = False
        st.session_state["acquisitions"] = pd.DataFrame(
            columns=["date", "pass", "orbit", "label"]
        )
        st.session_state["acquisition_range"] = None
        if not has_complete_range:
            st.error("Choose both a start and end date.")
        else:
            try:
                selected_aoi = _selected_aoi()
                acquisitions = find_acquisitions(
                    selected_aoi, chosen_range[0], chosen_range[1]
                )
            except (ee.EEException, ValueError) as exc:
                st.error(f"Could not search the selected area and dates: {exc}")
            else:
                st.session_state["acquisitions"] = acquisitions
                st.session_state["acquisition_range"] = tuple(chosen_range)
                if acquisitions.empty:
                    st.warning(
                        "No IW-mode acquisitions with both VV and VH were found "
                        "for this area and date range. Try a wider range or another area."
                    )
                else:
                    st.success(
                        f"Found {len(acquisitions)} available mosaic end dates "
                        "across the matching Sentinel-1 tracks."
                    )

    acquisitions = st.session_state["acquisitions"]
    current_range = tuple(chosen_range) if has_complete_range else None
    if not acquisitions.empty and st.session_state["acquisition_range"] != current_range:
        st.info("The date range changed. Search again to refresh available mosaic dates.")
        acquisitions = pd.DataFrame(columns=["date", "pass", "orbit", "label"])
        st.session_state["comparison_ready"] = False
    if not acquisitions.empty:
        st.subheader("3 · Compare two mosaics")
        labels = acquisitions["label"].tolist()
        suggested_pair = _suggested_labels(acquisitions)
        suggested_first = suggested_pair[0] if suggested_pair else labels[0]
        first_col, second_col = st.columns(2)
        with first_col:
            first_label = st.selectbox(
                "Earlier 60-day mosaic",
                labels,
                index=labels.index(suggested_first),
                key=f"first-mosaic-{current_range}",
            )
        first_record = _acquisition_record(acquisitions, first_label)
        first_end = date.fromisoformat(first_record["date"])
        eligible_second = acquisitions[
            (acquisitions["pass"] == first_record["pass"])
            & (acquisitions["orbit"] == first_record["orbit"])
            & (
                acquisitions["date"]
                >= first_end + timedelta(days=MIN_COMPARISON_GAP_DAYS)
            )
        ]
        if eligible_second.empty:
            st.warning(
                "No later mosaic date is available on the same Sentinel-1 track "
                f"at least {MIN_COMPARISON_GAP_DAYS} days after this date. "
                "Choose an earlier first date or search a later date range."
            )
            second_label = None
        else:
            suggested_second = (
                suggested_pair[1]
                if suggested_pair and suggested_pair[0] == first_label
                and suggested_pair[1] in eligible_second["label"].tolist()
                else eligible_second.iloc[0]["label"]
            )
            second_labels = eligible_second["label"].tolist()
            with second_col:
                second_label = st.selectbox(
                    "Later 60-day mosaic",
                    second_labels,
                    index=second_labels.index(suggested_second),
                    key=f"second-mosaic-{current_range}-{first_label}",
                )
        st.caption(
            f"Each mosaic covers {MOSAIC_WINDOW_DAYS} calendar days and uses the "
            "latest valid pixel in that window. End dates must be at least "
            f"{MIN_COMPARISON_GAP_DAYS} days apart, on the same orbit track."
        )
        st.caption(
            "The suggested 2022 Pakistan flood comparison targets May 15 "
            "(baseline) and September 5 (flood period); matching dates depend "
            "on the Sentinel-1 archive for this area."
        )
        if second_label is not None:
            first_window_start = mosaic_window_start(first_end)
            second_end = date.fromisoformat(
                _acquisition_record(acquisitions, second_label)["date"]
            )
            second_window_start = mosaic_window_start(second_end)
            st.caption(
                f"Left: {first_window_start} to {first_end} · "
                f"Right: {second_window_start} to {second_end}"
            )
            if st.session_state.get("comparison_ready") and st.session_state[
                "comparison_labels"
            ] != (first_label, second_label):
                st.session_state["comparison_ready"] = False
        compare_clicked = st.button(
            "Compare selected mosaics",
            type="primary",
            disabled=second_label is None,
        )
        if compare_clicked and second_label is not None:
            try:
                selected_aoi = _selected_aoi()
                first_record = _acquisition_record(acquisitions, first_label)
                second_record = _acquisition_record(acquisitions, second_label)
                first_image, second_image = comparison_layers(
                    selected_aoi, first_record, second_record
                )
                comparison = _comparison_map(
                    first_image, second_image, first_label, second_label
                )
            except (ee.EEException, ValueError) as exc:
                st.error(f"Could not build this comparison: {exc}")
            else:
                st.session_state["comparison_ready"] = True
                st.session_state["comparison_map"] = comparison
                st.session_state["comparison_labels"] = (first_label, second_label)
                st.session_state["comparison_aoi"] = selected_aoi
                st.session_state["comparison_records"] = (first_record, second_record)

    if st.session_state.get("comparison_ready"):
        first_label, second_label = st.session_state["comparison_labels"]
        st.subheader("4 · Swipe to compare")
        st.caption(
            "Drag the vertical divider across the map. Each side shows a "
            "60-day mosaic formed from the latest valid pixels in that window."
        )
        st_folium(
            st.session_state["comparison_map"],
            height=600,
            use_container_width=True,
            returned_objects=[],
            key=f"comparison-map-{first_label}-{second_label}",
        )
        if st.button("Prepare GeoTIFF download"):
            try:
                first_record, second_record = st.session_state["comparison_records"]
                archive = export_comparison_zip(
                    st.session_state["comparison_aoi"],
                    first_record,
                    second_record,
                )
            except (
                ee.EEException,
                ValueError,
                rasterio.errors.RasterioError,
                requests.RequestException,
                zipfile.BadZipFile,
            ) as exc:
                st.error(f"Could not prepare the GeoTIFF export: {exc}")
            else:
                st.download_button(
                    "Download comparison ZIP",
                    data=archive,
                    file_name="sentinel1_flood_comparison.zip",
                    mime="application/zip",
                )

    st.divider()
    st.caption(
        "Imagery: Copernicus Sentinel-1 via Google Earth Engine. "
        "For interpretation guidance, see the project methods note."
    )


if __name__ == "__main__":
    main()
