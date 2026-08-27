# Ariston Net per Home Assistant

[![hassfest](https://img.shields.io/github/actions/workflow/status/spotterandrea/ha-ariston-net/validate.yaml?label=hassfest)](https://github.com/your-org/ha-ariston-net/actions)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Release](https://img.shields.io/github/v/release/spotterandrea/ha-ariston-net)](https://github.com/spotterandrea/ha-ariston-net/releases)
[![License](https://img.shields.io/github/license/spotterandrea/ha-ariston-net)](LICENSE)

Integrazione custom per Home Assistant che collega caldaie, sistemi ibridi e
scaldacqua **Ariston Net** (app "Ariston Net" / "Ariston") tramite le API
cloud ufficiali.

Questa integrazione **non** reinventa il protocollo cloud Ariston: si
appoggia alla libreria PyPI [`ariston`](https://pypi.org/project/ariston/)
(già usata dal fork `fustom/ariston-remotethermo-home-assistant-v3`), che ha
già fatto il lavoro di reverse engineering delle API. Il valore aggiunto di
questo progetto è tutto nello strato di integrazione con Home Assistant:

- un unico `DataUpdateCoordinator` per account, che centralizza il polling
  di tutti i dispositivi invece di farne uno indipendente per entità;
- gestione **esplicita e differenziata** degli errori cloud: credenziali
  scadute → flusso di re-autenticazione guidato (`ConfigEntryAuthFailed`);
  cloud irraggiungibile → `ConfigEntryNotReady`/`UpdateFailed` con retry
  automatico; risposta `HTTP 429` (troppe richieste) → backoff temporaneo
  automatico dell'intervallo di polling;
- `ConfigFlow`/`OptionsFlow` completi via UI (nessuna riga YAML richiesta);
- entità con `unique_id`, `device_info` e `EntityCategory` coerenti con gli
  standard più recenti di Home Assistant.

## Requisiti

- Home Assistant **2024.6** o successivo (usa `ConfigEntry.runtime_data` e
  gli helper di re-auth più recenti).
- Un account Ariston Net/Ariston attivo, con almeno un dispositivo
  registrato.
- Nessun requisito hardware locale: la comunicazione è interamente cloud
  (`iot_class: cloud_polling`).

## Dispositivi supportati

| Famiglia | Modelli | Piattaforme create |
|---|---|---|
| Galevo (caldaie/pompe di calore con zone, es. Alteas One) | Sistemi con `sys=GALEVO` | `climate` (una per zona), `water_heater` (se ha ACS), `sensor`, `binary_sensor`, `switch`, `select` |
| Velis | Evo, Evo2, Andris2, Lux, Lux2, Lydos Wi-Fi, Lydos Hybrid, Nuos Split | `water_heater`, `sensor`, `binary_sensor`, `switch` |
| Bsb (sistemi con bus BSB) | Sistemi con `sys=BSB` | `climate` (una per zona), `water_heater` |

Il cloud Ariston Net non espone un nome commerciale (es. "Alteas One 24"),
solo un codice di system/whe type: è il massimo dettaglio disponibile senza
fare scraping dell'app ufficiale.

## Installazione

### Tramite HACS (consigliato)

1. HACS → Integrazioni → menu (⋮) → **Repository personalizzate**.
2. Aggiungi `https://github.com/spotterandrea/ha-ariston_net` come categoria
   *Integration*.
3. Cerca "Ariston Net" in HACS e installa.
4. Riavvia Home Assistant.

### Manuale

1. Copia la cartella `custom_components/ariston_net` in
   `<config>/custom_components/ariston_net`.
2. Riavvia Home Assistant.

## Configurazione

Tutta la configurazione avviene da UI, non è previsto (né supportato) YAML
legacy:

1. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**.
2. Cerca "Ariston Net".
3. Inserisci l'email e la password del tuo account Ariston Net.
4. I dispositivi dell'account vengono rilevati automaticamente.

Se la password dell'account cambia, l'integrazione lo rileva da sola e
propone un flusso di **re-autenticazione** guidato (notifica in
Impostazioni → Dispositivi e servizi) invece di smettere silenziosamente di
funzionare.

### Opzioni

Dalla scheda dell'integrazione → **Opzioni**:

| Opzione | Default | Note |
|---|---|---|
| Intervallo di aggiornamento | 120 s | Minimo consigliato 60 s per non incorrere in HTTP 429 |
| Intervallo aggiornamento consumi energetici | 1800 s | Chiamata più pesante, aggiornata meno spesso |
| Dispositivi da includere | tutti | Utile con account che gestiscono più abitazioni |

## Entità esposte

| Piattaforma | Entità | Note |
|---|---|---|
| `climate` | Una per zona (Galevo/Bsb) | `hvac_mode` off/heat/auto, temperatura target = comfort della zona |
| `water_heater` | Una per scaldacqua o per il circuito ACS della caldaia | Elenco modalità operative dinamico da API |
| `select` | Modalità impianto (estate/inverno/solo riscaldamento/...) | Solo Galevo |
| `select` | Modalità ibrida / controllo buffer | Solo se il sistema li supporta |
| `sensor` | Temperature, pressione circuito, segnale, consumi energetici | Alcuni disabilitati di default (diagnostici secondari) |
| `binary_sensor` | Fiamma, pompa di riscaldamento, vacanza, offline da 48h, ciclo antilegionella | |
| `switch` | Termoregolazione automatica, modalità silenziosa, eco, antilegionella, boost, ... | Create solo se il dispositivo concreto le supporta |

### Servizi personalizzati (`services.yaml`)

| Servizio | Target | Parametri | Descrizione |
|---|---|---|---|
| `ariston_net.set_holiday` | entità `select` modalità impianto | `end_date` (data) | Attiva la modalità vacanza fino alla data indicata |
| `ariston_net.cancel_holiday` | entità `select` modalità impianto | — | Disattiva la modalità vacanza |

## Esempi

### Automazione: avvisa se il dispositivo risulta offline da 48h

```yaml
automation:
  - alias: "Ariston Net offline da troppo tempo"
    trigger:
      - platform: state
        entity_id: binary_sensor.caldaia_offline_da_piu_di_48h
        to: "on"
    action:
      - service: notify.mobile_app_il_mio_telefono
        data:
          message: "La caldaia risulta offline sul cloud Ariston da più di 48 ore."
```

### Script: imposta la vacanza per due settimane

```yaml
script:
  vacanza_ariston:
    sequence:
      - service: ariston_net.set_holiday
        target:
          entity_id: select.caldaia_modalita_impianto
        data:
          end_date: "{{ (now() + timedelta(days=14)).strftime('%Y-%m-%d') }}"
```

### Card Lovelace di esempio

```yaml
type: entities
title: Caldaia
entities:
  - entity: climate.caldaia_soggiorno
  - entity: water_heater.caldaia_acqua_calda_sanitaria
  - entity: select.caldaia_modalita_impianto
  - entity: sensor.caldaia_pressione_circuito_di_riscaldamento
  - entity: binary_sensor.caldaia_fiamma
```

## Troubleshooting

Per log di debug dettagliati (utili per segnalare un problema):

```yaml
logger:
  default: info
  logs:
    custom_components.ariston_net: debug
    ariston: debug
```

Errori comuni:

- **"Impossibile contattare il cloud Ariston Net"** in fase di setup: il
  servizio Ariston Net ha probabilmente un disservizio lato server (capita,
  vedi [issue #433 del progetto upstream](https://github.com/fustom/ariston-remotethermo-home-assistant-v3/issues/433)).
  L'integrazione ritenterà automaticamente con backoff crescente.
- **Richiesta di re-autenticazione** dopo un cambio password
  sull'account Ariston: è il comportamento atteso, segui la notifica per
  reinserire la nuova password senza perdere storico/automazioni.
- **Entità che spariscono per un dispositivo specifico ma non per gli
  altri**: quel singolo dispositivo sta fallendo l'aggiornamento (vedi log
  a livello `debug`), gli altri continuano a funzionare normalmente grazie
  alla gestione per-dispositivo del coordinator.

## Sviluppo

```bash
# Ambiente di sviluppo
python3 -m venv .venv
source .venv/bin/activate
pip install ruff mypy homeassistant

# Lint
ruff check custom_components/ariston_net

# Type checking
mypy custom_components/ariston_net

# Commit e rilascio
git add custom_components hacs.json README.md .github
git commit -m "feat: bump to vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main --tags
```

## Limiti noti / roadmap

- Non espone ancora entità `number` per impostazioni avanzate (temperatura
  minima/massima, orari modalità notte Lydos Hybrid): per ora si possono
  comunque leggere via `sensor`/attributi o intervenire dall'app ufficiale.
- Il nome del modello mostrato è generico (Ariston Net non espone il nome
  commerciale via API).
- Testato principalmente su Alteas One (Galevo) e Velis Evo/Lydos Hybrid;
  altri modelli Velis (Lux, Lux2, Nuos Split, Andris2) usano lo stesso
  codice generico e dovrebbero funzionare, ma non sono stati verificati su
  hardware reale — segnalazioni e log di debug sono benvenuti via Issue.

## Crediti

Basata sul lavoro di reverse engineering della libreria
[`ariston`](https://pypi.org/project/ariston/) di [@fustom](https://github.com/fustom).

## Licenza

[MIT](LICENSE)
