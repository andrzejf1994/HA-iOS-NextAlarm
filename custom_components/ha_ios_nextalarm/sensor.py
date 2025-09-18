"""Sensor entities for the HA iOS NextAlarm integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity
try:  # Home Assistant 2023.12+
    from homeassistant.util import slugify
except ImportError:  # pragma: no cover - fallback for older Home Assistant
    from homeassistant.util.slugify import slugify

from .const import ATTR_NOTE, DOMAIN, MAP_VERSION
from .coordinator import NextAlarmCoordinator, PersonState
from .helpers import build_normalized_preview, describe_time_until

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
    created: set[str] = set()

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
        self.entity_id = f"sensor.{slug}_next_alarm"
        self._attr_unique_id = f"ha_ios_nextalarm_next_{slug}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._coordinator.signal_person(self._slug), self._handle_update
            )
        )
        self._handle_update()

    @callback
    def _handle_update(self) -> None:
        state = self._coordinator.get_person_state(self._slug)
        if state:
            self._attr_name = state.person
        else:
            self._attr_name = slugify(self._slug)
        self.async_write_ha_state()

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
        if state and state.next_alarm_time:
            attributes["time_until"] = describe_time_until(state.next_alarm_time)
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
        self.entity_id = f"sensor.{slug}_next_alarm_diagnostics"
        self._attr_unique_id = f"ha_ios_nextalarm_diag_{slug}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._coordinator.signal_person(self._slug), self._handle_update
            )
        )
        self._handle_update()

    @callback
    def _handle_update(self) -> None:
        state = self._coordinator.get_person_state(self._slug)
        if state:
            self._attr_name = state.person
        else:
            self._attr_name = slugify(self._slug)
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
            "source_person": state.person,
            "parse_errors": list(state.parse_errors),
            "map_errors": list(state.map_errors),
            "normalized_preview": build_normalized_preview(
                state.normalized_alarms, state.schedule
            ),
        }
        if state.raw_event:
            attributes["event"] = state.raw_event
        return attributes
