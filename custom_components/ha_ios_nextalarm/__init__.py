"""HA iOS NextAlarm integration setup."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import NextAlarmCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the HA iOS NextAlarm integration."""

    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA iOS NextAlarm from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    coordinator = NextAlarmCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("HA iOS NextAlarm entry %s set up", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    coordinator: NextAlarmCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_unload()
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    _LOGGER.debug("HA iOS NextAlarm entry %s unloaded", entry.entry_id)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update by reloading the config entry."""

    await hass.config_entries.async_reload(entry.entry_id)
