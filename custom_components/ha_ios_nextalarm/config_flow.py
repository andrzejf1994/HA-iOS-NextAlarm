"""Config flow for the HA iOS NextAlarm integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult  # Import FlowResult for HA typing compliance.
from homeassistant.core import callback

from .const import (
    CONF_REFRESH_TIMEOUT,
    CONF_WEEKDAY_CUSTOM_MAP,
    CONF_WEEKDAY_LOCALE,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPTION_WEEKDAY_LOCALES,
)
from . import helpers

_LOGGER = logging.getLogger(__name__)


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
        _LOGGER.debug("Options flow init started with user_input=%s", user_input)
        try:
            return await self._async_step_init_internal(user_input)
        except Exception:
            _LOGGER.exception(
                "Options flow init failed with user_input=%s options=%s",
                user_input,
                dict(self.config_entry.options) if self.config_entry.options else {},
            )
            return self._async_show_fallback_form({"base": "unknown"})

    def _async_show_fallback_form(self, errors: dict[str, str]) -> FlowResult:
        """Show a safe fallback form when options flow fails unexpectedly."""
        form_locale = DEFAULT_OPTIONS[CONF_WEEKDAY_LOCALE]
        form_map = DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP]
        form_timeout = DEFAULT_OPTIONS[CONF_REFRESH_TIMEOUT]
        locales = list(OPTION_WEEKDAY_LOCALES)
        schema = vol.Schema(
            {
                vol.Required(CONF_WEEKDAY_LOCALE, default=form_locale): vol.In(locales),
                vol.Optional(CONF_WEEKDAY_CUSTOM_MAP, default=form_map): str,
                vol.Required(CONF_REFRESH_TIMEOUT, default=form_timeout): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def _async_step_init_internal(
        self, user_input: dict[str, Any] | None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        # Safely get current options
        current = dict(DEFAULT_OPTIONS)
        try:
            options = self.config_entry.options
            if isinstance(options, dict):
                current.update(options)
        except Exception as err:
            _LOGGER.warning("Failed to load current options, using defaults: %s", err)

        def _option_str(value: Any, default: str) -> str:
            return value if isinstance(value, str) else default

        def _option_int(value: Any, default: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return default
            return parsed if parsed >= 1 else default

        form_locale = _option_str(
            current.get(CONF_WEEKDAY_LOCALE),
            DEFAULT_OPTIONS[CONF_WEEKDAY_LOCALE],
        )
        form_map = _option_str(
            current.get(CONF_WEEKDAY_CUSTOM_MAP),
            DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP],
        )
        form_timeout = _option_int(
            current.get(CONF_REFRESH_TIMEOUT),
            DEFAULT_OPTIONS[CONF_REFRESH_TIMEOUT],
        )

        # Initialize with safe defaults to prevent AttributeError on maps_preview.keys()
        maps_preview: dict[str, dict[str, int]] = {}
        map_errors: list[str] = []

        try:
            maps_preview, map_errors = helpers.build_weekday_maps(form_map)
        except Exception as err:
            _LOGGER.error("Options map parsing failed: %s", err, exc_info=True)
            try:
                maps_preview, map_errors = helpers.build_weekday_maps(
                    DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP]
                )
            except Exception as fallback_err:
                _LOGGER.error(
                    "Failed to build default map: %s. Using empty fallback.",
                    fallback_err,
                    exc_info=True,
                )
                # Use base maps from const as last resort
                from .const import WEEKDAY_MAPS

                maps_preview = dict(WEEKDAY_MAPS)
                map_errors = ["Failed to parse custom map, using defaults"]

        if user_input is not None:
            form_locale = _option_str(
                user_input.get(CONF_WEEKDAY_LOCALE),
                DEFAULT_OPTIONS[CONF_WEEKDAY_LOCALE],
            )
            form_map = _option_str(
                user_input.get(CONF_WEEKDAY_CUSTOM_MAP),
                DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP],
            )

            try:
                maps_preview, map_errors = helpers.build_weekday_maps(form_map)
            except Exception as err:
                _LOGGER.error("Options map parsing failed: %s", err, exc_info=True)
                try:
                    maps_preview, map_errors = helpers.build_weekday_maps(
                        DEFAULT_OPTIONS[CONF_WEEKDAY_CUSTOM_MAP]
                    )
                except Exception:
                    from .const import WEEKDAY_MAPS

                    maps_preview = dict(WEEKDAY_MAPS)
                errors["base"] = "invalid_custom_map"

            if map_errors:
                errors["base"] = "invalid_custom_map"

            if not errors:
                return self.async_create_entry(
                    title="",  # Title is ignored for options flow
                    data={
                        CONF_WEEKDAY_LOCALE: form_locale,
                        CONF_WEEKDAY_CUSTOM_MAP: form_map,
                        CONF_REFRESH_TIMEOUT: user_input.get(
                            CONF_REFRESH_TIMEOUT, form_timeout
                        ),
                    },
                )

        # Build locale list safely to prevent crashes
        try:
            locales = sorted({*OPTION_WEEKDAY_LOCALES, *maps_preview.keys(), form_locale})
        except Exception as err:
            _LOGGER.error("Failed to build locales list: %s", err, exc_info=True)
            locales = list(OPTION_WEEKDAY_LOCALES)
            if form_locale not in locales:
                locales.append(form_locale)
            locales.sort()

        schema = vol.Schema(
            {
                vol.Required(CONF_WEEKDAY_LOCALE, default=form_locale): vol.In(locales),
                vol.Optional(
                    CONF_WEEKDAY_CUSTOM_MAP,
                    default=form_map,
                ): str,
                vol.Required(CONF_REFRESH_TIMEOUT, default=form_timeout): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
