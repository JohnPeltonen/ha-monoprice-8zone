"""Constants for the Monoprice 8-Zone Amplifier (44518) integration."""

from datetime import timedelta

DOMAIN = "monoprice_8zone"

CONF_ZONES = "zones"
CONF_SOURCES = "sources"

ZONES = (1, 2, 3, 4, 5, 6, 7, 8)
SOURCES = (1, 2, 3, 4, 5, 6)

SCAN_INTERVAL = timedelta(seconds=30)
