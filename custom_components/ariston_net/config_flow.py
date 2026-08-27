"""Config flow per Ariston Net (solo UI, nessuna configurazione YAML)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from ariston import Ariston
from ariston.ariston_api import ConnectionException
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_ENABLED_GATEWAYS,
    CONF_ENERGY_SCAN_INTERVAL,
    CONF_IS_METRIC,
    CONF_LANGUAGE_TAG,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENERGY_SCAN_INTERVAL,
    DEFAULT_LANGUAGE_TAG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_ENERGY_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class AristonNetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gestisce il flusso di configurazione UI per Ariston Net."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_username: str | None = None

    async def _async_validate_credentials(
        self, username: str, password: str
    ) -> dict[str, str]:
        """Prova il login e ritorna un eventuale dizionario di errori per la UI."""
        errors: dict[str, str] = {}
        api = Ariston()
        try:
            logged_in = await api.async_connect(username, password)
        except ConnectionException:
            errors["base"] = "cannot_connect"
            return errors
        except Exception:
            _LOGGER.exception("Errore imprevisto durante il login ad Ariston Net")
            errors["base"] = "unknown"
            return errors

        if not logged_in:
            errors["base"] = "invalid_auth"

        return errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Primo (e unico) step: username e password dell'account Ariston Net."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            errors = await self._async_validate_credentials(username, password)

            if not errors:
                return self.async_create_entry(
                    title=username,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_LANGUAGE_TAG: self.hass.config.language
                        or DEFAULT_LANGUAGE_TAG,
                        CONF_IS_METRIC: self.hass.config.units.temperature_unit
                        == UnitOfTemperature.CELSIUS,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Avviato automaticamente quando il coordinator solleva ConfigEntryAuthFailed."""
        self._reauth_username = entry_data[CONF_USERNAME]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Chiede solo la nuova password, senza ricreare device/entità."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = self._reauth_username or ""
            password = user_input[CONF_PASSWORD]
            errors = await self._async_validate_credentials(username, password)

            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"username": self._reauth_username or ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return AristonNetOptionsFlow()


class AristonNetOptionsFlow(OptionsFlow):
    """Opzioni: intervalli di polling e selezione dei dispositivi da esporre."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        coordinator = getattr(self.config_entry, "runtime_data", None)
        gateway_choices: list[SelectOptionDict] = []
        if coordinator is not None and coordinator.data is not None:
            gateway_choices = [
                SelectOptionDict(value=gw, label=dev.name)
                for gw, dev in coordinator.data.devices.items()
            ]

        schema: dict[Any, Any] = {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=3600,
                    step=10,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            vol.Optional(
                CONF_ENERGY_SCAN_INTERVAL,
                default=current.get(
                    CONF_ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_ENERGY_SCAN_INTERVAL,
                    max=21600,
                    step=60,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }

        if gateway_choices:
            schema[
                vol.Optional(
                    CONF_ENABLED_GATEWAYS,
                    default=current.get(
                        CONF_ENABLED_GATEWAYS,
                        [c["value"] for c in gateway_choices],
                    ),
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=gateway_choices,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
