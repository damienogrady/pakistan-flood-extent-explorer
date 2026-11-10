# Methods and interpretation

## Default area and date range

The default area is the user-supplied polygon in Sindh, Pakistan. The initial
search range is March 1 to October 31, 2022. The app prefers a May 15 pre-flood
baseline and a September 5 flood-period window end when matching acquisitions
exist on the same orbit track. These are representative dates around the major
2022 Pakistan monsoon floods, not a claim that either date captures the local
flood peak. The supplied AOI is in Sindh near Karachi and may not cover the
main Indus channel or the worst-affected floodplain; check actual imagery and
local event records before interpreting it.
OCHA's [Pakistan response overview](https://www.unocha.org/pakistan) describes
the 2022 floods as a historic event affecting Sindh.

Sentinel-1 has a nominal six-day revisit with both satellites operating, but
the usable pass over a particular area can be less frequent. The flood peak
does not necessarily coincide with a satellite overpass. The 60-day mosaics
are not single-date snapshots; compare their temporal windows with local event
reporting before interpreting them.

The suggested baseline window is March 17–May 15, 2022. The suggested
flood-period window is July 8–September 5, 2022. Their end dates are 113 days
apart, so the 60-day windows do not overlap.

## Scene selection and mosaicking

The Earth Engine query uses `COPERNICUS/S1_GRD`, Interferometric Wide (IW)
mode, and scenes containing both VV and VH. A selected date is the inclusive
end of a 60-calendar-day window. Within that window, the app filters to the
selected orbit direction and relative orbit number, sorts by acquisition time,
and mosaics the scenes. Earth Engine's mosaic gives priority to the newest
valid pixel and fills masked areas from earlier scenes. This improves spatial
coverage when individual scenes have incomplete footprints, but can mix
acquisition dates spatially.

The two selected window end dates must be at least 60 days apart. Because each
window contains 60 calendar dates including its end date, this keeps the
compositing windows from overlapping. Comparisons also require the same orbit
direction and relative orbit number to reduce viewing-geometry differences.
The date selectors are mosaic window end dates, not single acquisition dates.

## Composite bands

Sentinel-1 GRD bands are expressed in decibels. The displayed three-band
composite is:

| Channel | Input |
|---|---|
| Red | VV backscatter (dB) |
| Green | VH backscatter (dB) |
| Blue | VH/VV ratio in linear power |

The VV and VH channels are mosaicked separately. For their resulting dB values
`VV` and `VH`, the linear ratio is `10 ** ((VH - VV) / 10)`.
The map uses fixed visualization ranges to make the two dates easier to
compare. Those display stretches are not calibrated measurements.

Sentinel-1's dual-polarization combinations are VV+VH and HH+HV. The app uses
VV+VH for the default area.

## Caveats

Open water often appears dark in SAR imagery because it reflects energy away
from the sensor, but this is not a universal flood signature. Urban structures,
vegetation, wind-roughened water, shadow, terrain, and acquisition geometry
can complicate interpretation (see my article [here](https://link.springer.com/article/10.1007/s00477-013-0712-3) for more about complications
mapping floods in Australia\*).
The 60-day mosaics are not snapshots: a short flood event may be blended
spatially with observations from before or after the peak, depending on scene
coverage. The app does not apply a permanent-water mask, terrain correction
beyond the source product's processing, or a validated classification model.

Direct GeoTIFF exports use Earth Engine's small-download endpoint and may be
rejected for large areas. Reduce the drawn AOI if an export exceeds the
service's limits.

\* **O’Grady, D., & Leblanc, M. (2013).** *Radar mapping of broad-scale inundation:
challenges and opportunities in Australia*. Stochastic Environmental Research
and Risk Assessment, 28 (1), 29–38 doi:10.1007/s00477-013-0712-3