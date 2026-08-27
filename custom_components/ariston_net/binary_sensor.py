"""Piattaforma binary_sensor per Ariston Net."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from ariston.base_device import AristonBaseDevice
from ariston.bsb_device import AristonBsbDevice
from ariston.const import DeviceAttribute
from ariston.galevo_device import AristonGalevoDevice
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AristonNetConfigEntry
from .entity import AristonNetEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AristonNetBinarySensorDescription(BinarySensorEntityDescription):
    """Descrizione di un binary_sensor Ariston Net."""

    is_on_fn: Callable[[AristonBaseDevice], bool | None] = lambda device: None
    supported_fn: Callable[[AristonBaseDevice], bool] = lambda device: True


_OFFLINE_SENSOR = AristonNetBinarySensorDescription(
    key="offline_48h",
    translation_key="offline_48h",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    is_on_fn=lambda device: bool(
        device.attributes.get(DeviceAttribute.IS_OFFLINE_48H)
    ),
)

_GALEVO_SENSORS: tuple[AristonNetBinarySensorDescription, ...] = (
    AristonNetBinarySensorDescription(
        key="flame",
        translation_key="flame",
        device_class=BinarySensorDeviceClass.HEAT,
        is_on_fn=lambda device: device.is_flame_on_value,
    ),
    AristonNetBinarySensorDescription(
        key="heating_pump",
        translation_key="heating_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda device: device.is_heating_pump_on_value,
    ),
    AristonNetBinarySensorDescription(
        key="holiday_mode",
        translation_key="holiday_mode",
        is_on_fn=lambda device: bool(device.holiday_mode_value),
    ),
)

_BSB_SENSORS: tuple[AristonNetBinarySensorDescription, ...] = (
    AristonNetBinarySensorDescription(
        key="flame",
        translation_key="flame",
        device_class=BinarySensorDeviceClass.HEAT,
        is_on_fn=lambda device: device.is_flame_on_value,
    ),
)

_VELIS_SENSORS: tuple[AristonNetBinarySensorDescription, ...] = (
    AristonNetBinarySensorDescription(
        key="heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.HEAT,
        is_on_fn=lambda device: device.is_heating,
        supported_fn=lambda device: hasattr(device, "is_heating"),
    ),
    AristonNetBinarySensorDescription(
        key="anti_legionella_running",
        translation_key="anti_legionella_running",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda device: device.is_antileg,
        supported_fn=lambda device: hasattr(device, "is_antileg"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonNetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea le entità binary_sensor supportate per ogni dispositivo."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []

    for gateway, device_entry in coordinator.data.devices.items():
        device = device_entry.device

        descriptions = [_OFFLINE_SENSOR]
        if isinstance(device, AristonGalevoDevice):
            descriptions.extend(_GALEVO_SENSORS)
        elif isinstance(device, AristonBsbDevice):
            descriptions.extend(_BSB_SENSORS)
        else:
            descriptions.extend(_VELIS_SENSORS)

        for description in descriptions:
            if description.supported_fn(device):
                entities.append(
                    AristonNetBinarySensor(coordinator, gateway, description)
                )

    async_add_entities(entities)


class AristonNetBinarySensor(AristonNetEntity, BinarySensorEntity):
    """Binary sensor generico Ariston Net guidato da una description."""

    entity_description: AristonNetBinarySensorDescription

    def __init__(
        self,
        coordinator,
        gateway: str,
        description: AristonNetBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, gateway, description.translation_key)
        self.entity_description = description
        self._attr_unique_id = f"{gateway}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.ariston_device)
