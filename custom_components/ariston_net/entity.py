"""Entità di base condivisa da tutte le piattaforme Ariston Net."""

from __future__ import annotations

from ariston.base_device import AristonBaseDevice
from ariston.const import SystemType, WheType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import AristonNetCoordinator, AristonNetDevice

_MODEL_NAMES: dict[WheType, str] = {
    WheType.Evo: "Velis Evo",
    WheType.Evo2: "Velis Evo2",
    WheType.LydosHybrid: "Velis Lydos Hybrid",
    WheType.Lydos: "Velis Lydos Wi-Fi",
    WheType.NuosSplit: "Nuos Split",
    WheType.Andris2: "Andris2",
    WheType.Lux2: "Velis Lux2",
    WheType.Lux: "Velis Lux",
}

_SYSTEM_MODEL_NAMES: dict[SystemType, str] = {
    SystemType.GALEVO: "Caldaia / pompa di calore (Galevo)",
    SystemType.BSB: "Sistema con bus BSB",
    SystemType.GALILEO1: "Galileo (gen. 1)",
    SystemType.GALILEO2: "Galileo (gen. 2)",
}


def device_model_name(device: AristonBaseDevice) -> str:
    """Ricava un nome modello leggibile.

    Il cloud Ariston Net non espone un nome commerciale (es. "Alteas One"),
    solo un codice di system type e, per gli scaldacqua, un whe type: è il
    massimo dettaglio disponibile senza fare scraping dell'app ufficiale,
    quindi ci limitiamo a tradurre questi codici in etichette leggibili.
    """
    if device.system_type is SystemType.VELIS:
        return _MODEL_NAMES.get(device.whe_type, f"Velis (whe type {device.whe_type})")
    return _SYSTEM_MODEL_NAMES.get(
        device.system_type, f"Sistema Ariston ({device.system_type})"
    )


class AristonNetEntity(CoordinatorEntity[AristonNetCoordinator]):
    """Entità base: tutte le entità Ariston Net hanno has_entity_name=True."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AristonNetCoordinator,
        gateway: str,
        translation_key: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._gateway = gateway
        if translation_key is not None:
            self._attr_translation_key = translation_key

    @property
    def _device_entry(self) -> AristonNetDevice:
        return self.coordinator.data.devices[self._gateway]

    @property
    def ariston_device(self) -> AristonBaseDevice:
        """Il device tipizzato (Galevo/Velis/Bsb) della libreria `ariston`."""
        return self._device_entry.device

    @property
    def available(self) -> bool:
        """L'entità è disponibile solo se il coordinator E il device lo sono."""
        return super().available and self._device_entry.available

    @property
    def device_info(self) -> DeviceInfo:
        device = self.ariston_device
        return DeviceInfo(
            identifiers={(DOMAIN, self._gateway)},
            name=self._device_entry.name,
            manufacturer=MANUFACTURER,
            model=device_model_name(device),
            sw_version=device.firmware_version,
            serial_number=self._device_entry.serial_number,
        )
