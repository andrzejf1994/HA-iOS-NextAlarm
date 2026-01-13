"""Sensor entities for the HA iOS NextAlarm integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
try:  # Home Assistant 2023.12+
    from homeassistant.util import slugify
except ImportError:  # pragma: no cover - fallback for older Home Assistant
    from homeassistant.util.slugify import slugify

from .const import ATTR_NOTE, DOMAIN, MAP_VERSION
from .coordinator import NextAlarmCoordinator, PersonState
from .helpers import build_normalized_preview, describe_time_until

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

NOTE_MESSAGES = {
    "no_alarms": "No alarms provided",
    "no_enabled": "No enabled alarms",
    "no_future": "No future alarms",
    "waiting": "Waiting for first event",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up NextAlarm sensors for a config entry."""

    coordinator: NextAlarmCoordinator = hass.data[DOMAIN][entry.entry_id]
    created: set[str] = set(coordinator.person_states)
    initial_entities = [
        NextAlarmSensor(coordinator, slug) for slug in created
    ] + [NextAlarmDiagnosticsSensor(coordinator, slug) for slug in created]
    async_add_entities(initial_entities)

    def _ensure_person(slug: str) -> None:
        if slug in created:
            return
        created.add(slug)
        async_add_entities(
            [
                NextAlarmSensor(coordinator, slug),
                NextAlarmDiagnosticsSensor(coordinator, slug),
            ]
        )

    remove = coordinator.async_add_person_listener(_ensure_person)
    entry.async_on_unload(remove)


def _note_text(state: PersonState | None) -> str | None:
    if state is None:
        return NOTE_MESSAGES["waiting"]
    if state.note is None:
        return None
    return NOTE_MESSAGES.get(state.note, state.note)


class NextAlarmSensor(RestoreEntity, SensorEntity):
    """Represents the next alarm timestamp."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_alarm"
    _attr_has_entity_name = True

    def __init__(self, coordinator: NextAlarmCoordinator, slug: str) -> None:
        self._coordinator = coordinator
        self._slug = slug
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{slug}_next"

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
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={_device_identifier(self._coordinator, self._slug)},
            manufacturer=DEVICE_MANUFACTURER,
            name=_device_name(self._coordinator, self._slug),
        )

    @property
    def available(self) -> bool:
        return self._coordinator.get_person_state(self._slug) is not None

    @property
    def native_value(self) -> datetime | None:
        state = self._coordinator.get_person_state(self._slug)
        return state.next_alarm_time if state else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._coordinator.get_person_state(self._slug)
        attributes: dict[str, Any] = {
            "source_person": state.person if state else self._slug,
            "map_version": state.map_version if state else MAP_VERSION,
            "weekday_map_locale": state.map_locale if state else None,
            ATTR_NOTE: _note_text(state),
        }
        if state and state.last_event_time:
            attributes["source_event_time"] = state.last_event_time.isoformat()
            attributes["source_event_time_local"] = dt_util.as_local(
                state.last_event_time
            ).isoformat()
        if state and state.last_refresh_start:
            attributes["last_refresh_start"] = state.last_refresh_start.isoformat()
            attributes["last_refresh_start_local"] = dt_util.as_local(
                state.last_refresh_start
            ).isoformat()
        if state and state.last_refresh_end:
            attributes["last_refresh_end"] = state.last_refresh_end.isoformat()
            attributes["last_refresh_end_local"] = dt_util.as_local(
                state.last_refresh_end
            ).isoformat()
        if state and state.previous_alarm_time:
            attributes["previous_alarm_time"] = state.previous_alarm_time.isoformat()
            localized_previous = dt_util.as_local(state.previous_alarm_time)
            attributes["previous_alarm_time_local"] = localized_previous.isoformat()
            attributes["previous_alarm_date_local"] = localized_previous.date().isoformat()
            attributes["previous_alarm_clock_time_local"] = localized_previous.strftime(
                "%H:%M:%S"
            )
        if state and state.previous_alarm_key:
            attributes["previous_alarm_key"] = state.previous_alarm_key
        if state and state.next_alarm_time:
            attributes["time_until"] = describe_time_until(state.next_alarm_time)
            localized_alarm = dt_util.as_local(state.next_alarm_time)
            attributes["next_alarm_time_local"] = localized_alarm.isoformat()
            attributes["next_alarm_date_local"] = localized_alarm.date().isoformat()
            attributes["next_alarm_clock_time_local"] = localized_alarm.strftime(
                "%H:%M:%S"
            )
        if state and state.next_alarm_key:
            alarm = state.normalized_alarms.get(state.next_alarm_key)
            if alarm:
                attributes.update(
                    {
                        "label": alarm.label,
                        "enabled": alarm.enabled,
                        "repeat": alarm.repeat,
                        "repeat_days_localized": list(alarm.repeat_days_localized),
                        "repeat_days_normalized": list(alarm.repeat_days_normalized),
                        "snooze": alarm.snooze,
                        "source_alarm_key": alarm.key,
                    }
                )
        if not state or not state.next_alarm_time:
            attributes.setdefault(ATTR_NOTE, _note_text(state))
        return attributes


class NextAlarmDiagnosticsSensor(RestoreEntity, SensorEntity):
    """Diagnostics sensor exposing the raw event payload."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "next_alarm_diagnostics"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NextAlarmCoordinator, slug: str) -> None:
        self._coordinator = coordinator
        self._slug = slug
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{slug}_diagnostics"

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
    def native_value(self) -> str | None:
        state = self._coordinator.get_person_state(self._slug)
        if not state or not state.last_event_time:
            return None
        return state.last_event_time.isoformat()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._coordinator.get_person_state(self._slug)
        if not state:
            return {
                ATTR_NOTE: _note_text(None),
                "map_version": MAP_VERSION,
                "weekday_map_locale": None,
            }
        attributes: dict[str, Any] = {
            ATTR_NOTE: _note_text(state),
            "map_version": state.map_version,
            "weekday_map_locale": state.map_locale,
            "next_alarm_key": state.next_alarm_key,
            "next_alarm_time": state.next_alarm_time.isoformat()
            if state.next_alarm_time
            else None,
            "previous_alarm_key": state.previous_alarm_key,
            "previous_alarm_time": state.previous_alarm_time.isoformat()
            if state.previous_alarm_time
            else None,
            "source_person": state.person,
            "parse_errors": list(state.parse_errors),
            "map_errors": list(state.map_errors),
            "normalized_preview": build_normalized_preview(
                state.normalized_alarms, state.schedule
            ),
            "refresh_problem": state.refresh_problem,
        }
        if state.last_refresh_start:
            attributes["last_refresh_start"] = state.last_refresh_start.isoformat()
            attributes["last_refresh_start_local"] = dt_util.as_local(
                state.last_refresh_start
            ).isoformat()
        if state.last_refresh_end:
            attributes["last_refresh_end"] = state.last_refresh_end.isoformat()
            attributes["last_refresh_end_local"] = dt_util.as_local(
                state.last_refresh_end
            ).isoformat()
        if state.last_event_time:
            attributes["last_event_time_local"] = dt_util.as_local(
                state.last_event_time
            ).isoformat()
        if state.next_alarm_time:
            localized_alarm = dt_util.as_local(state.next_alarm_time)
            attributes["next_alarm_time_local"] = localized_alarm.isoformat()
            attributes["next_alarm_date_local"] = localized_alarm.date().isoformat()
            attributes["next_alarm_clock_time_local"] = localized_alarm.strftime(
                "%H:%M:%S"
            )
        if state.previous_alarm_time:
            localized_previous = dt_util.as_local(state.previous_alarm_time)
            attributes["previous_alarm_time_local"] = localized_previous.isoformat()
            attributes["previous_alarm_date_local"] = localized_previous.date().isoformat()
            attributes["previous_alarm_clock_time_local"] = localized_previous.strftime(
                "%H:%M:%S"
            )
        if state.raw_event:
            attributes["event"] = state.raw_event
        return attributes

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={_device_identifier(self._coordinator, self._slug)},
            manufacturer=DEVICE_MANUFACTURER,
            name=_device_name(self._coordinator, self._slug),
        )
