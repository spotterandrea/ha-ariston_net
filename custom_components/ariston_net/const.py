"""Constanti per l'integrazione Ariston Net."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final[str] = "ariston_net"

# --- Config entry keys -----------------------------------------------------
CONF_LANGUAGE_TAG: Final[str] = "language_tag"
CONF_IS_METRIC: Final[str] = "is_metric"

# --- Options ----------------------------------------------------------------
CONF_SCAN_INTERVAL: Final[str] = "scan_interval"
CONF_ENERGY_SCAN_INTERVAL: Final[str] = "energy_scan_interval"
CONF_ENABLED_GATEWAYS: Final[str] = "enabled_gateways"

DEFAULT_SCAN_INTERVAL: Final[int] = 120  # secondi
MIN_SCAN_INTERVAL: Final[int] = 60  # secondi - protezione dal rate limiting (HTTP 429)
DEFAULT_ENERGY_SCAN_INTERVAL: Final[int] = 1800  # secondi (30 minuti)
MIN_ENERGY_SCAN_INTERVAL: Final[int] = 600  # secondi

DEFAULT_LANGUAGE_TAG: Final[str] = "it-IT"

# Numero di cicli di update "leggero" (solo stato) tra due aggiornamenti
# del blocco energia/consumi, che è più pesante e meno time-critical.
UPDATE_TIMEOUT: Final[timedelta] = timedelta(seconds=30)

# Backoff applicato temporaneamente quando il cloud Ariston risponde 429
# (troppe richieste). Vedi coordinator.py.
RATE_LIMIT_BACKOFF: Final[timedelta] = timedelta(minutes=10)

# Numero massimo di update falliti consecutivi prima di considerare il
# dispositivo realmente irraggiungibile (oltre alla gestione nativa del
# DataUpdateCoordinator).
MAX_CONSECUTIVE_FAILURES_LOG: Final[int] = 3

MANUFACTURER: Final[str] = "Ariston"

ATTR_GATEWAY: Final[str] = "gateway"
ATTR_END_DATE: Final[str] = "end_date"

SERVICE_SET_HOLIDAY: Final[str] = "set_holiday"
SERVICE_CANCEL_HOLIDAY: Final[str] = "cancel_holiday"
