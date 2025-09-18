"""Constants for the HA iOS NextAlarm integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "ha_ios_nextalarm"
PLATFORMS: Final = [Platform.SENSOR]
EVENT_NEXT_ALARM: Final = "ha_ios_nextalarm"

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = DOMAIN

SIGNAL_PERSON_UPDATED: Final = f"{DOMAIN}_person_updated"

CONF_WEEKDAY_LOCALE: Final = "weekday_locale"
CONF_WEEKDAY_CUSTOM_MAP: Final = "weekday_custom_map"

DEFAULT_WEEKDAY_LOCALE: Final = "auto"
DEFAULT_CUSTOM_MAP: Final = "{}"
DEFAULT_OPTIONS: Final = {
    CONF_WEEKDAY_LOCALE: DEFAULT_WEEKDAY_LOCALE,
    CONF_WEEKDAY_CUSTOM_MAP: DEFAULT_CUSTOM_MAP,
}

MAP_VERSION: Final = 1

STR_ONOFF: Final = {"on": True, "off": False}

WEEKDAY_MAPS: Final = {
    "en": {
        "monday": 0,
        "mon": 0,
        "tuesday": 1,
        "tue": 1,
        "wednesday": 2,
        "wed": 2,
        "thursday": 3,
        "thu": 3,
        "friday": 4,
        "fri": 4,
        "saturday": 5,
        "sat": 5,
        "sunday": 6,
        "sun": 6,
    },
    "pl": {
        "poniedzialek": 0,
        "pon": 0,
        "poniedziałek": 0,
        "wtorek": 1,
        "wt": 1,
        "sroda": 2,
        "środa": 2,
        "sr": 2,
        "czwartek": 3,
        "czw": 3,
        "piatek": 4,
        "piątek": 4,
        "pt": 4,
        "sobota": 5,
        "sob": 5,
        "niedziela": 6,
        "nd": 6,
        "nie": 6,
    },
}

OPTION_WEEKDAY_LOCALES: Final = [DEFAULT_WEEKDAY_LOCALE, *sorted(WEEKDAY_MAPS)]

ATTR_NOTE: Final = "note"

PREVIEW_LIMIT: Final = 5
