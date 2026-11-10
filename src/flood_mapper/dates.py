"""Date rules for trailing-window Sentinel-1 mosaics."""

from datetime import date, timedelta

MOSAIC_WINDOW_DAYS = 60
MIN_COMPARISON_GAP_DAYS = MOSAIC_WINDOW_DAYS


def mosaic_window_start(window_end: date) -> date:
    """Return the inclusive start date for a 60-calendar-day window."""
    return window_end - timedelta(days=MOSAIC_WINDOW_DAYS - 1)


def comparison_dates_are_valid(first_end: date, second_end: date) -> bool:
    """Require chronological, non-overlapping trailing mosaic windows."""
    return (second_end - first_end).days >= MIN_COMPARISON_GAP_DAYS
