"""Binary sensors for HA iOS NextAlarm refresh diagnostics."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
try:  # Home Assistant 2023.12+
    from homeassistant.util import slugify
except ImportError:  # pragma: no cover - fallback for older Home Assistant
    from homeassistant.util.slugify import slugify

from .const import DOMAIN
from .coordinator import NextAlarmCoordinator

DEVICE_MANUFACTURER = "Home Assistant Companion"


def _device_identifier(coordinator: NextAlarmCoordinator, slug: str) -> tuple[str, str]:
    """Return the identifier tuple for a person's device entry."""

    return (DOMAIN, f"{coordinator.entry.entry_id}_{slug}")


def _device_name(coordinator: NextAlarmCoordinator, slug: str) -> str:
    """Return the friendly name for a person's device."""

    state = coordinator.get_person_state(slug)
    if state and state.person:
        return state.person
    return slugify(slug)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up refresh problem binary sensors for a config entry."""

    coordinator: NextAlarmCoordinator = hass.data[DOMAIN][entry.entry_id]
    created: set[str] = set(coordinator.person_states)
    entities = [NextAlarmRefreshProblemBinarySensor(coordinator, slug) for slug in created]
    async_add_entities(entities)

    def _ensure_person(slug: str) -> None:
        if slug in created:
            return
        created.add(slug)
        async_add_entities([NextAlarmRefreshProblemBinarySensor(coordinator, slug)])

    remove = coordinator.async_add_person_listener(_ensure_person)
    entry.async_on_unload(remove)


class NextAlarmRefreshProblemBinarySensor(BinarySensorEntity):
    """Indicate refresh problems for a person."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "refresh_problem"
    _attr_has_entity_name = True

    def __init__(self, coordinator: NextAlarmCoordinator, slug: str) -> None:
        self._coordinator = coordinator
        self._slug = slug
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{slug}_refresh_problem"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        _async_update_device_registry(self.hass, self._coordinator, self._slug)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._coordinator.signal_person(self._slug), self._handle_update
            )
        )
        self._handle_update()

    @callback
    def _handle_update(self) -> None:
        _async_update_device_registry(self.hass, self._coordinator, self._slug)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        state = self._coordinator.get_person_state(self._slug)
        if not state:
            return None
        return state.refresh_problem

    @property
    def available(self) -> bool:
        return self._coordinator.get_person_state(self._slug) is not None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        state = self._coordinator.get_person_state(self._slug)
        if not state:
            return {}
        return {
            "source_person": state.person,
            "last_refresh_start": state.last_refresh_start.isoformat()
            if state.last_refresh_start
            else None,
            "last_refresh_end": state.last_refresh_end.isoformat()
            if state.last_refresh_end
            else None,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={_device_identifier(self._coordinator, self._slug)},
            manufacturer=DEVICE_MANUFACTURER,
            name=_device_name(self._coordinator, self._slug),
        )


def _async_update_device_registry(
    hass: HomeAssistant | None, coordinator: NextAlarmCoordinator, slug: str
) -> None:
    """Ensure a device exists for the person and update its metadata."""

    if hass is None:
        return
    name = _device_name(coordinator, slug)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=coordinator.entry.entry_id,
        identifiers={_device_identifier(coordinator, slug)},
        manufacturer=DEVICE_MANUFACTURER,
        name=name,
    )
    if device.name != name:
        registry.async_update_device(device.id, name=name)
