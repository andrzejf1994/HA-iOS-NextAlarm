"""Tests for helper utilities."""

from __future__ import annotations

from datetime import datetime

from homeassistant.util import dt as dt_util

from custom_components.ha_ios_nextalarm import helpers


def test_parse_alarm_datetime_24h() -> None:
    tz = dt_util.get_time_zone("Europe/Warsaw")
    result = helpers.parse_alarm_datetime("18.09.2025 05:15", tz)
    assert result.tzinfo == tz
    assert result.hour == 5
    assert result.minute == 15
    assert result.isoformat().endswith("+02:00")


def test_parse_on_off_conversion() -> None:
    errors: list[str] = []
    assert helpers.parse_on_off("on", field="State", alarm_key="1", errors=errors) is True
    assert helpers.parse_on_off("off", field="State", alarm_key="1", errors=errors) is False
    assert helpers.parse_on_off("ON", field="State", alarm_key="1", errors=errors) is True
    assert helpers.parse_on_off("unexpected", field="State", alarm_key="2", errors=errors) is None
    assert errors[-1].startswith("Alarm 2")


def test_normalize_repeat_days_polish() -> None:
    maps, map_errors = helpers.build_weekday_maps("")
    assert not map_errors
    parse_errors: list[str] = []
    localized, normalized, locale = helpers.normalize_repeat_days(
        "Wtorek\nPoniedziałek\nŚroda\nCzwartek\nPiątek",
        alarm_key="1",
        locale_option="auto",
        maps=maps,
        errors=parse_errors,
    )
    assert locale == "pl"
    assert normalized == [1, 0, 2, 3, 4]
    assert localized == [
        "Wtorek",
        "Poniedziałek",
        "Środa",
        "Czwartek",
        "Piątek",
    ]
    assert not parse_errors


def test_normalize_repeat_days_english() -> None:
    maps, map_errors = helpers.build_weekday_maps("")
    assert not map_errors
    parse_errors: list[str] = []
    localized, normalized, locale = helpers.normalize_repeat_days(
        "Monday\nSunday",
        alarm_key="1",
        locale_option="auto",
        maps=maps,
        errors=parse_errors,
    )
    assert locale == "en"
    assert normalized == [0, 6]
    assert localized == ["Monday", "Sunday"]
    assert not parse_errors


def _alarm(
    *,
    key: str,
    enabled: bool,
    repeat: bool,
    base_time: datetime,
    repeat_days: list[int] | None = None,
) -> helpers.NormalizedAlarm:
    return helpers.NormalizedAlarm(
        key=key,
        label=f"Alarm {key}",
        enabled=enabled,
        repeat=repeat,
        snooze=False,
        base_time=base_time,
        repeat_days_localized=["test"] if repeat and repeat_days else [],
        repeat_days_normalized=repeat_days or [],
    )


def test_compute_next_alarm_tie_prefers_lower_key() -> None:
    tz = dt_util.get_time_zone("Europe/Warsaw")
    base = helpers.parse_alarm_datetime("18.09.2025 05:15", tz)
    alarms = {
        "2": _alarm(key="2", enabled=True, repeat=False, base_time=base),
        "1": _alarm(key="1", enabled=True, repeat=False, base_time=base),
    }
    now = helpers.parse_alarm_datetime("17.09.2025 20:00", tz)
    result = helpers.compute_next_alarm(alarms, now, tz)
    assert result.alarm is not None
    assert result.alarm.key == "1"
    assert result.next_time == base


def test_compute_next_alarm_no_future() -> None:
    tz = dt_util.get_time_zone("Europe/Warsaw")
    past = helpers.parse_alarm_datetime("17.09.2025 05:15", tz)
    alarms = {"1": _alarm(key="1", enabled=True, repeat=False, base_time=past)}
    now = helpers.parse_alarm_datetime("18.09.2025 05:15", tz)
    result = helpers.compute_next_alarm(alarms, now, tz)
    assert result.next_time is None
    assert result.note == "no_future"


def test_repeating_alarm_schedule() -> None:
    tz = dt_util.get_time_zone("Europe/Warsaw")
    base = helpers.parse_alarm_datetime("18.09.2025 05:15", tz)
    alarms = {
        "1": _alarm(
            key="1",
            enabled=True,
            repeat=True,
            base_time=base,
            repeat_days=[0, 1, 2, 3, 4],
        )
    }
    now = helpers.parse_alarm_datetime("17.09.2025 18:00", tz)
    result = helpers.compute_next_alarm(alarms, now, tz)
    assert result.next_time is not None
    assert result.next_time.isoformat().startswith("2025-09-18T05:15")
