"""Piattaforma water_heater per Ariston Net.

Copre in un'unica implementazione tutta la famiglia Velis (Evo, Evo2,
Andris2, Lux, Lux2, Lydos, Lydos Hybrid, Nuos Split, Evo One) grazie
all'interfaccia comune esposta dalla libreria `ariston` per questi
dispositivi, oltre al circuito ACS delle caldaie Galevo e ai sistemi Bsb.
"""

from __future__ import annotations

import logging
from typing import Any

from ariston.base_device import AristonBaseDevice
from ariston.const import SystemType
from ariston.velis_base_device import AristonVelisBaseDevice
from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AristonNetConfigEntry
from .entity import AristonNetEntity

_LOGGER = logging.getLogger(__name__)

_UNIT_MAP = {"°C": UnitOfTemperature.CELSIUS, "°F": UnitOfTemperature.FAHRENHEIT}

_BASE_FEATURES = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE
    | WaterHeaterEntityFeature.OPERATION_MODE
)
_VELIS_FEATURES = _BASE_FEATURES | WaterHeaterEntityFeature.ON_OFF


def _temperature_unit(device: AristonBaseDevice) -> str:
    unit = device.water_heater_temperature_unit
    return _UNIT_MAP.get(unit, UnitOfTemperature.CELSIUS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonNetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea le entità water_heater per ogni dispositivo compatibile."""
    coordinator = entry.runtime_data
    entities: list[WaterHeaterEntity] = []

    for gateway, device_entry in coordinator.data.devices.items():
        device = device_entry.device
        if isinstance(device, AristonVelisBaseDevice):
            entities.append(AristonNetVelisWaterHeater(coordinator, gateway))
        elif device.system_type in (SystemType.GALEVO, SystemType.BSB) and (
            device.system_type is SystemType.BSB or device.has_dhw
        ):
            entities.append(AristonNetBoilerWaterHeater(coordinator, gateway))

    async_add_entities(entities)


class _AristonNetWaterHeaterBase(AristonNetEntity, WaterHeaterEntity):
    """Comportamento comune: temperatura target e modalità operativa."""

    _attr_supported_features = _BASE_FEATURES
    _attr_precision = PRECISION_WHOLE
    _attr_translation_key = "water_heater"

    def __init__(self, coordinator, gateway: str) -> None:
        super().__init__(coordinator, gateway)
        self._attr_unique_id = f"{gateway}_water_heater"

    @property
    def temperature_unit(self) -> str:
        return _temperature_unit(self.ariston_device)

    @property
    def current_temperature(self) -> float | None:
        return self.ariston_device.water_heater_current_temperature

    @property
    def target_temperature(self) -> float | None:
        return self.ariston_device.water_heater_target_temperature

    @property
    def min_temp(self) -> float:
        return self.ariston_device.water_heater_minimum_temperature

    @property
    def max_temp(self) -> float | None:
        return self.ariston_device.water_heater_maximum_temperature

    @property
    def target_temperature_step(self) -> float | None:
        return self.ariston_device.water_heater_temperature_step

    @property
    def operation_list(self) -> list[str]:
        return self.ariston_device.water_heater_mode_operation_texts

    @property
    def current_operation(self) -> str | None:
        return self.ariston_device.water_heater_current_mode_text

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        await self.ariston_device.async_set_water_heater_temperature(temperature)
        self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        await self.ariston_device.async_set_water_heater_operation_mode(
            operation_mode
        )
        self.async_write_ha_state()


class AristonNetVelisWaterHeater(_AristonNetWaterHeaterBase):
    """Scaldacqua Velis (Evo, Lydos, Lux, Nuos Split, ...): supporta on/off."""

    _attr_supported_features = _VELIS_FEATURES

    @property
    def is_on(self) -> bool | None:
        return self.ariston_device.water_heater_power_value

    async def async_turn_on(self) -> None:
        await self.ariston_device.async_set_power(True)
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        await self.ariston_device.async_set_power(False)
        self.async_write_ha_state()


class AristonNetBoilerWaterHeater(_AristonNetWaterHeaterBase):
    """Circuito ACS di una caldaia Galevo o di un sistema Bsb."""
