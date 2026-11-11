# Design notes

## Purpose and scope

The explorer is a small interactive client for comparing Sentinel-1 GRD
backscatter over a user-drawn or default area of interest (AOI). It is designed
for visual exploration and learning, not for producing an authoritative flood
extent, an emergency alert, or a validated classification.

The Streamlit interface owns user interaction and session state. Earth Engine
does the scene search, mosaicking, clipping, and map-tile generation. Pandas
organizes acquisition metadata, GeoPandas and Shapely validate the AOI, and
rasterio checks downloaded GeoTIFFs.

## Application flow

1. The user authenticates with Earth Engine outside the browser and initializes
   the app with a registered Google Cloud project.
2. The map starts at the configured default AOI. A drawn polygon or rectangle
   replaces it for subsequent searches.
3. The app searches `COPERNICUS/S1_GRD` for IW-mode images containing both VV
   and VH, then presents available acquisition dates and orbit metadata.
4. The user selects an earlier and later date on the same pass direction and
   relative orbit. Candidate end dates must be separated by at least the
   60-day mosaic window.
5. For each end date, the data layer queries the preceding 60 calendar days,
   orders the matching collection by acquisition time, and creates a mosaic.
   The latest valid pixel takes priority; earlier scenes can fill masked
   areas.
6. Each mosaic is clipped to the AOI, converted to VV, VH, and linear VH/VV
   ratio bands, and shown as an Earth Engine tile layer. Folium's swipe control
   reveals the two layers side by side.
7. If requested, the same mosaics are downloaded as clipped three-band
   GeoTIFFs and packaged with a CSV metadata record.

The acquisition search range limits which mosaic end dates are offered. The
60-day imagery window for a selected end date may begin before the search
range's start date.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `src/flood_mapper/app.py` | Streamlit page, session state, map interactions, date selection, comparison and download controls |
| `src/flood_mapper/aoi.py` | Default AOI and map center; GeoJSON polygon validation and conversion to a WGS 84 GeoDataFrame |
| `src/flood_mapper/dates.py` | Inclusive 60-day window calculation and non-overlap rule |
| `src/flood_mapper/gee.py` | Earth Engine initialization, Sentinel-1 filtering, mosaicking, visualization bands, and raster download |

The UI passes normalized AOIs and acquisition records to the data helpers.
Processing and selection rules belong in helpers rather than being duplicated
in Streamlit callbacks.

## Key decisions

### Same-track comparisons

The two mosaics must have the same orbit direction and relative orbit number.
This reduces differences in viewing geometry between the dates. It also means
that a search can return acquisitions without producing an eligible pair;
the interface reports that condition rather than silently mixing tracks.

### Fixed trailing windows

Each selected date is an inclusive mosaic end date covering that date and the
previous 59 calendar days. End dates at least 60 days apart produce windows
that do not overlap. This was chosen to improve spatial coverage over sparse
single-scene footprints while avoiding overlap between the comparison periods.

Mosaicking improves coverage but sacrifices temporal specificity. Different
pixels can come from different acquisition days, so a short-lived flood may
not appear consistently throughout a window. The map and export metadata
identify the window dates; neither should be described as a single-date image.

### Polarization and ratio

Earth Engine's dual-polarization Sentinel-1 GRD scenes provide VV+VH or HH+HV,
not HH+VH. The implementation uses VV and VH and derives a VH/VV ratio in
linear power from their dB values:

```text
VH/VV = 10 ** ((VH_dB - VV_dB) / 10)
```

Display stretches are visualization parameters, not calibrated thresholds or
flood classifications.

### AOI validation

Drawn geometries must be valid polygons or multipolygons in longitude and
latitude ranges. The AOI is stored and sent to Earth Engine in EPSG:4326. A
changed AOI invalidates prior search results and comparisons so stale imagery
cannot be mistaken for results from the new geometry.

## External services and limits

- Earth Engine access requires user authentication and a registered Cloud
  project. Credentials are not collected in the app.
- Scene dates and coverage depend on the live Sentinel-1 catalog; the app does
  not guarantee a matching scene or suitable flood observation.
- Direct GeoTIFF downloads use Earth Engine's small-download endpoint. Large
  AOIs may exceed service limits; users can reduce the AOI and retry.
- The default AOI and suggested Pakistan-flood comparison dates are starting
  points. Verify that the area intersects the floodplain and inspect the
  imagery before drawing conclusions.

## Validation

The test suite checks polygon validation, the 60-day window boundaries,
non-overlapping date rules, rejection of invalid comparisons, and suggested
date-pair selection. Live Earth Engine queries and exports require credentials
and are not part of the offline test suite.
