"""Config flow for Sensors to Weather."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.selector as selector

from .const import DOMAIN


class SensorsToWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Single step: name + sensor selection."""
        errors = {}

        if user_input is not None:
            if not user_input.get("sensors"):
                errors["sensors"] = "no_sensors"
            else:
                return self.async_create_entry(
                    title=user_input.get("name", "Station météo"),
                    data={
                        "name": user_input["name"],
                        "sensors": user_input["sensors"],
                    },
                )

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="Station météo"): str,
                    vol.Required("sensors"): selector.selector(
                        {
                            "entity": {
                                "domain": "sensor",
                                "multiple": True,
                            }
                        }
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return SensorsToWeatherOptionsFlow(entry)


class SensorsToWeatherOptionsFlow(config_entries.OptionsFlow):
    """Allow updating the sensor list."""

    def __init__(self, entry):
        self._entry = entry

    async def async_step_init(self, user_input=None):
        current = self._entry.options.get(
            "sensors", self._entry.data.get("sensors", [])
        )
        errors = {}

        if user_input is not None:
            if not user_input.get("sensors"):
                errors["sensors"] = "no_sensors"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("sensors", default=current): selector.selector(
                        {
                            "entity": {
                                "domain": "sensor",
                                "multiple": True,
                            }
                        }
                    ),
                }
            ),
        )
