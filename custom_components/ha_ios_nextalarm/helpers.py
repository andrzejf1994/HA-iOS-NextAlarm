"""Helper utilities for the HA iOS NextAlarm integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
import json
import logging
import unicodedata
from typing import Any, Mapping, Sequence

from homeassistant.util import dt as dt_util

from .const import PREVIEW_LIMIT, STR_ONOFF, WEEKDAY_MAPS

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class NormalizedAlarm:
    """Representation of a normalized alarm received from an event."""

    key: str
    label: str
    enabled: bool
    repeat: bool
    snooze: bool
    base_time: datetime
    repeat_days_localized: list[str]
    repeat_days_normalized: list[int]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the alarm into a JSON-friendly dictionary."""

        return {
            "key": self.key,
            "label": self.label,
            "enabled": self.enabled,
            "repeat": self.repeat,
            "snooze": self.snooze,
            "base_time": self.base_time.isoformat(),
            "repeat_days_localized": list(self.repeat_days_localized),
            "repeat_days_normalized": list(self.repeat_days_normalized),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NormalizedAlarm":
        """Deserialize an alarm from storage."""

        base_time_str = data["base_time"]
        base_time = dt_util.parse_datetime(base_time_str)
        if base_time is None:
            raise ValueError(f"Invalid datetime stored: {base_time_str}")
        return cls(
            key=str(data["key"]),
            label=str(data.get("label", "")),
            enabled=bool(data.get("enabled", False)),
            repeat=bool(data.get("repeat", False)),
            snooze=bool(data.get("snooze", False)),
            base_time=base_time,
            repeat_days_localized=list(data.get("repeat_days_localized", [])),
            repeat_days_normalized=list(data.get("repeat_days_normalized", [])),
        )


@dataclass(slots=True)
class NormalizedEvent:
    """Container for normalized event data."""

    alarms: dict[str, NormalizedAlarm]
    map_locale: str
    parse_errors: list[str]
    map_errors: list[str]


@dataclass(slots=True)
class NextAlarmComputation:
    """Result of evaluating the next alarm for a person."""

    alarm: NormalizedAlarm | None
    next_time: datetime | None
    schedule: dict[str, datetime | None]
    note: str | None


def normalize_day_key(value: str) -> str:
    """Normalize weekday names for lookup."""

    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.replace(" ", "").replace("-", "").casefold().strip()


def _localize(naive: datetime, tzinfo) -> datetime:
    """Attach a timezone to a naive datetime."""

    if hasattr(tzinfo, "localize"):
        return tzinfo.localize(naive)
    return naive.replace(tzinfo=tzinfo)


def parse_alarm_datetime(value: str, tzinfo) -> datetime:
    """Parse the alarm datetime string into an aware datetime."""

    text = (value or "").strip()
    if not text:
        raise ValueError("missing datetime value")

    parsed = dt_util.parse_datetime(text)
    if parsed is None:
        try:
            parsed = datetime.strptime(text, "%d.%m.%Y %H:%M")
        except ValueError:
            upper = text.upper()
            if "AM" in upper or "PM" in upper:
                try:
                    parsed = datetime.strptime(text, "%m/%d/%Y %I:%M %p")
                except ValueError as exc:
                    raise ValueError(f"unsupported datetime format: {text}") from exc
            else:
                raise ValueError(f"unsupported datetime format: {text}")

    if parsed.tzinfo is None:
        parsed = _localize(parsed, tzinfo)
    return parsed.astimezone(tzinfo)


def parse_on_off(value: Any, *, field: str, alarm_key: str, errors: list[str]) -> bool | None:
    """Parse an on/off value."""

    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in STR_ONOFF:
            return STR_ONOFF[normalized]
    elif isinstance(value, bool):
        return value
    errors.append(f"Alarm {alarm_key}: invalid value '{value}' for field '{field}'")
    return None


def build_weekday_maps(custom_map_json: str) -> tuple[dict[str, dict[str, int]], list[str]]:
    """Build locale weekday maps from defaults and an optional JSON override."""

    base: dict[str, dict[str, int]] = {
        locale: {normalize_day_key(key): value for key, value in mapping.items()}
        for locale, mapping in WEEKDAY_MAPS.items()
    }
    if not custom_map_json or not custom_map_json.strip():
        return base, []

    errors: list[str] = []
    try:
        parsed = json.loads(custom_map_json)
    except json.JSONDecodeError as err:
        errors.append(f"Invalid custom map JSON: {err}")
        return base, errors
    if not isinstance(parsed, Mapping):
        errors.append("Custom map must be a JSON object")
        return base, errors

    for locale, mapping in parsed.items():
        if not isinstance(locale, str):
            errors.append("Custom map locale keys must be strings")
            continue
        if not isinstance(mapping, Mapping):
            errors.append(f"Custom map for locale '{locale}' must be an object")
            continue
        normalized_mapping: dict[str, int] = base.get(locale, {}).copy()
        for day_name, index in mapping.items():
            if not isinstance(day_name, str):
                errors.append(
                    f"Custom map for locale '{locale}' has non-string key '{day_name}'"
                )
                continue
            try:
                weekday_index = int(index)
            except (TypeError, ValueError) as err:
                errors.append(
                    f"Custom map value for '{day_name}' in locale '{locale}' is not an integer: {index}"
                )
                continue
            if weekday_index < 0 or weekday_index > 6:
                errors.append(
                    f"Custom map value for '{day_name}' in locale '{locale}' must be between 0 and 6"
                )
                continue
            normalized_mapping[normalize_day_key(day_name)] = weekday_index
        base[locale] = normalized_mapping
    return base, errors


def detect_weekday_locale(
    weekday_lines: Sequence[str],
    locale_option: str,
    maps: Mapping[str, Mapping[str, int]],
) -> str:
    """Detect the best matching weekday locale."""

    default_locale = next(iter(maps))
    if locale_option != "auto":
        return locale_option if locale_option in maps else default_locale
    if not weekday_lines:
        return default_locale

    best_locale = None
    best_score = -1
    normalized_lines = [normalize_day_key(item) for item in weekday_lines]
    for locale, mapping in maps.items():
        score = sum(1 for item in normalized_lines if item in mapping)
        if score > best_score:
            best_locale = locale
            best_score = score
    if best_locale is None:
        return default_locale
    return best_locale


def normalize_repeat_days(
    raw: Any,
    *,
    alarm_key: str,
    locale_option: str,
    maps: Mapping[str, Mapping[str, int]],
    errors: list[str],
) -> tuple[list[str], list[int], str]:
    """Normalize repeat day values."""

    text = str(raw or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    locale = detect_weekday_locale(lines, locale_option, maps)
    normalized_days: list[int] = []
    localized_days: list[str] = []
    seen: set[int] = set()

    if not lines:
        return localized_days, normalized_days, locale

    mapping = maps.get(locale, {})
    fallback_maps = [mapping] + [maps[name] for name in maps if name != locale]

    for line in lines:
        normalized_line = normalize_day_key(line)
        matched = False
        for candidate_map in fallback_maps:
            if normalized_line in candidate_map:
                weekday_index = candidate_map[normalized_line]
                if weekday_index not in seen:
                    seen.add(weekday_index)
                    normalized_days.append(weekday_index)
                    localized_days.append(line)
                matched = True
                break
        if not matched:
            errors.append(
                f"Alarm {alarm_key}: could not map repeat day '{line}' with locale '{locale}'"
            )
    return localized_days, normalized_days, locale


def normalize_event(
    *,
    alarms: Mapping[str, Mapping[str, Any]],
    tzinfo,
    locale_option: str,
    maps: Mapping[str, Mapping[str, int]],
    map_errors: Sequence[str] | None = None,
) -> NormalizedEvent:
    """Normalize the alarm payload of an event."""

    parse_errors: list[str] = []
    normalized_alarms: dict[str, NormalizedAlarm] = {}
    all_repeat_lines: list[str] = []

    valid_alarms: dict[str, Mapping[str, Any]] = {}
    for key, raw_alarm in alarms.items():
        str_key = str(key)
        if not isinstance(raw_alarm, Mapping):
            parse_errors.append(
                f"Alarm {str_key}: payload must be an object with alarm fields"
            )
            continue
        valid_alarms[str_key] = raw_alarm
        raw_days = raw_alarm.get("Repeat Days")
        if isinstance(raw_days, str):
            all_repeat_lines.extend(
                [line.strip() for line in raw_days.splitlines() if line.strip()]
            )

    map_locale = detect_weekday_locale(all_repeat_lines, locale_option, maps)

    for key, raw_alarm in valid_alarms.items():
        label = str(raw_alarm.get("Label", "")).strip() or key
        raw_date = raw_alarm.get("Date")
        if raw_date is None:
            parse_errors.append(f"Alarm {key}: missing Date")
            continue
        try:
            base_time = parse_alarm_datetime(str(raw_date), tzinfo)
        except ValueError as err:
            parse_errors.append(f"Alarm {key}: {err}")
            continue

        state = parse_on_off(
            raw_alarm.get("State"), field="State", alarm_key=key, errors=parse_errors
        )
        if state is None:
            continue
        repeat = parse_on_off(
            raw_alarm.get("Repeat"), field="Repeat", alarm_key=key, errors=parse_errors
        )
        if repeat is None:
            continue
        snooze = parse_on_off(
            raw_alarm.get("Snooze"), field="Snooze", alarm_key=key, errors=parse_errors
        )
        if snooze is None:
            continue

        repeat_days_localized: list[str] = []
        repeat_days_normalized: list[int] = []
        if repeat:
            (
                repeat_days_localized,
                repeat_days_normalized,
                _,
            ) = normalize_repeat_days(
                raw_alarm.get("Repeat Days", ""),
                alarm_key=key,
                locale_option=map_locale,
                maps=maps,
                errors=parse_errors,
            )
            if not repeat_days_normalized:
                parse_errors.append(
                    f"Alarm {key}: repeat is enabled but no valid repeat days were provided"
                )
                continue

        normalized_alarms[key] = NormalizedAlarm(
            key=key,
            label=label,
            enabled=state,
            repeat=repeat,
            snooze=snooze,
            base_time=base_time,
            repeat_days_localized=repeat_days_localized,
            repeat_days_normalized=repeat_days_normalized,
        )

    return NormalizedEvent(
        alarms=normalized_alarms,
        map_locale=map_locale,
        parse_errors=parse_errors,
        map_errors=list(map_errors or []),
    )


def compute_alarm_schedule(
    alarms: Mapping[str, NormalizedAlarm], now: datetime, tzinfo
) -> dict[str, datetime | None]:
    """Compute the next trigger per alarm."""

    schedule: dict[str, datetime | None] = {}
    for key, alarm in alarms.items():
        schedule[key] = compute_single_alarm_next(alarm, now, tzinfo)
    return schedule


def compute_single_alarm_next(
    alarm: NormalizedAlarm, now: datetime, tzinfo
) -> datetime | None:
    """Compute the next occurrence for a single alarm."""

    if not alarm.enabled:
        return None

    if not alarm.repeat:
        return alarm.base_time if alarm.base_time > now else None

    if not alarm.repeat_days_normalized:
        return None

    local_now = now.astimezone(tzinfo)
    local_today = local_now.date()
    base_local = alarm.base_time.astimezone(tzinfo)
    base_time_components = time(
        hour=base_local.hour,
        minute=base_local.minute,
        second=base_local.second,
        microsecond=base_local.microsecond,
    )

    for offset in range(0, 8):
        candidate_date = local_today + timedelta(days=offset)
        weekday = candidate_date.weekday()
        if weekday not in alarm.repeat_days_normalized:
            continue
        candidate_naive = datetime.combine(candidate_date, base_time_components)
        candidate = _localize(candidate_naive, tzinfo)
        if candidate > now:
            return candidate
    return None


def compute_next_alarm(
    alarms: Mapping[str, NormalizedAlarm], now: datetime, tzinfo
) -> NextAlarmComputation:
    """Compute the next alarm selection."""

    schedule = compute_alarm_schedule(alarms, now, tzinfo)
    next_alarm: NormalizedAlarm | None = None
    next_time: datetime | None = None

    for key in sorted(alarms):
        candidate_time = schedule.get(key)
        if candidate_time is None:
            continue
        if next_time is None or candidate_time < next_time:
            next_time = candidate_time
            next_alarm = alarms[key]

    note: str | None = None
    if not alarms:
        note = "no_alarms"
    elif all(not alarm.enabled for alarm in alarms.values()):
        note = "no_enabled"
    elif next_time is None:
        note = "no_future"

    return NextAlarmComputation(
        alarm=next_alarm,
        next_time=next_time,
        schedule=schedule,
        note=note,
    )


def build_normalized_preview(
    alarms: Mapping[str, NormalizedAlarm],
    schedule: Mapping[str, datetime | None],
) -> list[dict[str, Any]]:
    """Build a truncated preview for diagnostics."""

    preview: list[dict[str, Any]] = []
    for key in sorted(alarms):
        alarm = alarms[key]
        next_time = schedule.get(key)
        preview.append(
            {
                "key": alarm.key,
                "label": alarm.label,
                "enabled": alarm.enabled,
                "repeat": alarm.repeat,
                "repeat_days": list(alarm.repeat_days_normalized),
                "next": next_time.isoformat() if next_time else None,
            }
        )
        if len(preview) >= PREVIEW_LIMIT:
            break
    return preview


def describe_time_until(target: datetime | None, now: datetime | None = None) -> str | None:
    """Return a human-friendly description of the time until target."""

    if target is None:
        return None
    reference = now or dt_util.utcnow()
    delta = target - reference
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "due"
    parts: list[str] = []
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return f"in {' '.join(parts)}"


def ensure_serializable(value: Any) -> Any:
    """Convert arbitrary event data into JSON-serialisable objects."""

    if isinstance(value, dict):
        return {str(key): ensure_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [ensure_serializable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
