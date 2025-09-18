"""Coordinator for HA iOS NextAlarm integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.slugify import slugify

from .const import (
    CONF_WEEKDAY_CUSTOM_MAP,
    CONF_WEEKDAY_LOCALE,
    DEFAULT_OPTIONS,
    EVENT_NEXT_ALARM,
    MAP_VERSION,
    SIGNAL_PERSON_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from . import helpers

_LOGGER = logging.getLogger(__name__)


@dataclass
class PersonState:
    """Runtime state for a person."""

    slug: str
    person: str
    normalized_alarms: dict[str, helpers.NormalizedAlarm] = field(default_factory=dict)
    parse_errors: list[str] = field(default_factory=list)
    map_errors: list[str] = field(default_factory=list)
    map_locale: str | None = None
    last_event_time: datetime | None = None
    raw_event: dict[str, Any] | None = None
    next_alarm_key: str | None = None
    next_alarm_time: datetime | None = None
    note: str | None = None
    schedule: dict[str, datetime | None] = field(default_factory=dict)
    timer_cancel: CALLBACK_TYPE | None = None
    map_version: int = MAP_VERSION

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation safe for storage."""

        return {
            "person": self.person,
            "normalized_alarms": {
                key: alarm.to_dict() for key, alarm in self.normalized_alarms.items()
            },
            "parse_errors": list(self.parse_errors),
            "map_errors": list(self.map_errors),
            "map_locale": self.map_locale,
            "last_event_time": self.last_event_time.isoformat()
            if self.last_event_time
            else None,
            "raw_event": self.raw_event,
            "next_alarm_key": self.next_alarm_key,
            "next_alarm_time": self.next_alarm_time.isoformat()
            if self.next_alarm_time
            else None,
            "note": self.note,
            "schedule": {
                key: value.isoformat() if value else None
                for key, value in self.schedule.items()
            },
            "map_version": self.map_version,
        }

    @classmethod
    def from_dict(cls, slug: str, data: dict[str, Any]) -> "PersonState":
        """Restore a person state from storage."""

        normalized_alarms = {
            key: helpers.NormalizedAlarm.from_dict(value)
            for key, value in data.get("normalized_alarms", {}).items()
        }
        last_event_time = dt_util.parse_datetime(data.get("last_event_time"))
        next_alarm_time = dt_util.parse_datetime(data.get("next_alarm_time"))
        schedule: dict[str, datetime | None] = {}
        for key, value in data.get("schedule", {}).items():
            schedule[key] = dt_util.parse_datetime(value) if value else None
        return cls(
            slug=slug,
            person=str(data.get("person", slug)),
            normalized_alarms=normalized_alarms,
            parse_errors=list(data.get("parse_errors", [])),
            map_errors=list(data.get("map_errors", [])),
            map_locale=data.get("map_locale"),
            last_event_time=last_event_time,
            raw_event=data.get("raw_event"),
            next_alarm_key=data.get("next_alarm_key"),
            next_alarm_time=next_alarm_time,
            note=data.get("note"),
            schedule=schedule,
            map_version=int(data.get("map_version", MAP_VERSION)),
        )


class NextAlarmCoordinator:
    """Coordinator responsible for processing incoming events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator."""

        self.hass = hass
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._person_states: dict[str, PersonState] = {}
        self._person_listeners: list[Callable[[str], None]] = []
        self._remove_listener: CALLBACK_TYPE | None = None
        self._lock = asyncio.Lock()

    @property
    def persons(self) -> list[str]:
        """Return the known person identifiers."""

        return list(self._person_states)

    def get_person_state(self, slug: str) -> PersonState | None:
        """Return the state for a given person."""

        return self._person_states.get(slug)

    def signal_person(self, slug: str) -> str:
        """Return the dispatcher signal for a person."""

        return f"{SIGNAL_PERSON_UPDATED}_{self.entry.entry_id}_{slug}"

    async def async_setup(self) -> None:
        """Set up the coordinator."""

        await self._async_load_storage()
        self._remove_listener = self.hass.bus.async_listen(
            EVENT_NEXT_ALARM, self._async_handle_event
        )
        _LOGGER.debug("Listening for %s events", EVENT_NEXT_ALARM)

    async def async_unload(self) -> None:
        """Tear down the coordinator."""

        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        for state in self._person_states.values():
            if state.timer_cancel:
                state.timer_cancel()
                state.timer_cancel = None
        await self._store.async_save(self._storage_payload())

    def async_add_person_listener(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Register a callback for new persons."""

        self._person_listeners.append(listener)
        for slug in self._person_states:
            listener(slug)

        def _remove() -> None:
            self._person_listeners.remove(listener)

        return _remove

    async def _async_load_storage(self) -> None:
        """Load previously stored state."""

        data = await self._store.async_load()
        if not data:
            return
        persons: dict[str, Any] = data.get("persons", {})
        for slug, stored in persons.items():
            try:
                state = PersonState.from_dict(slug, stored)
            except Exception as err:  # pragma: no cover - safety net
                _LOGGER.warning("Failed to restore state for %s: %s", slug, err)
                continue
            self._person_states[slug] = state
            reference_now = dt_util.utcnow()
            if state.next_alarm_time and reference_now <= state.next_alarm_time:
                near_time = state.next_alarm_time - timedelta(seconds=1)
                computation = helpers.compute_next_alarm(
                    state.normalized_alarms, near_time, self._timezone
                )
                state.next_alarm_key = computation.alarm.key if computation.alarm else None
                state.next_alarm_time = computation.next_time
                state.note = computation.note
                state.schedule = computation.schedule
            else:
                self._refresh_schedule(state, reference_time=reference_now)
            self._schedule_rollover(state)

    @property
    def _timezone(self):
        tz_name = self.hass.config.time_zone
        timezone = dt_util.get_time_zone(tz_name) if tz_name else None
        return timezone or dt_util.UTC

    def _current_options(self) -> dict[str, Any]:
        options = dict(DEFAULT_OPTIONS)
        options.update(self.entry.options)
        return options

    async def _async_handle_event(self, event: Event) -> None:
        """Handle an incoming NextAlarm event."""

        async with self._lock:
            await self._async_process_event(event)

    async def _async_process_event(self, event: Event) -> None:
        person_raw = event.data.get("person")
        if not person_raw:
            _LOGGER.warning("Received %s event without person", EVENT_NEXT_ALARM)
            return
        alarms = event.data.get("alarms")
        if not isinstance(alarms, dict):
            _LOGGER.warning("Event for %s does not contain alarm dictionary", person_raw)
            return

        slug = slugify(str(person_raw)) or str(person_raw).strip().casefold()
        if slug not in self._person_states:
            self._person_states[slug] = PersonState(slug=slug, person=str(person_raw))
            self._notify_new_person(slug)
        state = self._person_states[slug]
        state.person = str(person_raw)

        options = self._current_options()
        maps, map_errors = helpers.build_weekday_maps(
            options.get(CONF_WEEKDAY_CUSTOM_MAP, DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP])
        )
        if map_errors:
            _LOGGER.warning("Custom weekday map issues: \n%s", "\n".join(map_errors))

        normalized = helpers.normalize_event(
            alarms=alarms,
            tzinfo=self._timezone,
            locale_option=options.get(CONF_WEEKDAY_LOCALE, DEFAULT_OPTIONS[CONF_WEEKDAY_LOCALE]),
            maps=maps,
            map_errors=map_errors,
        )
        now = dt_util.utcnow()
        computation = helpers.compute_next_alarm(
            normalized.alarms, now, self._timezone
        )

        state.normalized_alarms = normalized.alarms
        state.parse_errors = normalized.parse_errors
        state.map_errors = list(normalized.map_errors)
        state.map_locale = normalized.map_locale
        state.last_event_time = event.time_fired
        state.next_alarm_key = computation.alarm.key if computation.alarm else None
        state.next_alarm_time = computation.next_time
        state.note = computation.note
        state.schedule = computation.schedule
        state.map_version = MAP_VERSION
        state.raw_event = {
            "event_type": event.event_type,
            "origin": event.origin,
            "time_fired": event.time_fired.isoformat(),
            "context": helpers.ensure_serializable(event.context.as_dict()),
            "data": helpers.ensure_serializable(event.data),
        }

        self._schedule_rollover(state)
        await self._store.async_save(self._storage_payload())
        _LOGGER.debug(
            "Processed NextAlarm event for %s; next alarm %s",
            state.person,
            state.next_alarm_time,
        )
        self._notify_person_update(slug)

    def _notify_new_person(self, slug: str) -> None:
        for listener in list(self._person_listeners):
            listener(slug)

    def _notify_person_update(self, slug: str) -> None:
        async_dispatcher_send(self.hass, self.signal_person(slug))

    def _schedule_rollover(self, state: PersonState) -> None:
        if state.timer_cancel:
            state.timer_cancel()
            state.timer_cancel = None
        if not state.next_alarm_time:
            return

        @callback
        def _fire(now: datetime) -> None:
            self.hass.async_create_task(self._async_rollover(state.slug, now))

        state.timer_cancel = async_track_point_in_time(
            self.hass, _fire, state.next_alarm_time
        )

    async def _async_rollover(self, slug: str, trigger_time: datetime | None = None) -> None:
        state = self._person_states.get(slug)
        if not state:
            return
        state.timer_cancel = None
        self._refresh_schedule(state, reference_time=trigger_time)
        self._schedule_rollover(state)
        await self._store.async_save(self._storage_payload())
        _LOGGER.debug("Rollover executed for %s", state.person)
        self._notify_person_update(slug)

    def _refresh_schedule(self, state: PersonState, reference_time: datetime | None = None) -> None:
        if not state.normalized_alarms:
            state.next_alarm_key = None
            state.next_alarm_time = None
            state.note = "no_alarms"
            state.schedule = {}
            return
        now = reference_time or dt_util.utcnow()
        computation = helpers.compute_next_alarm(
            state.normalized_alarms, now, self._timezone
        )
        state.next_alarm_key = computation.alarm.key if computation.alarm else None
        state.next_alarm_time = computation.next_time
        state.note = computation.note
        state.schedule = computation.schedule
        state.map_version = MAP_VERSION

    def build_preview(self, state: PersonState) -> list[dict[str, Any]]:
        """Expose helper for diagnostics sensor."""

        return helpers.build_normalized_preview(state.normalized_alarms, state.schedule)

    def describe_time_until(self, state: PersonState) -> str | None:
        """Return a human-friendly delta for the next alarm."""

        return helpers.describe_time_until(state.next_alarm_time)

    def time_zone(self):
        return self._timezone

    def _storage_payload(self) -> dict[str, Any]:
        return {"persons": {slug: state.as_dict() for slug, state in self._person_states.items()}}
