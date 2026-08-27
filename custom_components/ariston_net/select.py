"""Piattaforma select per Ariston Net (modalità a livello di impianto).

Copre la modalità estate/inverno/spegnimento (solo caldaie Galevo, le
uniche che espongono un plant mode) e, dove presenti, le modalità ibrida e
del buffer. La modalità "Holiday" con data di fine viene invece esposta
come servizio (`ariston_net.set_holiday` / `ariston_net.cancel_holiday`)
sull'entità plant mode, perché richiede un parametro (la data) che il
modello a singola opzione di un select non può rappresentare bene.
"""

from __future__ import annotations

import logging
from datetime import date

import voluptuous as vol
from ariston.const import PlantMode
from ariston.galevo_device import AristonGalevoDevice
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    async_get_current_platform,
)

from .const import ATTR_END_DATE, SERVICE_CANCEL_HOLIDAY, SERVICE_SET_HOLIDAY
from .coordinator import AristonNetConfigEntry
from .entity import AristonNetEntity

_LOGGER = logging.getLogger(__name__)

SET_HOLIDAY_SCHEMA = {vol.Required(ATTR_END_DATE): cv.date}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonNetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea le entità select per ogni caldaia Galevo."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = []

    for gateway, device_entry in coordinator.data.devices.items():
        device = device_entry.device
        if not isinstance(device, AristonGalevoDevice):
            continue
        if device.plant_mode_supported:
            entities.append(AristonNetPlantModeSelect(coordinator, gateway))
        if device.hybrid_mode_value is not None and device.hybrid_mode_options:
            entities.append(AristonNetHybridModeSelect(coordinator, gateway))
        if device.buffer_control_mode_value is not None and (
            device.buffer_control_mode_options
        ):
            entities.append(AristonNetBufferControlModeSelect(coordinator, gateway))

    async_add_entities(entities)

    platform = async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_HOLIDAY,
        SET_HOLIDAY_SCHEMA,
        "async_set_holiday_service",
    )
    platform.async_register_entity_service(
        SERVICE_CANCEL_HOLIDAY,
        None,
        "async_cancel_holiday_service",
    )


class AristonNetPlantModeSelect(AristonNetEntity, SelectEntity):
    """Modalità dell'impianto (Estate/Inverno/Solo riscaldamento/Spento/...)."""

    _attr_translation_key = "plant_mode"

    def __init__(self, coordinator, gateway: str) -> None:
        super().__init__(coordinator, gateway, "plant_mode")
        self._attr_unique_id = f"{gateway}_plant_mode"

    @property
    def options(self) -> list[str]:
        return self.ariston_device.plant_mode_opt_texts or []

    @property
    def current_option(self) -> str | None:
        text = self.ariston_device.plant_mode_text
        return text if text in self.options else None

    async def async_select_option(self, option: str) -> None:
        device = self.ariston_device
        try:
            index = device.plant_mode_opt_texts.index(option)
        except (ValueError, TypeError) as err:
            raise ValueError(f"Opzione modalità impianto non valida: {option}") from err
        plant_mode = PlantMode(device.plant_mode_options[index])
        await device.async_set_plant_mode(plant_mode)
        self.async_write_ha_state()

    async def async_set_holiday_service(self, end_date: date) -> None:
        """Servizio ariston_net.set_holiday: imposta la modalità vacanza."""
        await self.ariston_device.async_set_holiday(end_date)
        self.async_write_ha_state()

    async def async_cancel_holiday_service(self) -> None:
        """Servizio ariston_net.cancel_holiday: annulla la modalità vacanza."""
        await self.ariston_device.async_set_holiday(None)
        self.async_write_ha_state()


class AristonNetHybridModeSelect(AristonNetEntity, SelectEntity):
    """Modalità del sistema ibrido (caldaia + pompa di calore)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, gateway: str) -> None:
        super().__init__(coordinator, gateway, "hybrid_mode")
        self._attr_unique_id = f"{gateway}_hybrid_mode"

    @property
    def options(self) -> list[str]:
        return self.ariston_device.hybrid_mode_opt_texts or []

    @property
    def current_option(self) -> str | None:
        # `hybrid_mode` solleva ValueError se il valore corrente non è tra
        # le opzioni note (può capitare con dati transitori appena dopo un
        # cambio cloud): meglio "sconosciuto" che un'eccezione che rompe
        # l'aggiornamento dell'entità.
        try:
            value = self.ariston_device.hybrid_mode
        except (ValueError, TypeError):
            return None
        return value if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.ariston_device.async_set_hybrid_mode(option)
        self.async_write_ha_state()


class AristonNetBufferControlModeSelect(AristonNetEntity, SelectEntity):
    """Modalità di controllo del buffer termico."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, gateway: str) -> None:
        super().__init__(coordinator, gateway, "buffer_control_mode")
        self._attr_unique_id = f"{gateway}_buffer_control_mode"

    @property
    def options(self) -> list[str]:
        return self.ariston_device.buffer_control_mode_opt_texts or []

    @property
    def current_option(self) -> str | None:
        try:
            value = self.ariston_device.buffer_control_mode
        except (ValueError, TypeError):
            return None
        return value if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.ariston_device.async_set_buffer_control_mode(option)
        self.async_write_ha_state()
