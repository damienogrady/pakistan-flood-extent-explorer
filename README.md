# Sentinel-1 Flood Extent Explorer

A small, interactive Sentinel-1 flood-imagery explorer. Its default area of
interest is the polygon supplied in Sindh, Pakistan. Choose dates and compare
trailing mosaics or draw a different area. Imagery is requested from Google
Earth Engine (GEE); the map is not a flood-warning or operational mapping
product.

I first mapped floods using radar data back in 2011, using the very coarse
ENVISAT ASAR GM-mode [(you can see the article here)](https://hess.copernicus.org/articles/15/3475/2011/).
Back then, without a decent budget and without the power of GEE, such a process
was far more difficult and less precise than it is now.
If you are not yet set up with GEE, let me tell you that a new world awaits you.
Start at the [Google Earth Engine](https://earthengine.google.com/) project page,
and click **Get Started** at the top-right of the screen when you are ready to set
yourself up.

## What it shows

After you connect to Earth Engine, the app searches the Sentinel-1 archive for
the selected area and date range and suggests two matching dates when data is
available. For the 2022 Pakistan flood demonstration, the suggested end dates
are **May 15, 2022** (pre-flood baseline) and **September 5, 2022**
(flood-period mosaic), if matching acquisitions exist. Each date ends a trailing
60-calendar-day mosaic: March 17–May 15 and July 8–September 5, respectively.
The date selectors remain available, and matching acquisitions are discovered
from the live archive.

The [UN Office for the Coordination of Humanitarian Affairs (OCHA)](https://www.unocha.org/pakistan)
describes the 2022 Pakistan floods as historic and affecting Sindh. These are
representative comparison windows, not exact flood-peak snapshots.
The supplied area is in Sindh near Karachi and may not include the main Indus
channel or the worst-affected floodplain. Confirm flood extent in the selected
area from the imagery rather than assuming it from the date alone.

Each false-colour composite contains:

1. VV backscatter (red channel)
2. VH backscatter (green channel)
3. VH/VV backscatter ratio (blue channel)

Earth Engine's Sentinel-1 GRD collection
provides dual-polarization scenes as VV+VH or HH+HV. The app uses the available VV+VH pair for this area and
calculates the ratio from the two dB bands in linear power.

Each mosaic is assembled from same-track scenes in the 60 days ending on its
selected date. The newest valid observation is used at each pixel to fill gaps
between scene footprints. This improves spatial coverage but means a mosaic is
not a single-date snapshot. Use the vertical swipe divider to compare them.
For another analysis, draw a rectangle or polygon, search for available mosaic
end dates, choose two dates at least 60 days apart on the same orbit track, and
run the comparison. You can optionally download both clipped three-band
mosaics as GeoTIFFs in a ZIP archive.

## Requirements

- Python 3.10 or later
- A Google account with access to Earth Engine
- A Google Cloud project registered for Earth Engine, with the Earth Engine
  API enabled

Earth Engine requires authentication and a Cloud project. Review Google's
[Earth Engine access setup](https://developers.google.com/earth-engine/guides/access)
and [Python installation guide](https://developers.google.com/earth-engine/guides/python_install)
before running the app.

## Setup

Run these commands from the repository root. The project already includes a
`.venv` environment; if you are setting it up on another machine, create it
with `python -m venv .venv` first.

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Authenticate once from a terminal:

```bash
earthengine authenticate
```

Set the Cloud project ID in your shell (or copy `.env.example` as a reference;
the app does not load `.env` automatically):

```bash
export GEE_PROJECT="your-earth-engine-project-id"
```

For PowerShell:

```powershell
$env:GEE_PROJECT = "your-earth-engine-project-id"
```

Start the app:

```bash
streamlit run src/flood_mapper/app.py
```

Enter the Cloud project ID in the app if you did not set `GEE_PROJECT`, then
select **Connect to Earth Engine**. Authentication is performed in the
terminal, not in the browser. The app reports an initialization error if the
account or project is not configured.

## Using the explorer

1. Read the short workflow overview and connect to Earth Engine.
2. Keep the default 2022 flood-period date range or choose another range of mosaic
   end dates.
3. Pan and zoom the map, then draw a rectangle or polygon for the area of
   interest. If you do not draw a shape, the supplied default polygon in Sindh,
   Pakistan is used.
4. Select **Find mosaic dates**. The app lists dates with matching Sentinel-1
   acquisitions for the area and date range. It suggests dates near May 15 and
   September 5, 2022, when compatible scenes are available.
5. Choose two mosaic end dates. The app requires at least 60 days between them
   and the same orbit direction and relative orbit number to reduce
   viewing-geometry differences.
6. Optionally select **Prepare GeoTIFF download** to get both composites and a
   metadata table in a ZIP archive.

The GeoTIFF endpoint is intended for small areas of interest; Earth Engine
limits the size of direct image downloads. If an export is too large, draw a
smaller area and try again.

## Project layout

```text
.
├── docs/                 # Design notes and data-method documentation
├── src/flood_mapper/     # Streamlit app and Earth Engine/data helpers
├── tests/                # Focused tests for area-of-interest handling
├── .env.example
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Data notes and limitations

- Source: Google Earth Engine's
  [COPERNICUS/S1_GRD collection](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD).
- The app filters to IW-mode acquisitions with both VV and VH. Each mosaic
  combines scenes from the 60 calendar days ending on its selected date, using
  the newest valid observation per pixel. The two windows do not overlap.
- Sentinel-1 GRD values in this collection are calibrated backscatter in dB.
  The ratio band is calculated as `10 ** ((VH - VV) / 10)`.
- Floodwater can be difficult to distinguish in built-up areas, under
  vegetation, or when wind, soil moisture, acquisition geometry, and
  processing choices differ. The composites are for demonstration and
  interpretation, not a validated flood classification.
- The default dates are intended to compare a pre-monsoon baseline with the
  September 2022 Pakistan flood period. They do not guarantee floodwater in the
  selected AOI or identify the exact flood peak. The app checks actual scene
  dates in the AOI and does not promise that every window has full coverage.
  A multi-week mosaic can include observations from before and after peak
  inundation.
- O’Grady, D., Leblanc, M., & Gillieson, D. (2011). *Use of ENVISAT ASAR Global Monitoring Mode to complement
  optical data in the mapping of rapid broad-scale flooding in Pakistan*. Hydrology and Earth System Sciences, 15,
  3475–3794. doi:10.5194/hess-15-3475-2011

## Development

```bash
pytest
```

See [the methods note](docs/methods.md) for the processing sequence and
interpretation guidance.
