"""Config flow for the HA iOS NextAlarm integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult  # Import FlowResult for HA typing compliance.
from homeassistant.core import callback

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

        await self.async_set_unique_id(
            DOMAIN
        )  # Ensure Home Assistant tracks a single instance via unique ID.
        if self._async_current_entries():
            # Surface a translation-aligned abort when the integration already exists.
            return self.async_abort(reason="single_instance_allowed")
        if result := self._abort_if_unique_id_configured():
            # Defer to the core helper so duplicate flows triggered externally abort safely.
            return result

        if user_input is not None:
            return self.async_create_entry(
                title="HA iOS NextAlarm",
                data={},
                options=dict(DEFAULT_OPTIONS),
            )

        # Present an explicit empty schema so the UI renders a confirmation form without validation errors.
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )

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

        form_locale = current[CONF_WEEKDAY_LOCALE]
        form_map = current[CONF_WEEKDAY_CUSTOM_MAP]
        maps_preview, _ = helpers.build_weekday_maps(form_map)

        if user_input is not None:
            form_locale = user_input[CONF_WEEKDAY_LOCALE]
            form_map = user_input.get(
                CONF_WEEKDAY_CUSTOM_MAP, DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP]
            )
            maps_preview, map_errors = helpers.build_weekday_maps(form_map)
            if map_errors:
                errors["base"] = "invalid_custom_map"
            else:
                return self.async_create_entry(
                    data={
                        CONF_WEEKDAY_LOCALE: form_locale,
                        CONF_WEEKDAY_CUSTOM_MAP: form_map,
                    }
                )

        locales = sorted({*OPTION_WEEKDAY_LOCALES, *maps_preview.keys(), form_locale})

        schema = vol.Schema(
            {
                vol.Required(CONF_WEEKDAY_LOCALE, default=form_locale): vol.In(locales),
                vol.Optional(
                    CONF_WEEKDAY_CUSTOM_MAP,
                    default=form_map,
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
