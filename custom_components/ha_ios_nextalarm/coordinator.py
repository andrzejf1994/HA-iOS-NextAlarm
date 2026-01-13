"""Coordinator for HA iOS NextAlarm integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo  # Import tzinfo for explicit return typing.
import logging
import uuid
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
try:  # Home Assistant 2023.12+
    from homeassistant.util import slugify
except ImportError:  # pragma: no cover - fallback for older Home Assistant
    from homeassistant.util.slugify import slugify

from .const import (
    CONF_REFRESH_TIMEOUT,
    CONF_WEEKDAY_CUSTOM_MAP,
    CONF_WEEKDAY_LOCALE,
    DEFAULT_OPTIONS,
    EVENT_NEXT_ALARM,
    EVENT_REFRESH_START,
    MAP_VERSION,
    SIGNAL_PERSON_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
    STR_ONOFF,
)
from . import helpers

_LOGGER = logging.getLogger(__name__)


def _log_restore_field_error(
    person: str,
    slug: str,
    field: str,
    raw_value: Any,
    error: str | Exception,
) -> None:
    _LOGGER.debug(
        "Restore field failed: person=%s, slug=%s, field=%s, raw_value=%r, type=%s, error=%s",
        person,
        slug,
        field,
        raw_value,
        type(raw_value),
        error,
    )


def _restore_str(
    person: str,
    slug: str,
    field: str,
    raw_value: Any,
    default: str | None,
) -> str | None:
    if raw_value is None:
        return default
    if isinstance(raw_value, str):
        return raw_value
    _log_restore_field_error(person, slug, field, raw_value, "expected str or None")
    return default


def _restore_list(
    person: str,
    slug: str,
    field: str,
    raw_value: Any,
    default: list[Any],
) -> list[Any]:
    if raw_value is None:
        return list(default)
    if isinstance(raw_value, list):
        return list(raw_value)
    if isinstance(raw_value, tuple):
        return list(raw_value)
    _log_restore_field_error(person, slug, field, raw_value, "expected list or tuple")
    return list(default)


def _restore_mapping(
    person: str,
    slug: str,
    field: str,
    raw_value: Any,
    default: Mapping[str, Any],
) -> dict[str, Any]:
    if raw_value is None:
        return dict(default)
    if isinstance(raw_value, Mapping):
        return dict(raw_value)
    _log_restore_field_error(person, slug, field, raw_value, "expected mapping")
    return dict(default)


def _restore_datetime(
    person: str,
    slug: str,
    field: str,
    raw_value: Any,
) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, str):
        parsed = dt_util.parse_datetime(raw_value)
        if parsed is None:
            _log_restore_field_error(
                person,
                slug,
                field,
                raw_value,
                "unparseable datetime string",
            )
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.UTC)
            _LOGGER.warning(
                "Restored naive datetime for %s.%s, assuming UTC: %s",
                person,
                field,
                parsed,
            )
        return parsed
    _log_restore_field_error(person, slug, field, raw_value, "expected str or datetime")
    return None


def _restore_int(
    person: str,
    slug: str,
    field: str,
    raw_value: Any,
    default: int,
) -> int:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        _log_restore_field_error(person, slug, field, raw_value, "expected int")
        return default
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError as err:
            _log_restore_field_error(person, slug, field, raw_value, err)
            return default
    _log_restore_field_error(person, slug, field, raw_value, "expected int or str")
    return default


def _restore_bool(
    person: str,
    slug: str,
    field: str,
    raw_value: Any,
    default: bool,
) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, int):
        return bool(raw_value)
    if isinstance(raw_value, str):
        normalized = raw_value.strip().casefold()
        if normalized in STR_ONOFF:
            return STR_ONOFF[normalized]
        if normalized in {"true", "false"}:
            return normalized == "true"
        _log_restore_field_error(person, slug, field, raw_value, "invalid boolean string")
        return default
    _log_restore_field_error(person, slug, field, raw_value, "expected bool or str")
    return default


def _person_slug(person_raw: str) -> str:
    """Normalize a person identifier for internal use."""

    person = str(person_raw)
    return slugify(person) or person.casefold()


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
    previous_alarm_key: str | None = None
    previous_alarm_time: datetime | None = None
    note: str | None = None
    schedule: dict[str, datetime | None] = field(default_factory=dict)
    timer_cancel: CALLBACK_TYPE | None = None
    map_version: int = MAP_VERSION
    last_refresh_start: datetime | None = None
    last_refresh_end: datetime | None = None
    refresh_problem: bool = False
    refresh_timer_cancel: CALLBACK_TYPE | None = None
    refresh_timeout_token: str | None = None

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
            "previous_alarm_key": self.previous_alarm_key,
            "previous_alarm_time": self.previous_alarm_time.isoformat()
            if self.previous_alarm_time
            else None,
            "note": self.note,
            "schedule": {
                key: value.isoformat() if value else None
                for key, value in self.schedule.items()
            },
            "map_version": self.map_version,
            "last_refresh_start": self.last_refresh_start.isoformat()
            if self.last_refresh_start
            else None,
            "last_refresh_end": self.last_refresh_end.isoformat()
            if self.last_refresh_end
            else None,
        }

    @classmethod
    def from_dict(cls, slug: str, data: dict[str, Any]) -> "PersonState":
        """Restore a person state from storage."""
        person = _restore_str(slug, slug, "person", data.get("person"), slug) or slug
        normalized_alarms: dict[str, helpers.NormalizedAlarm] = {}
        raw_alarms = _restore_mapping(person, slug, "normalized_alarms", data.get("normalized_alarms"), {})
        for alarm_key, alarm_data in raw_alarms.items():
            field_prefix = f"normalized_alarms.{alarm_key}"
            if not isinstance(alarm_data, Mapping):
                _log_restore_field_error(
                    person,
                    slug,
                    field_prefix,
                    alarm_data,
                    "expected mapping",
                )
                continue
            base_time = _restore_datetime(
                person,
                slug,
                f"{field_prefix}.base_time",
                alarm_data.get("base_time"),
            )
            if base_time is None:
                _log_restore_field_error(
                    person,
                    slug,
                    f"{field_prefix}.base_time",
                    alarm_data.get("base_time"),
                    "missing or invalid base_time",
                )
                continue
            alarm_payload = {
                "key": _restore_str(
                    person,
                    slug,
                    f"{field_prefix}.key",
                    alarm_data.get("key"),
                    str(alarm_key),
                )
                or str(alarm_key),
                "label": _restore_str(
                    person,
                    slug,
                    f"{field_prefix}.label",
                    alarm_data.get("label"),
                    "",
                )
                or "",
                "enabled": _restore_bool(
                    person,
                    slug,
                    f"{field_prefix}.enabled",
                    alarm_data.get("enabled"),
                    False,
                ),
                "repeat": _restore_bool(
                    person,
                    slug,
                    f"{field_prefix}.repeat",
                    alarm_data.get("repeat"),
                    False,
                ),
                "snooze": _restore_bool(
                    person,
                    slug,
                    f"{field_prefix}.snooze",
                    alarm_data.get("snooze"),
                    False,
                ),
                "base_time": base_time,
                "repeat_days_localized": _restore_list(
                    person,
                    slug,
                    f"{field_prefix}.repeat_days_localized",
                    alarm_data.get("repeat_days_localized"),
                    [],
                ),
                "repeat_days_normalized": _restore_list(
                    person,
                    slug,
                    f"{field_prefix}.repeat_days_normalized",
                    alarm_data.get("repeat_days_normalized"),
                    [],
                ),
            }
            try:
                normalized_alarms[str(alarm_key)] = helpers.NormalizedAlarm.from_dict(
                    alarm_payload
                )
            except Exception as err:  # pragma: no cover - safety net
                _log_restore_field_error(person, slug, field_prefix, alarm_payload, err)
        last_event_time = _restore_datetime(
            person,
            slug,
            "last_event_time",
            data.get("last_event_time"),
        )
        next_alarm_time = _restore_datetime(
            person,
            slug,
            "next_alarm_time",
            data.get("next_alarm_time"),
        )
        previous_alarm_time = _restore_datetime(
            person,
            slug,
            "previous_alarm_time",
            data.get("previous_alarm_time"),
        )
        last_refresh_start = _restore_datetime(
            person,
            slug,
            "last_refresh_start",
            data.get("last_refresh_start"),
        )
        last_refresh_end = _restore_datetime(
            person,
            slug,
            "last_refresh_end",
            data.get("last_refresh_end"),
        )
        schedule: dict[str, datetime | None] = {}
        raw_schedule = _restore_mapping(person, slug, "schedule", data.get("schedule"), {})
        for key, value in raw_schedule.items():
            if not isinstance(key, str):
                _log_restore_field_error(person, slug, "schedule", key, "expected str key")
                continue
            schedule[key] = _restore_datetime(
                person,
                slug,
                f"schedule.{key}",
                value,
            )
        raw_event = data.get("raw_event")
        if raw_event is None:
            raw_event_value = None
        elif isinstance(raw_event, Mapping):
            raw_event_value = dict(raw_event)
        else:
            _log_restore_field_error(person, slug, "raw_event", raw_event, "expected mapping")
            raw_event_value = None

        return cls(
            slug=slug,
            person=person,
            normalized_alarms=normalized_alarms,
            parse_errors=_restore_list(
                person,
                slug,
                "parse_errors",
                data.get("parse_errors"),
                [],
            ),
            map_errors=_restore_list(
                person,
                slug,
                "map_errors",
                data.get("map_errors"),
                [],
            ),
            map_locale=_restore_str(
                person,
                slug,
                "map_locale",
                data.get("map_locale"),
                None,
            ),
            last_event_time=last_event_time,
            raw_event=raw_event_value,
            next_alarm_key=_restore_str(
                person,
                slug,
                "next_alarm_key",
                data.get("next_alarm_key"),
                None,
            ),
            next_alarm_time=next_alarm_time,
            previous_alarm_key=_restore_str(
                person,
                slug,
                "previous_alarm_key",
                data.get("previous_alarm_key"),
                None,
            ),
            previous_alarm_time=previous_alarm_time,
            note=_restore_str(person, slug, "note", data.get("note"), None),
            schedule=schedule,
            map_version=_restore_int(
                person,
                slug,
                "map_version",
                data.get("map_version"),
                MAP_VERSION,
            ),
            last_refresh_start=last_refresh_start,
            last_refresh_end=last_refresh_end,
            refresh_problem=False,
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
        self._remove_refresh_listener: CALLBACK_TYPE | None = None
        self._lock = asyncio.Lock()

    @property
    def persons(self) -> list[str]:
        """Return the known person identifiers."""

        return list(self._person_states)

    @property
    def person_states(self) -> dict[str, PersonState]:
        """Expose the current person states."""

        return self._person_states

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
        self._remove_refresh_listener = self.hass.bus.async_listen(
            EVENT_REFRESH_START, self._async_handle_refresh_start
        )
        _LOGGER.debug("Listening for %s events", EVENT_NEXT_ALARM)
        _LOGGER.debug("Listening for %s events", EVENT_REFRESH_START)

    async def async_unload(self) -> None:
        """Tear down the coordinator."""

        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        if self._remove_refresh_listener:
            self._remove_refresh_listener()
            self._remove_refresh_listener = None
        for state in self._person_states.values():
            if state.timer_cancel:
                state.timer_cancel()
                state.timer_cancel = None
            if state.refresh_timer_cancel:
                state.refresh_timer_cancel()
                state.refresh_timer_cancel = None
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
        if not isinstance(data, dict):
            _LOGGER.warning("Stored NextAlarm data is not a dictionary; skipping restore")
            return
        persons = data.get("persons", {})
        if not isinstance(persons, dict):
            _LOGGER.warning("Stored NextAlarm persons data is not a dictionary; skipping restore")
            return
        for stored_slug, stored in persons.items():
            slug = stored_slug
            _LOGGER.debug(
                "Restoring person from storage: stored_slug=%s, stored_person=%s",
                stored_slug,
                stored.get("person") if isinstance(stored, dict) else None,
            )
            if not isinstance(stored, dict):
                _LOGGER.warning(
                    "Skipping restore for %s because stored entry is not a dictionary",
                    stored_slug,
                )
                continue
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
            _LOGGER.debug(
                "Restored state: slug=%s, person=%s, next_alarm_time=%s",
                slug,
                state.person,
                state.next_alarm_time,
            )

    @property
    def _timezone(self) -> tzinfo:
        """Return the active timezone, falling back to UTC when unset."""

        tz_name = self.hass.config.time_zone
        timezone = dt_util.get_time_zone(tz_name) if tz_name else None
        return timezone or dt_util.UTC

    def _current_options(self) -> dict[str, Any]:
        options = dict(DEFAULT_OPTIONS)
        entry_options = self.entry.options
        if isinstance(entry_options, dict):
            options.update(entry_options)
        return options

    def _refresh_timeout_seconds(self) -> int:
        options = self._current_options()
        raw_timeout = options.get(CONF_REFRESH_TIMEOUT, DEFAULT_OPTIONS[CONF_REFRESH_TIMEOUT])
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            timeout = DEFAULT_OPTIONS[CONF_REFRESH_TIMEOUT]
        else:
            timeout = timeout if timeout >= 1 else DEFAULT_OPTIONS[CONF_REFRESH_TIMEOUT]
        _LOGGER.debug(
            "Resolved refresh timeout option: raw=%s, effective=%ss",
            raw_timeout,
            timeout,
        )
        return timeout

    async def _async_handle_event(self, event: Event) -> None:
        """Handle an incoming NextAlarm event."""

        async with self._lock:
            await self._async_process_event(event)

    async def _async_handle_refresh_start(self, event: Event) -> None:
        """Handle an incoming refresh start event."""

        async with self._lock:
            await self._async_process_refresh_start(event)

    async def _async_process_event(self, event: Event) -> None:
        person_raw = event.data.get("person")
        if not person_raw:
            _LOGGER.warning("Received %s event without person", EVENT_NEXT_ALARM)
            return
        _LOGGER.debug("Incoming EVENT_NEXT_ALARM for person_raw=%s", person_raw)
        person = str(person_raw)
        alarms = event.data.get("alarms")
        if not isinstance(alarms, dict):
            _LOGGER.warning("Event for %s does not contain alarm dictionary", person_raw)
            return

        slug = _person_slug(person)
        _LOGGER.debug("Derived slug=%s for person=%s", slug, person)
        if slug not in self._person_states:
            for existing in self._person_states.values():
                if existing.person == person:
                    _LOGGER.debug(
                        "Remapped incoming person %s to existing slug=%s",
                        person,
                        existing.slug,
                    )
                    slug = existing.slug
                    break
        if slug not in self._person_states:
            _LOGGER.debug("Creating new PersonState: slug=%s, person=%s", slug, person)
            self._person_states[slug] = PersonState(slug=slug, person=person)
            self._notify_new_person(slug)
        state = self._person_states[slug]
        state.person = person

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

        reference_now = event.time_fired or dt_util.utcnow()
        # Use the event time as reference to keep schedule calculations deterministic.
        computation = helpers.compute_next_alarm(
            normalized.alarms, reference_now, self._timezone
        )

        state.normalized_alarms = normalized.alarms
        state.parse_errors = normalized.parse_errors
        state.map_errors = list(normalized.map_errors)
        state.map_locale = normalized.map_locale

        state.last_event_time = reference_now  # Store when the payload was received for diagnostics.
        state.last_refresh_end = reference_now
        state.refresh_problem = False
        state.refresh_timeout_token = None
        self._cancel_refresh_timer(state)

        state.next_alarm_key = computation.alarm.key if computation.alarm else None
        state.next_alarm_time = computation.next_time
        state.note = computation.note
        state.schedule = computation.schedule
        state.map_version = MAP_VERSION
        state.raw_event = {
            "event_type": event.event_type,
            "origin": event.origin,
            "context": helpers.ensure_serializable(event.context.as_dict()),
            "data": helpers.ensure_serializable(event.data),
            "time_fired": reference_now.isoformat(),  # Persist the firing time for traceability.
        }
        _LOGGER.debug(
            "Updated state for %s: next_alarm_time=%s, map_version=%s",
            state.person,
            state.next_alarm_time,
            state.map_version,
        )

        self._schedule_rollover(state)
        await self._store.async_save(self._storage_payload())
        _LOGGER.debug(
            "Processed NextAlarm event for %s; next alarm %s",
            state.person,
            state.next_alarm_time,
        )
        self._notify_person_update(slug)

    async def _async_process_refresh_start(self, event: Event) -> None:
        person_raw = event.data.get("person")
        if not person_raw:
            _LOGGER.warning("Received %s event without person", EVENT_REFRESH_START)
            return

        _LOGGER.debug("EVENT_REFRESH_START received for person_raw=%s", person_raw)
        person = str(person_raw)
        slug = _person_slug(person)
        _LOGGER.debug("Refresh start mapped to slug=%s for person=%s", slug, person)
        if slug not in self._person_states:
            for existing in self._person_states.values():
                if existing.person == person:
                    _LOGGER.debug(
                        "Remapped incoming person %s to existing slug=%s",
                        person,
                        existing.slug,
                    )
                    slug = existing.slug
                    break
        if slug not in self._person_states:
            _LOGGER.debug("Creating new PersonState: slug=%s, person=%s", slug, person)
            self._person_states[slug] = PersonState(slug=slug, person=person)
            self._notify_new_person(slug)
        state = self._person_states[slug]
        state.person = person

        reference_now = event.time_fired or dt_util.utcnow()
        state.last_refresh_start = reference_now
        self._cancel_refresh_timer(state)
        state.refresh_timeout_token = None
        state.refresh_problem = False
        token = uuid.uuid4().hex
        state.refresh_timeout_token = token
        _LOGGER.debug(
            "Starting refresh: person=%s, token=%s, timeout=%ss",
            state.person,
            token,
            self._refresh_timeout_seconds(),
        )
        self._schedule_refresh_timeout(state, token)

        await self._store.async_save(self._storage_payload())
        _LOGGER.debug("Processed refresh start event for %s", state.person)
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
        if state.next_alarm_time or trigger_time:
            state.previous_alarm_time = trigger_time or state.next_alarm_time
            state.previous_alarm_key = state.next_alarm_key
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

    def _schedule_refresh_timeout(self, state: PersonState, token: str) -> None:
        timeout = self._refresh_timeout_seconds()
        _LOGGER.debug(
            "Scheduling refresh timeout: person=%s, slug=%s, timeout=%ss, token=%s",
            state.person,
            state.slug,
            timeout,
            token,
        )

        @callback
        def _fire(*_args) -> None:
            self.hass.async_create_task(
                self._async_mark_refresh_timeout(
                    state.slug, dt_util.utcnow(), token
                )
            )

        state.refresh_timer_cancel = async_call_later(self.hass, timeout, _fire)

    def _cancel_refresh_timer(self, state: PersonState) -> None:
        if state.refresh_timer_cancel:
            state.refresh_timer_cancel()
            state.refresh_timer_cancel = None

    async def _async_mark_refresh_timeout(
        self, slug: str, trigger_time: datetime, token: str
    ) -> None:
        state = self._person_states.get(slug)
        if not state:
            return

        _LOGGER.debug(
            "Refresh timeout fired: slug=%s, trigger_time=%s, token=%s, current_token=%s",
            slug,
            trigger_time,
            token,
            state.refresh_timeout_token,
        )

        if state.refresh_timeout_token != token:
            _LOGGER.debug(
                "Refresh timeout ignored due to token mismatch: expected=%s, current=%s",
                token,
                state.refresh_timeout_token,
            )
            return

        state.refresh_timer_cancel = None
        state.refresh_problem = True
        state.refresh_timeout_token = None
        await self._store.async_save(self._storage_payload())

        _LOGGER.debug(
            "Refresh problem set: person=%s, slug=%s",
            state.person,
            slug,
        )
        self._notify_person_update(slug)
