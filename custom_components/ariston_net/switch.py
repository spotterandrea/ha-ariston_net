"""Piattaforma switch per Ariston Net.

Copre le impostazioni booleane esposte dai vari dispositivi: non tutte le
famiglie Velis supportano le stesse opzioni (es. il "boost" esiste solo su
Nuos Split, il "power option" solo su Lux2), quindi ogni entità viene
creata solo se il device concreto espone davvero il metodo corrispondente.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ariston.base_device import AristonBaseDevice
from ariston.const import DeviceProperties
from ariston.galevo_device import AristonGalevoDevice
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AristonNetConfigEntry
from .entity import AristonNetEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AristonNetSwitchDescription(SwitchEntityDescription):
    """Descrizione di uno switch Ariston Net."""

    is_on_fn: Callable[[AristonBaseDevice], bool | None] = lambda device: None
    turn_on_fn: Callable[[AristonBaseDevice], Awaitable[None]]
    turn_off_fn: Callable[[AristonBaseDevice], Awaitable[None]]
    supported_fn: Callable[[AristonBaseDevice], bool] = lambda device: True


_GALEVO_SWITCHES: tuple[AristonNetSwitchDescription, ...] = (
    AristonNetSwitchDescription(
        key="automatic_thermoregulation",
        translation_key="automatic_thermoregulation",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.automatic_thermoregulation),
        turn_on_fn=lambda device: device.async_set_automatic_thermoregulation(True),
        turn_off_fn=lambda device: device.async_set_automatic_thermoregulation(False),
    ),
    AristonNetSwitchDescription(
        key="quiet_mode",
        translation_key="quiet_mode",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.is_quiet_value),
        turn_on_fn=lambda device: device.async_set_is_quiet(True),
        turn_off_fn=lambda device: device.async_set_is_quiet(False),
        supported_fn=lambda device: bool(
            device.custom_features.get(DeviceProperties.IS_QUIET)
        ),
    ),
)

_VELIS_SWITCHES: tuple[AristonNetSwitchDescription, ...] = (
    AristonNetSwitchDescription(
        key="anti_legionella",
        translation_key="anti_legionella",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.water_anti_leg_value),
        turn_on_fn=lambda device: device.async_set_antilegionella(True),
        turn_off_fn=lambda device: device.async_set_antilegionella(False),
        supported_fn=lambda device: hasattr(device, "async_set_antilegionella"),
    ),
    AristonNetSwitchDescription(
        key="eco_mode",
        translation_key="eco_mode",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.water_heater_eco_value),
        turn_on_fn=lambda device: device.async_set_eco_mode(True),
        turn_off_fn=lambda device: device.async_set_eco_mode(False),
        supported_fn=lambda device: hasattr(device, "async_set_eco_mode"),
    ),
    AristonNetSwitchDescription(
        key="power_option",
        translation_key="power_option",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.water_heater_power_option_value),
        turn_on_fn=lambda device: device.async_set_water_heater_power_option(True),
        turn_off_fn=lambda device: device.async_set_water_heater_power_option(False),
        supported_fn=lambda device: hasattr(
            device, "async_set_water_heater_power_option"
        ),
    ),
    AristonNetSwitchDescription(
        key="boost",
        translation_key="boost",
        is_on_fn=lambda device: bool(device.water_heater_boost),
        turn_on_fn=lambda device: device.async_set_water_heater_boost(True),
        turn_off_fn=lambda device: device.async_set_water_heater_boost(False),
        supported_fn=lambda device: hasattr(device, "async_set_water_heater_boost"),
    ),
    AristonNetSwitchDescription(
        key="permanent_boost",
        translation_key="permanent_boost",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.permanent_boost_value),
        turn_on_fn=lambda device: device.async_set_permanent_boost_value(True),
        turn_off_fn=lambda device: device.async_set_permanent_boost_value(False),
        supported_fn=lambda device: hasattr(
            device, "async_set_permanent_boost_value"
        ),
    ),
    AristonNetSwitchDescription(
        key="anti_cooling",
        translation_key="anti_cooling",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.anti_cooling_value),
        turn_on_fn=lambda device: device.async_set_anti_cooling_value(True),
        turn_off_fn=lambda device: device.async_set_anti_cooling_value(False),
        supported_fn=lambda device: hasattr(device, "async_set_anti_cooling_value"),
    ),
    AristonNetSwitchDescription(
        key="night_mode",
        translation_key="night_mode",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda device: bool(device.night_mode_value),
        turn_on_fn=lambda device: device.async_set_night_mode_value(True),
        turn_off_fn=lambda device: device.async_set_night_mode_value(False),
        supported_fn=lambda device: hasattr(device, "async_set_night_mode_value"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonNetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Crea le entità switch supportate per ogni dispositivo."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []

    for gateway, device_entry in coordinator.data.devices.items():
        device = device_entry.device

        descriptions = list(_VELIS_SWITCHES)
        if isinstance(device, AristonGalevoDevice):
            descriptions = list(_GALEVO_SWITCHES)

        for description in descriptions:
            if description.supported_fn(device):
                entities.append(AristonNetSwitch(coordinator, gateway, description))

    async_add_entities(entities)


class AristonNetSwitch(AristonNetEntity, SwitchEntity):
    """Switch generico Ariston Net guidato da una description."""

    entity_description: AristonNetSwitchDescription

    def __init__(
        self, coordinator, gateway: str, description: AristonNetSwitchDescription
    ) -> None:
        super().__init__(coordinator, gateway, description.translation_key)
        self.entity_description = description
        self._attr_unique_id = f"{gateway}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.ariston_device)

    async def async_turn_on(self, **kwargs) -> None:
        await self.entity_description.turn_on_fn(self.ariston_device)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.entity_description.turn_off_fn(self.ariston_device)
        self.async_write_ha_state()
