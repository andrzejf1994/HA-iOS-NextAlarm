"""Tests for the NextAlarm coordinator."""

from __future__ import annotations

from copy import deepcopy
import asyncio

from homeassistant.const import EVENT_TIME_CHANGED
from homeassistant.core import Context, Event, EventOrigin, HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.ha_ios_nextalarm.const import (
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_NEXT_ALARM,
)
from custom_components.ha_ios_nextalarm.coordinator import NextAlarmCoordinator


class MockConfigEntry:
    """Simplified stand-in for Home Assistant's ConfigEntry."""

    def __init__(self, *, domain: str, data: dict | None = None, options: dict | None = None) -> None:
        self.domain = domain
        self.data = data or {}
        self.options = options or {}
        self.entry_id = "test-entry"

    def add_to_hass(self, hass) -> None:
        hass.data.setdefault(self.domain, {})


async def async_fire_time_changed(hass, when) -> None:
    """Fire a time changed event for the provided timestamp."""

    hass.bus.async_fire(EVENT_TIME_CHANGED, {"now": when})
    await hass.async_block_till_done()

EVENT_DATA = {
    "alarms": {
        "1": {
            "Date": "18.09.2025 05:15",
            "Label": "Alarm",
            "Repeat": "on",
            "Repeat Days": "Wtorek\nPoniedziałek\nŚroda\nCzwartek\nPiątek",
            "Snooze": "on",
            "State": "on",
        },
        "2": {
            "Date": "18.09.2025 05:25",
            "Label": "Alarm",
            "Repeat": "on",
            "Repeat Days": "Środa\nWtorek\nPoniedziałek\nCzwartek\nPiątek",
            "Snooze": "on",
            "State": "off",
        },
        "3": {
            "Date": "18.09.2025 06:40",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
        "4": {
            "Date": "18.09.2025 08:30",
            "Label": "Alarm",
            "Repeat": "on",
            "Repeat Days": "Sobota\nNiedziela",
            "Snooze": "on",
            "State": "off",
        },
        "5": {
            "Date": "18.09.2025 09:30",
            "Label": "Alarm",
            "Repeat": "on",
            "Repeat Days": "Niedziela\nPoniedziałek\nWtorek\nŚroda\nCzwartek\nPiątek\nSobota",
            "Snooze": "on",
            "State": "off",
        },
        "6": {
            "Date": "18.09.2025 12:00",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
        "7": {
            "Date": "18.09.2025 20:05",
            "Label": "Pizza",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
        "8": {
            "Date": "17.09.2025 20:30",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "off",
            "State": "on",
        },
        "9": {
            "Date": "17.09.2025 21:00",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
        "10": {
            "Date": "17.09.2025 21:30",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
        "11": {
            "Date": "17.09.2025 21:45",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
        "12": {
            "Date": "17.09.2025 21:50",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
        "13": {
            "Date": "17.09.2025 22:10",
            "Label": "Alarm",
            "Repeat": "off",
            "Repeat Days": "",
            "Snooze": "on",
            "State": "off",
        },
    },
    "person": "andrzej",
}

EVENT_TIME = "2025-09-17T18:16:18.576523+00:00"


def test_rollover_and_restore() -> None:
    """Ensure rollover planning persists across restarts."""

    async def _run() -> None:
        hass = HomeAssistant()
        hass.config.time_zone = "Europe/Warsaw"
        entry = MockConfigEntry(domain=DOMAIN, data={}, options=dict(DEFAULT_OPTIONS))
        entry.add_to_hass(hass)

        coordinator = NextAlarmCoordinator(hass, entry)
        await coordinator.async_setup()

        event_payload = deepcopy(EVENT_DATA)
        event = Event(
            EVENT_NEXT_ALARM,
            data=event_payload,
            origin=EventOrigin.remote,
            time_fired=dt_util.parse_datetime(EVENT_TIME),
            context=Context(id="ctx", user_id="user"),
        )
        await coordinator._async_process_event(event)
        await hass.async_block_till_done()

        state = coordinator.get_person_state("andrzej")
        assert state is not None
        assert state.next_alarm_time is not None
        first_next = state.next_alarm_time
        assert first_next.isoformat().startswith("2025-09-17T20:30")

        original_utcnow = dt_util.utcnow
        try:
            dt_util.utcnow = lambda: first_next

            await async_fire_time_changed(hass, first_next)
            await hass.async_block_till_done()

            state = coordinator.get_person_state("andrzej")
            assert state is not None
            assert state.next_alarm_time is not None
            second_next = state.next_alarm_time
            assert second_next > first_next
            assert second_next.isoformat().startswith("2025-09-18T05:15")

            dt_util.utcnow = lambda: second_next
            await coordinator.async_unload()

            new_coordinator = NextAlarmCoordinator(hass, entry)
            await new_coordinator.async_setup()
            await hass.async_block_till_done()
            new_state = new_coordinator.get_person_state("andrzej")
            assert new_state is not None
            assert new_state.next_alarm_time == second_next

            await new_coordinator.async_unload()
        finally:
            dt_util.utcnow = original_utcnow

    asyncio.run(_run())
