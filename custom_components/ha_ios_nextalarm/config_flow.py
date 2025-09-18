"""Config flow for the HA iOS NextAlarm integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_WEEKDAY_CUSTOM_MAP,
    CONF_WEEKDAY_LOCALE,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPTION_WEEKDAY_LOCALES,
)
from . import helpers


class NextAlarmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="HA iOS NextAlarm",
                data={},
                options=dict(DEFAULT_OPTIONS),
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return NextAlarmOptionsFlow(config_entry)


class NextAlarmOptionsFlow(config_entries.OptionsFlow):
    """Options flow for NextAlarm."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""

        errors: dict[str, str] = {}
        current = dict(DEFAULT_OPTIONS)
        current.update(self.config_entry.options)

        if user_input is not None:
            locale = user_input[CONF_WEEKDAY_LOCALE]
            custom_map = user_input.get(
                CONF_WEEKDAY_CUSTOM_MAP, DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP]
            )
            _, map_errors = helpers.build_weekday_maps(custom_map)
            if map_errors:
                errors["base"] = "invalid_custom_map"
            else:
                return self.async_create_entry(
                    data={
                        CONF_WEEKDAY_LOCALE: locale,
                        CONF_WEEKDAY_CUSTOM_MAP: custom_map,
                    }
                )

        locales = list(OPTION_WEEKDAY_LOCALES)
        if current[CONF_WEEKDAY_LOCALE] not in locales:
            locales.append(current[CONF_WEEKDAY_LOCALE])

        schema = vol.Schema(
            {
                vol.Required(CONF_WEEKDAY_LOCALE, default=current[CONF_WEEKDAY_LOCALE]): vol.In(
                    locales
                ),
                vol.Optional(
                    CONF_WEEKDAY_CUSTOM_MAP,
                    default=current[CONF_WEEKDAY_CUSTOM_MAP],
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
