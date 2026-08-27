"""Piattaforma sensor per Ariston Net.

Sensori diagnostici/di misura comuni a tutti i dispositivi (consumi
energetici) più i sensori specifici delle caldaie Galevo (temperature di
mandata, pressione, segnale) e degli scaldacqua Velis (docce disponibili,
tempo residuo di riscaldamento).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from ariston.base_device import AristonBaseDevice
from ariston.bsb_device import AristonBsbDevice
from ariston.const import ConsumptionType, CustomDeviceFeatures
from ariston.galevo_device import AristonGalevoDevice
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AristonNetConfigEntry
from .entity import AristonNetEntity

_LOGGER = logging.getLogger(__name__)

_TEMP_UNIT_MAP = {"°C": UnitOfTemperature.CELSIUS, "°F": UnitOfTemperature.FAHRENHEIT}


@dataclass(frozen=True, kw_only=True)
class AristonNetSensorDescription(SensorEntityDescription):
    """Descrizione di un sensore Ariston Net con accessor e guardia opzionali."""

    value_fn: Callable[[AristonBaseDevice], object] = lambda device: None
    unit_fn: Callable[[AristonBaseDevice], str | None] | None = None
    supported_fn: Callable[[AristonBaseDevice], bool] = lambda device: True


def _energy_sensor(
    key: str, translation_key: str, consumption_type: ConsumptionType
) -> AristonNetSensorDescription:
    return AristonNetSensorDescription(
        key=key,
        translation_key=translation_key,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device, _ct=consumption_type: getattr(
            device, _CONSUMPTION_PROPERTY[_ct]
        ),
        supported_fn=lambda device, _ct=consumption_type: bool(
            device.custom_features.get(_ct.name)
        ),
    )


_CONSUMPTION_PROPERTY = {
    ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY: "central_heating_total_energy_consumption",
    ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY: "domestic_hot_water_total_energy_consumption",
    ConsumptionType.CENTRAL_HEATING_GAS: "central_heating_gas_consumption",
    ConsumptionType.DOMESTIC_HOT_WATER_GAS: "domestic_hot_water_gas_consumption",
    ConsumptionType.CENTRAL_HEATING_ELECTRICITY: "central_heating_electricity_consumption",
    ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY: "domestic_hot_water_electricity_consumption",
}

_COMMON_SENSORS: tuple[AristonNetSensorDescription, ...] = (
    _energy_sensor(
        "ch_total_energy",
        "central_heating_total_energy",
        ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY,
    ),
    _energy_sensor(
        "dhw_total_energy",
        "domestic_hot_water_total_energy",
        ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
    ),
    _energy_sensor(
        "ch_gas", "central_heating_gas", ConsumptionType.CENTRAL_HEATING_GAS
    ),
    _energy_sensor(
        "dhw_gas", "domestic_hot_water_gas", ConsumptionType.DOMESTIC_HOT_WATER_GAS
    ),
    _energy_sensor(
        "ch_electricity",
        "central_heating_electricity",
        ConsumptionType.CENTRAL_HEATING_ELECTRICITY,
    ),
    _energy_sensor(
        "dhw_electricity",
        "domestic_hot_water_electricity",
        ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY,
    ),
)

_GALEVO_SENSORS: tuple[AristonNetSensorDescription, ...] = (
    AristonNetSensorDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.outside_temp_value,
        unit_fn=lambda device: _TEMP_UNIT_MAP.get(
            device.outside_temp_unit, UnitOfTemperature.CELSIUS
        ),
        supported_fn=lambda device: bool(
            device.custom_features.get(CustomDeviceFeatures.HAS_OUTSIDE_TEMP)
        ),
    ),
    AristonNetSensorDescription(
        key="ch_flow_temperature",
        translation_key="ch_flow_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.ch_flow_temp_value,
        unit_fn=lambda device: _TEMP_UNIT_MAP.get(
            device.ch_flow_temp_unit, UnitOfTemperature.CELSIUS
        ),
    ),
    AristonNetSensorDescription(
        key="ch_flow_setpoint_temperature",
        translation_key="ch_flow_setpoint_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.ch_flow_setpoint_temp_value,
        unit_fn=lambda device: _TEMP_UNIT_MAP.get(
            device.ch_flow_setpoint_temp_unit, UnitOfTemperature.CELSIUS
        ),
    ),
    AristonNetSensorDescription(
        key="heating_circuit_pressure",
        translation_key="heating_circuit_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        value_fn=lambda device: device.heating_circuit_pressure_value,
    ),
    AristonNetSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda device: device.signal_strength_value,
    ),
    AristonNetSensorDescription(
        key="ch_return_temperature",
        translation_key="ch_return_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.ch_return_temp_value,
        unit_fn=lambda device: _TEMP_UNIT_MAP.get(
            device.ch_return_temp_unit, UnitOfTemperature.CELSIUS
        ),
    ),
)

_VELIS_REMAINING_TIME_SENSOR = AristonNetSensorDescription(
    key="remaining_heating_time",
    translation_key="remaining_heating_time",
    device_class=SensorDeviceClass.DURATION,
    native_unit_of_measurement=UnitOfTime.MINUTES,
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda device: (
        None if device.rm_tm_in_minutes < 0 else device.rm_tm_in_minutes
    ),
    supported_fn=lambda device: hasattr(device, "rm_tm_in_minutes"),
)

_VELIS_AVAILABLE_SHOWERS_SENSOR = AristonNetSensorDescription(
    key="available_showers",
    translation_key="available_showers",
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda device: device.av_shw_value,
    supported_fn=lambda device: hasattr(device, "av_shw_value"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonNetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea le entità sensor supportate per ogni dispositivo."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for gateway, device_entry in coordinator.data.devices.items():
        device = device_entry.device

        descriptions = list(_COMMON_SENSORS)
        if isinstance(device, AristonGalevoDevice):
            descriptions.extend(_GALEVO_SENSORS)
        if not isinstance(device, (AristonGalevoDevice, AristonBsbDevice)):
            # Famiglia Velis: sensori specifici degli scaldacqua.
            descriptions.append(_VELIS_REMAINING_TIME_SENSOR)
            descriptions.append(_VELIS_AVAILABLE_SHOWERS_SENSOR)

        for description in descriptions:
            if description.supported_fn(device):
                entities.append(AristonNetSensor(coordinator, gateway, description))

    async_add_entities(entities)


class AristonNetSensor(AristonNetEntity, SensorEntity):
    """Sensore generico Ariston Net guidato da una AristonNetSensorDescription."""

    entity_description: AristonNetSensorDescription

    def __init__(
        self, coordinator, gateway: str, description: AristonNetSensorDescription
    ) -> None:
        super().__init__(coordinator, gateway, description.translation_key)
        self.entity_description = description
        self._attr_unique_id = f"{gateway}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.ariston_device)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.unit_fn is not None:
            return self.entity_description.unit_fn(self.ariston_device)
        return super().native_unit_of_measurement
