"""Piattaforma climate per le zone di riscaldamento (Galevo e Bsb).

Le due famiglie di dispositivi con zone (caldaie "Galevo", es. Alteas One,
e sistemi con bus "Bsb") espongono un'interfaccia a metodi quasi identica
nella libreria `ariston` (get_zone_mode, get_measured_temp_value,
get_comfort_temp_value, set_comfort_temp, set_zone_mode, ...): l'unica
differenza reale è l'enum usato per la modalità di zona (ZoneMode vs
BsbZoneMode). Una sola classe di entità copre quindi entrambe le famiglie.
"""

from __future__ import annotations

import logging
from typing import Any

from ariston.base_device import AristonBaseDevice
from ariston.bsb_device import AristonBsbDevice
from ariston.const import BsbZoneMode, SystemType, ZoneMode
from ariston.galevo_device import AristonGalevoDevice
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_TENTHS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AristonNetConfigEntry
from .entity import AristonNetEntity

_LOGGER = logging.getLogger(__name__)

_ZONE_MODE_ENUM: dict[SystemType, type] = {
    SystemType.GALEVO: ZoneMode,
    SystemType.BSB: BsbZoneMode,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonNetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea un'entità climate per ogni zona di riscaldamento disponibile."""
    coordinator = entry.runtime_data
    entities: list[ClimateEntity] = []

    for gateway, device_entry in coordinator.data.devices.items():
        device = device_entry.device
        if not isinstance(device, (AristonGalevoDevice, AristonBsbDevice)):
            continue
        for zone in device.zone_numbers:
            entities.append(AristonNetZoneClimate(coordinator, gateway, zone))

    async_add_entities(entities)


def _zone_name(device: AristonBaseDevice, zone: int) -> str:
    if isinstance(device, AristonGalevoDevice):
        for zone_attrs in device.zones:
            if zone_attrs.get("num") == zone:
                name = zone_attrs.get("name")
                if name:
                    return name
    return f"Zona {zone}"


class AristonNetZoneClimate(AristonNetEntity, ClimateEntity):
    """Entità climate per una singola zona di riscaldamento/raffrescamento."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_TENTHS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator, gateway: str, zone: int) -> None:
        super().__init__(coordinator, gateway)
        self._zone = zone
        self._attr_unique_id = f"{gateway}_zone_{zone}_climate"
        self._attr_name = _zone_name(self.ariston_device, zone)
        self._zone_mode_enum = _ZONE_MODE_ENUM[self.ariston_device.system_type]

    @property
    def current_temperature(self) -> float | None:
        return self.ariston_device.get_measured_temp_value(self._zone)

    @property
    def target_temperature(self) -> float | None:
        return self.ariston_device.get_target_temp_value(self._zone)

    @property
    def target_temperature_step(self) -> float | None:
        return self.ariston_device.get_target_temp_step(self._zone)

    @property
    def min_temp(self) -> float:
        return self.ariston_device.get_comfort_temp_min(self._zone) or 7.0

    @property
    def max_temp(self) -> float:
        return self.ariston_device.get_comfort_temp_max(self._zone) or 30.0

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = [HVACMode.OFF]
        if self.ariston_device.is_zone_mode_options_contains_manual(self._zone):
            modes.append(HVACMode.HEAT)
        if self.ariston_device.is_zone_mode_options_contains_time_program(self._zone):
            modes.append(HVACMode.AUTO)
        return modes

    @property
    def hvac_mode(self) -> HVACMode | None:
        zone_mode = self.ariston_device.get_zone_mode(self._zone)
        if zone_mode == self._zone_mode_enum.OFF:
            return HVACMode.OFF
        if self.ariston_device.is_zone_in_manual_mode(self._zone):
            return HVACMode.HEAT
        if self.ariston_device.is_zone_in_time_program_mode(self._zone):
            return HVACMode.AUTO
        return None

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.ariston_device.is_flame_on_value:
            return (
                HVACAction.COOLING
                if self.ariston_device.is_plant_in_cool_mode
                else HVACAction.HEATING
            )
        return HVACAction.IDLE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.ariston_device.async_set_comfort_temp(temperature, self._zone)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        target = {
            HVACMode.OFF: self._zone_mode_enum.OFF,
            HVACMode.HEAT: self._zone_mode_enum.MANUAL,
            HVACMode.AUTO: self._zone_mode_enum.TIME_PROGRAM,
        }.get(hvac_mode)
        if target is None:
            _LOGGER.warning(
                "Modalità HVAC %s non supportata per la zona %s", hvac_mode, self._zone
            )
            return
        await self.ariston_device.async_set_zone_mode(target, self._zone)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
