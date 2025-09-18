from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ha_ios_nextalarm.config_flow import (
    NextAlarmConfigFlow,
    NextAlarmOptionsFlow,
)
from custom_components.ha_ios_nextalarm.const import (
    CONF_WEEKDAY_CUSTOM_MAP,
    CONF_WEEKDAY_LOCALE,
    DEFAULT_OPTIONS,
    DOMAIN,
)


def test_user_flow_creates_entry() -> None:
    """Ensure the user step renders cleanly and creates the entry without UI errors."""

    async def _run() -> None:
        hass = HomeAssistant()
        flow = NextAlarmConfigFlow()
        flow.hass = hass

        form = await flow.async_step_user()
        assert form["type"] == FlowResultType.FORM
        assert form["errors"] == {}
        assert form["data_schema"] is not None

        created = await flow.async_step_user({})
        assert created["type"] == FlowResultType.CREATE_ENTRY
        assert created["title"] == "HA iOS NextAlarm"
        assert created["data"] == {}
        assert created["options"] == DEFAULT_OPTIONS
        assert hass.config_entries._entries  # type: ignore[attr-defined]

        duplicate_flow = NextAlarmConfigFlow()
        duplicate_flow.hass = hass
        abort = await duplicate_flow.async_step_user()
        assert abort["type"] == FlowResultType.ABORT
        assert abort["reason"] in {"single_instance_allowed", "already_configured"}

    asyncio.run(_run())


def test_options_flow_validates_custom_map() -> None:
    """Validate that options flow surfaces JSON issues and stores confirmed values."""

    async def _run() -> None:
        entry = ConfigEntry(domain=DOMAIN, data={}, options=dict(DEFAULT_OPTIONS))
        flow = NextAlarmOptionsFlow(entry)
        hass = HomeAssistant()
        flow.hass = hass

        invalid = await flow.async_step_init(
            {
                CONF_WEEKDAY_LOCALE: "en",
                CONF_WEEKDAY_CUSTOM_MAP: "not json",
            }
        )
        assert invalid["type"] == FlowResultType.FORM
        assert invalid["errors"] == {"base": "invalid_custom_map"}
        assert entry.options == DEFAULT_OPTIONS

        valid = await flow.async_step_init(
            {
                CONF_WEEKDAY_LOCALE: "pl",
                CONF_WEEKDAY_CUSTOM_MAP: DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP],
            }
        )
        assert valid["type"] == FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_WEEKDAY_LOCALE] == "pl"
        assert (
            entry.options[CONF_WEEKDAY_CUSTOM_MAP]
            == DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP]
        )

    asyncio.run(_run())
