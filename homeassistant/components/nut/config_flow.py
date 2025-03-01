"""Config flow for Network UPS Tools (NUT) integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.components import zeroconf
from homeassistant.const import (
    CONF_ALIAS,
    CONF_BASE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from . import PyNUTData
from .const import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _base_schema(discovery_info):
    """Generate base schema."""
    base_schema = {}
    if not discovery_info:
        base_schema.update(
            {
                vol.Optional(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
    base_schema.update(
        {vol.Optional(CONF_USERNAME): str, vol.Optional(CONF_PASSWORD): str}
    )

    return vol.Schema(base_schema)


def _ups_schema(ups_list):
    """UPS selection schema."""
    return vol.Schema({vol.Required(CONF_ALIAS): vol.In(ups_list)})


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.

    Data has the keys from _base_schema with values provided by the user.
    """

    host = data[CONF_HOST]
    port = data[CONF_PORT]
    alias = data.get(CONF_ALIAS)
    username = data.get(CONF_USERNAME)
    password = data.get(CONF_PASSWORD)

    data = PyNUTData(host, port, alias, username, password)
    await hass.async_add_executor_job(data.update)
    if not (status := data.status):
        raise CannotConnect

    return {"ups_list": data.ups_list, "available_resources": status}


def _format_host_port_alias(user_input):
    """Format a host, port, and alias so it can be used for comparison or display."""
    host = user_input[CONF_HOST]
    port = user_input[CONF_PORT]
    alias = user_input.get(CONF_ALIAS)
    if alias:
        return f"{alias}@{host}:{port}"
    return f"{host}:{port}"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Network UPS Tools (NUT)."""

    VERSION = 1

    def __init__(self):
        """Initialize the nut config flow."""
        self.nut_config = {}
        self.discovery_info = {}
        self.ups_list = None
        self.title = None

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Prepare configuration for a discovered nut device."""
        self.discovery_info = discovery_info
        await self._async_handle_discovery_without_unique_id()
        self.context["title_placeholders"] = {
            CONF_PORT: discovery_info[zeroconf.ATTR_PORT] or DEFAULT_PORT,
            CONF_HOST: discovery_info[zeroconf.ATTR_HOST],
        }
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle the user input."""
        errors = {}
        if user_input is not None:
            if self.discovery_info:
                user_input.update(
                    {
                        CONF_HOST: self.discovery_info[CONF_HOST],
                        CONF_PORT: self.discovery_info.get(CONF_PORT, DEFAULT_PORT),
                    }
                )
            info, errors = await self._async_validate_or_error(user_input)

            if not errors:
                self.nut_config.update(user_input)
                if len(info["ups_list"]) > 1:
                    self.ups_list = info["ups_list"]
                    return await self.async_step_ups()

                if self._host_port_alias_already_configured(self.nut_config):
                    return self.async_abort(reason="already_configured")
                title = _format_host_port_alias(self.nut_config)
                return self.async_create_entry(title=title, data=self.nut_config)

        return self.async_show_form(
            step_id="user", data_schema=_base_schema(self.discovery_info), errors=errors
        )

    async def async_step_ups(self, user_input=None):
        """Handle the picking the ups."""
        errors = {}

        if user_input is not None:
            self.nut_config.update(user_input)
            if self._host_port_alias_already_configured(self.nut_config):
                return self.async_abort(reason="already_configured")
            _, errors = await self._async_validate_or_error(self.nut_config)
            if not errors:
                title = _format_host_port_alias(self.nut_config)
                return self.async_create_entry(title=title, data=self.nut_config)

        return self.async_show_form(
            step_id="ups",
            data_schema=_ups_schema(self.ups_list),
            errors=errors,
        )

    def _host_port_alias_already_configured(self, user_input):
        """See if we already have a nut entry matching user input configured."""
        existing_host_port_aliases = {
            _format_host_port_alias(entry.data)
            for entry in self._async_current_entries()
            if CONF_HOST in entry.data
        }
        return _format_host_port_alias(user_input) in existing_host_port_aliases

    async def _async_validate_or_error(self, config):
        errors = {}
        info = {}
        try:
            info = await validate_input(self.hass, config)
        except CannotConnect:
            errors[CONF_BASE] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors[CONF_BASE] = "unknown"
        return info, errors

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for nut."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        base_schema = {
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int), vol.Clamp(min=10, max=300)
            )
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(base_schema))


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
