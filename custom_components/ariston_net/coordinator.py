"""DataUpdateCoordinator per Ariston Net.

Il coordinator è il cuore della bonifica architetturale: centralizza il
polling per *tutti* i dispositivi dell'account (una sola sessione/token,
un solo giro di richieste per ciclo) e distingue esplicitamente i tre modi
in cui il cloud Ariston può fallire, cosa che la libreria di terze parti
`ariston` non fa in modo coerente:

* credenziali non più valide (password cambiata, token rifiutato due volte)
  -> ConfigEntryAuthFailed, che fa scattare il flusso di re-auth nativo di
  Home Assistant invece di lasciare l'integrazione bloccata;
* cloud irraggiungibile / timeout / errore HTTP generico -> UpdateFailed,
  gestito nativamente dal coordinator (entità che passano a `unavailable`
  e nuovo tentativo al giro successivo, senza far crashare l'integrazione
  né bloccare l'event loop);
* HTTP 429 (rate limit) -> invece di continuare a martellare l'endpoint
  ogni `scan_interval`, il coordinator allarga temporaneamente l'intervallo
  di polling (RATE_LIMIT_BACKOFF) e lo ripristina al primo successo.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

import aiohttp
from ariston import Ariston
from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice
from ariston.const import DeviceAttribute
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    RATE_LIMIT_BACKOFF,
)

_LOGGER = logging.getLogger(__name__)

# Errori di rete che la libreria `ariston` non normalizza sempre in
# ConnectionException (in particolare timeout/errori di connessione a
# livello aiohttp possono propagarsi grezzi dalle chiamate `async_*`).
_TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    ConnectionException,
    aiohttp.ClientError,
    asyncio.TimeoutError,
    TimeoutError,
)

_AUTH_FAILURE_MARKERS: tuple[str, ...] = (
    "login failed",
    "invalid token",
)


@dataclass(slots=True)
class AristonNetDevice:
    """Wrapper leggero attorno a un device della libreria `ariston`."""

    gateway: str
    device: AristonBaseDevice
    name: str
    serial_number: str | None
    available: bool = True


@dataclass(slots=True)
class AristonNetData:
    """Snapshot dei dati esposti dal coordinator alle entità."""

    devices: dict[str, AristonNetDevice] = field(default_factory=dict)


type AristonNetConfigEntry = ConfigEntry[AristonNetCoordinator]


class AristonNetCoordinator(DataUpdateCoordinator[AristonNetData]):
    """Coordina il polling di tutti i dispositivi Ariston Net di un account."""

    config_entry: AristonNetConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AristonNetConfigEntry) -> None:
        self._entry = entry
        self._username: str = entry.data[CONF_USERNAME]
        self._password: str = entry.data[CONF_PASSWORD]
        self._language_tag: str = entry.data.get(CONF_LANGUAGE_TAG, DEFAULT_LANGUAGE_TAG)
        self._is_metric: bool = entry.data.get(CONF_IS_METRIC, True)
        self._ariston = Ariston()
        self._default_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._energy_interval = timedelta(
            seconds=entry.options.get(
                CONF_ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL
            )
        )
        self._last_energy_update: dict[str, float] = {}  # gateway -> loop.time()
        self._connected = False

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self._default_interval,
        )

    @property
    def enabled_gateways(self) -> list[str] | None:
        """Elenco dei gateway abilitati dall'utente, None = tutti."""
        gateways = self.config_entry.options.get(CONF_ENABLED_GATEWAYS)
        return list(gateways) if gateways else None

    async def async_login(self) -> None:
        """Effettua il login iniziale e la discovery dei dispositivi.

        Chiamato una sola volta da async_setup_entry. Solleva
        ConfigEntryAuthFailed se le credenziali sono errate e
        ConfigEntryNotReady per qualsiasi altro problema di connessione,
        così Home Assistant sa se proporre subito la re-autenticazione o
        se limitarsi a riprovare più tardi.
        """
        try:
            logged_in = await self._ariston.async_connect(
                self._username, self._password
            )
        except _TRANSIENT_ERRORS as err:
            raise ConfigEntryNotReady(
                f"Impossibile contattare il cloud Ariston Net: {err}"
            ) from err

        if not logged_in:
            raise ConfigEntryAuthFailed(
                "Credenziali Ariston Net non valide o rifiutate dal cloud"
            )

        self._connected = True

        try:
            await self._ariston.async_discover()
        except _TRANSIENT_ERRORS as err:
            raise ConfigEntryNotReady(
                f"Login riuscito ma discovery dispositivi fallita: {err}"
            ) from err

    async def _async_build_devices(self) -> dict[str, AristonNetDevice]:
        """Istanzia gli oggetti device tipizzati per ogni gateway scoperto."""
        enabled = self.enabled_gateways
        devices: dict[str, AristonNetDevice] = {}

        for raw in self._ariston.cloud_devices:
            gateway = raw.get(DeviceAttribute.GW)
            if not gateway:
                continue
            if enabled is not None and gateway not in enabled:
                continue

            device = await self._ariston.async_hello(
                gateway, self._is_metric, self._language_tag
            )
            if device is None:
                _LOGGER.warning(
                    "Dispositivo Ariston Net %s non supportato (sys/whe type "
                    "sconosciuto): verrà ignorato",
                    gateway,
                )
                continue

            devices[gateway] = AristonNetDevice(
                gateway=gateway,
                device=device,
                name=raw.get(DeviceAttribute.NAME) or gateway,
                serial_number=raw.get(DeviceAttribute.SN),
            )

        if not devices:
            raise ConfigEntryNotReady(
                "Nessun dispositivo Ariston Net supportato trovato per questo account"
            )

        return devices

    async def _async_update_data(self) -> AristonNetData:
        """Aggiorna lo stato di tutti i dispositivi in un solo ciclo."""
        if not self._connected:
            await self.async_login()

        if self.data is None:
            devices = await self._async_build_devices()
        else:
            devices = self.data.devices

        results = await asyncio.gather(
            *(self._async_update_device(dev) for dev in devices.values()),
            return_exceptions=True,
        )

        auth_error: ConfigEntryAuthFailed | None = None
        transient_errors: list[Exception] = []

        for dev, result in zip(devices.values(), results, strict=True):
            if result is None:
                dev.available = True
                continue

            dev.available = False
            if isinstance(result, ConfigEntryAuthFailed):
                auth_error = result
            elif isinstance(result, Exception):
                transient_errors.append(result)
                _LOGGER.debug(
                    "Aggiornamento fallito per il dispositivo %s: %s",
                    dev.gateway,
                    result,
                )

        # Se anche un solo dispositivo segnala credenziali non valide,
        # è inutile continuare a riprovare: chiediamo subito la re-auth.
        if auth_error is not None:
            self._connected = False
            raise auth_error

        if transient_errors and all(not dev.available for dev in devices.values()):
            # Tutti i dispositivi falliscono: probabilmente il cloud Ariston
            # è giù. Segnaliamo UpdateFailed (le entità passano a
            # unavailable) invece di propagare un'eccezione grezza.
            self._maybe_apply_rate_limit_backoff(transient_errors[0])
            raise UpdateFailed(
                f"Cloud Ariston Net non raggiungibile: {transient_errors[0]}"
            )

        if not transient_errors:
            self._restore_default_interval()

        return AristonNetData(devices=devices)

    async def _async_update_device(self, entry: AristonNetDevice) -> None:
        """Aggiorna lo stato (e periodicamente l'energia) di un device."""
        try:
            await entry.device.async_update_state()
            await self._async_maybe_update_energy(entry)
        except _TRANSIENT_ERRORS as err:
            if self._looks_like_auth_failure(err):
                raise ConfigEntryAuthFailed(
                    f"Sessione Ariston Net scaduta per {entry.gateway}: {err}"
                ) from err
            raise

    async def _async_maybe_update_energy(self, entry: AristonNetDevice) -> None:
        """Aggiorna i consumi energetici al massimo ogni `_energy_interval`.

        Il primo giro (nessun timestamp registrato per questo gateway) viene
        sempre eseguito, così le entità sensor "energia" vengono popolate
        subito al primo avvio invece di restare assenti finché non passa
        un intero `_energy_interval`.
        """
        loop_time = self.hass.loop.time()
        last = self._last_energy_update.get(entry.gateway)
        if last is not None and loop_time - last < self._energy_interval.total_seconds():
            return
        try:
            await entry.device.async_update_energy()
        except _TRANSIENT_ERRORS as err:
            # I consumi sono un "nice to have": un fallimento qui non deve
            # far sparire l'intero dispositivo, lo logghiamo soltanto.
            _LOGGER.debug(
                "Aggiornamento consumi energetici fallito per %s: %s",
                entry.gateway,
                err,
            )
        else:
            self._last_energy_update[entry.gateway] = loop_time

    @staticmethod
    def _looks_like_auth_failure(err: Exception) -> bool:
        message = str(err).lower()
        return any(marker in message for marker in _AUTH_FAILURE_MARKERS)

    def _maybe_apply_rate_limit_backoff(self, err: Exception) -> None:
        """Allarga temporaneamente l'intervallo di polling dopo un 429."""
        if "429" not in str(err):
            return
        if self.update_interval == RATE_LIMIT_BACKOFF:
            return
        _LOGGER.warning(
            "Il cloud Ariston Net ha risposto 429 (troppe richieste): "
            "l'intervallo di aggiornamento viene temporaneamente esteso a %s",
            RATE_LIMIT_BACKOFF,
        )
        self.update_interval = RATE_LIMIT_BACKOFF

    def _restore_default_interval(self) -> None:
        if self.update_interval != self._default_interval:
            _LOGGER.info(
                "Ripristino l'intervallo di aggiornamento standard (%s) dopo "
                "il recupero dal rate limiting",
                self._default_interval,
            )
            self.update_interval = self._default_interval
