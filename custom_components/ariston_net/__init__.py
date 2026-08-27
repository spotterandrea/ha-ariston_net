"""Integrazione Ariston Net per Home Assistant.

Bonifica architetturale pensata per sostituire lo scraping HTML della
vecchia integrazione "v2" e irrobustire la gestione degli errori rispetto
al fork "v3" basato su API: qui il polling passa da un unico
DataUpdateCoordinator per account (vedi coordinator.py), che distingue
esplicitamente le credenziali scadute (ConfigEntryAuthFailed -> re-auth
guidata) dai disservizi temporanei del cloud Ariston (UpdateFailed /
ConfigEntryNotReady), invece di lasciare l'integrazione bloccata quando
il servizio ha un hiccup.
"""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import AristonNetConfigEntry, AristonNetCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]


async def async_setup_entry(hass: HomeAssistant, entry: AristonNetConfigEntry) -> bool:
    """Configura Ariston Net da una config entry (nessuna configurazione YAML)."""
    coordinator = AristonNetCoordinator(hass, entry)

    # Login e discovery iniziali: qui vengono sollevate ConfigEntryAuthFailed
    # (credenziali errate -> Home Assistant propone subito la re-auth) o
    # ConfigEntryNotReady (cloud irraggiungibile -> Home Assistant ritenta
    # automaticamente con backoff crescente, senza marcare l'entry come
    # fallita in modo permanente).
    await coordinator.async_login()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AristonNetConfigEntry) -> bool:
    """Scarica una config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: AristonNetConfigEntry) -> None:
    """Ricarica l'integrazione quando le opzioni (es. scan interval) cambiano."""
    await hass.config_entries.async_reload(entry.entry_id)
