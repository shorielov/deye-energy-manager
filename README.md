# Smart Energy Manager

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![HA min version](https://img.shields.io/badge/HA-%3E%3D2024.1.0-blue)

A Home Assistant custom integration for Deye/Sunsynk hybrid inverters that builds a daily **Time-of-Use charge plan** from PV forecast, battery state and tariff data — and optionally writes it directly to the inverter.

---

## Features

### ✅ Implemented (v0.1.0)

#### Decision engine
- Three strategies selectable via the **Mode** switch:
  - **Balanced** — cost-aware; charges from grid when deficit and cheap window justify it
  - **Eco** — never charges from grid; increases target SoC when weather risk is high
  - **Backup** — keeps battery as full as possible; 100 % SoC during cheap night window (dual tariff)
- Modes **Winter** and **Autonomous** fall back to Balanced with an informational note
- Pure-function engine (no I/O) — easy to unit-test and extend

#### Tariff support
- **Flat** — single rate, PV-only optimisation
- **Dual (day/night)** — overnight cheap window with wrap-around support (e.g. 23:00–07:00)

#### Daily 6-slot TOU plan
- Exactly 6 `PlanSlot` entries sorted by `start_time`, always padded or collapsed to 6
- Each slot carries: `start_time`, `target_soc`, `charge_from_grid`, `max_power_w`, `reason` code
- Plan metadata: `strategy`, `generated_at`, `estimated_savings_uah`, `expected_balance_kwh`, `notes`

#### Consumption forecast — priority chain
1. **Statistics** (Home Assistant Recorder) — survives restarts, highest confidence
2. **Power-history** — 24-hour rolling window of instantaneous power readings
3. **Live-counter extrapolation** — projects today's energy counter pace to full-day estimate
4. Falls back gracefully to `None` when no data is available

#### Plan entities (read-only, published to HA)
| Entity | Type | Description |
|---|---|---|
| `sensor.smart_energy_manager_plan` | sensor | Active strategy name; full slot list in attributes |
| `sensor.smart_energy_manager_plan_slot_N_start` | sensor | Slot N start time (HH:MM), N = 1–6 |
| `sensor.smart_energy_manager_plan_slot_N_target_soc` | sensor | Slot N target SoC (%) |
| `binary_sensor.smart_energy_manager_plan_slot_N_charge` | binary sensor | Slot N charge-from-grid flag |

#### Telemetry sensors
Battery SoC, battery power, PV power, PV generation today, grid import/export, home consumption, today's load and smart-load counters.

#### Controls
| Entity | Type | Description |
|---|---|---|
| `switch.smart_energy_manager_eco_mode` | switch | Enable Eco strategy |
| `switch.smart_energy_manager_winter_mode` | switch | Enable Winter strategy (falls back to Balanced) |
| `switch.smart_energy_manager_auto_apply_recommendations` | switch | Auto-write plan to inverter |
| `number.smart_energy_manager_min_soc_override` | number | Override minimum SoC (%) |
| `number.smart_energy_manager_target_soc_override` | number | Override target SoC (%) |

#### Inverter adapters
- **None** (default) — plan is published as HA entities only; writes are logged
- **Sunsynk / Deye** — writes the 6-slot plan to [kellerza/sunsynk](https://github.com/kellerza/sunsynk) TOU entities:
  - `time.{prefix}prog{N}_time`
  - `number.{prefix}prog{N}_capacity`
  - `switch.{prefix}prog{N}_charge`
  - Duplicate-write protection via plan hash
  - Configurable entity prefix for multi-inverter setups
- **Solarman / Deye** — writes the 6-slot plan to [davidrapan/ha-solarman](https://github.com/davidrapan/ha-solarman) TOU entities:
  - `time.{slug}_program_{N}_time`
  - `number.{slug}_program_{N}_soc`
  - `select.{slug}_program_{N}_charging` (`"Grid"` / `"Disabled"`)
  - Configurable device name (default: `inverter`)

#### Config flow (UI)
Full setup and options flow with HA-native selectors:
- Entity selectors for all telemetry inputs
- Number selectors for rates and capacity
- Time selectors for night window
- Select selector for tariff type, energy mode, inverter adapter
- Boolean selector for auto-apply toggle

#### Services
| Service | Description |
|---|---|
| `smart_energy_manager.recompute` | Force an immediate plan recompute |
| `smart_energy_manager.clear_history` | Clear power-history and forecast cache |
| `smart_energy_manager.set_mode` | Change energy mode via service call |

---

### 🚧 Coming Soon

#### Strategies
- **Winter** — cold-weather optimisation with extended grid-charge window
- **Autonomous** — fully self-sufficient mode; no grid import target

#### Tariffs
- **ToU (multi-zone)** — more than 2 price bands (e.g. peak / shoulder / off-peak)
- **Dynamic pricing** — real-time spot price integration (ENTSO-E, Tibber, etc.)

#### Forecast integrations
- Native [Solcast](https://solcast.com) polling (currently expects an external HA sensor)
- [Open-Meteo](https://open-meteo.com) solar irradiance as a lightweight alternative

#### Inverter adapters
- **SolarEdge** — StorEdge storage API
- **Fronius** — Modbus / SolarAPI v1
- **Generic Modbus** — register-map-based adapter for any inverter

#### Automation & UX
- Lovelace dashboard card (energy flow + today's plan timeline)
- Push notifications on plan change or bad-weather alert
- Plan history stored in HA Statistics for retrospective analysis
- Energy cost vs. baseline savings graph

#### Multi-inverter
- Support for more than one inverter per HA instance under a single integration entry

---

## Installation

### HACS (recommended)
1. Add this repository as a **Custom Repository** in HACS → Integrations.
2. Install **Smart Energy Manager** and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for *Smart Energy Manager*.

### Manual
Copy `custom_components/smart_energy_manager/` into your `config/custom_components/` directory and restart Home Assistant.

---

## Configuration

All configuration is done through the UI. You will need:

| Input | Example entity |
|---|---|
| Battery SoC | `sensor.deye_battery_soc` |
| Battery power | `sensor.deye_battery_power` |
| Battery capacity (kWh) | `10.24` |
| PV power | `sensor.deye_pv_power` |
| PV generation today | `sensor.deye_day_pv_energy` |
| Grid import / export | `sensor.deye_grid_import_power` |
| Home consumption (W or kW) | `sensor.deye_load_power` |
| Today load counter | `sensor.deye_day_load_energy` |
| Smart load counter | `sensor.deye_day_battery_charge` |
| PV forecast today / tomorrow | `sensor.solcast_pv_forecast_today` |

### Sunsynk adapter entity prefix

If you use a prefix in your kellerza/sunsynk configuration (e.g. `deye_`), enter it in the **Sunsynk entity prefix** field so the integration resolves the correct entities:
```
time.deye_prog1_time
number.deye_prog1_capacity
switch.deye_prog1_charge
```

### Solarman adapter device name

The **Solarman device name** field must match the device name (slug) used by the davidrapan/ha-solarman integration entry — default is `inverter`.  
The integration writes to these entities per slot N = 1…6:
```
time.inverter_program_1_time
number.inverter_program_1_soc
select.inverter_program_1_charging   ← option: "Grid" or "Disabled"
```
If your Solarman config entry uses a different device name (e.g. `deye_sg04`), set that name in the **Solarman device name** field.

> **Note:** Enable the Time-of-Use schedule in the Solarman UI at least once before using auto-apply. The adapter writes slot values but does not enable the TOU master switch.

---

## Dashboard (Lovelace)

A ready-to-use dashboard built entirely from entities published by this integration.  
No extra helpers, template sensors, or automations required.

### Prerequisites

Install via **HACS → Frontend**:

| Card | Repository | Notes |
|---|---|---|
| **Mushroom** | `piitaya/lovelace-mushroom` | required |
| **vertical-stack-in-card** | `ofekashery/vertical-stack-in-card` | required |
| **Power Flow Card Plus** | `flixlix/power-flow-card-plus` | required |
| **ApexCharts Card** | `RomRider/apexcharts-card` | required (History view) |

After installing all cards, restart Home Assistant and hard-refresh your browser (`Ctrl+F5`).

### Add the dashboard

1. **Settings → Dashboards → Add dashboard → New dashboard from scratch**, name it *Smart Energy*.
2. Open the dashboard → **⋮ → Edit dashboard → ⋮ → Raw configuration editor**.
3. Paste the YAML below, replace every `sensor.deye_*` placeholder with your actual entity IDs (the same ones you entered during integration setup), then **Save**.

---

### Dashboard YAML

```yaml
title: Smart Energy
views:

  # ════════════════════════════════════════════════════════════
  # VIEW 1 — Overview
  # ════════════════════════════════════════════════════════════
  - title: Overview
    path: overview
    icon: mdi:solar-power
    cards:

      # ── Power flow animation ──────────────────────────────
      - type: custom:power-flow-card-plus
        title: Live power flow
        entities:
          battery:
            entity: sensor.deye_battery_soc        # ← your battery SoC sensor
            state_of_charge: sensor.deye_battery_soc
            power_entity: sensor.deye_battery_power  # ← your battery power sensor (W, + = charge, - = discharge)
          solar:
            entity: sensor.deye_pv_power            # ← your PV power sensor (W)
          grid:
            entity: sensor.deye_grid_import_power   # ← your grid import power sensor (W)
          home:
            entity: sensor.deye_load_power          # ← your home consumption sensor (W)
        display_zero_lines: true
        use_new_flow_rate_model: true
        watt_threshold: 1000

      # ── Status chips + Plan card (combined via vertical-stack) ───
      - type: custom:vertical-stack-in-card
        title: Today's plan
        cards:

          # chips row
          - type: custom:mushroom-chips-card
            alignment: center
            chips:
              - type: entity
                entity: sensor.smart_energy_manager_plan
                icon: mdi:lightning-bolt-circle
                content_info: state
                tap_action:
                  action: more-info
              - type: entity
                entity: sensor.smart_energy_manager_energy_score
                icon: mdi:leaf
              - type: entity
                entity: sensor.smart_energy_manager_grid_dependency
                icon: mdi:transmission-tower
              - type: entity
                entity: binary_sensor.smart_energy_manager_bad_weather
                icon: mdi:weather-cloudy-alert
              - type: entity
                entity: binary_sensor.smart_energy_manager_energy_deficit
                icon: mdi:battery-alert

          # plan summary tile
          - type: custom:mushroom-template-card
            entity: sensor.smart_energy_manager_energy_plan
            primary: "{{ states('sensor.smart_energy_manager_energy_plan') }} strategy"
            secondary: >-
              Est. savings: {{ state_attr('sensor.smart_energy_manager_energy_plan',
              'estimated_savings_uah') | round(2) }} UAH · Balance: {{
              state_attr('sensor.smart_energy_manager_energy_plan', 'expected_balance_kwh')
              | round(2) }} kWh
            icon: mdi:chart-timeline-variant
            tap_action:
            action: more-info
            color: blue
            features_position: bottom
            area: summer_kitchen

          # 6 TOU slots
          - type: grid
            columns: 3
            square: false
            cards:
              - type: custom:mushroom-template-card
                primary: "Slot 1 · {{ states('sensor.smart_energy_manager_plan_slot_1_start') }}"
                secondary: >-
                  {{ states('sensor.smart_energy_manager_plan_slot_1_target_soc') }}%
                  · {{ 'Grid charge' if is_state('binary_sensor.smart_energy_manager_plan_slot_1_charge', 'on') else 'PV / idle' }}
                icon: >-
                  {{ 'mdi:transmission-tower-import' if is_state('binary_sensor.smart_energy_manager_plan_slot_1_charge', 'on') else 'mdi:solar-power' }}
                icon_color: >-
                  {{ 'red' if is_state('binary_sensor.smart_energy_manager_plan_slot_1_charge', 'on') else 'green' }}
              - type: custom:mushroom-template-card
                primary: "Slot 2 · {{ states('sensor.smart_energy_manager_plan_slot_2_start') }}"
                secondary: >-
                  {{ states('sensor.smart_energy_manager_plan_slot_2_target_soc') }}%
                  · {{ 'Grid charge' if is_state('binary_sensor.smart_energy_manager_plan_slot_2_charge', 'on') else 'PV / idle' }}
                icon: >-
                  {{ 'mdi:transmission-tower-import' if is_state('binary_sensor.smart_energy_manager_plan_slot_2_charge', 'on') else 'mdi:solar-power' }}
                icon_color: >-
                  {{ 'red' if is_state('binary_sensor.smart_energy_manager_plan_slot_2_charge', 'on') else 'green' }}
              - type: custom:mushroom-template-card
                primary: "Slot 3 · {{ states('sensor.smart_energy_manager_plan_slot_3_start') }}"
                secondary: >-
                  {{ states('sensor.smart_energy_manager_plan_slot_3_target_soc') }}%
                  · {{ 'Grid charge' if is_state('binary_sensor.smart_energy_manager_plan_slot_3_charge', 'on') else 'PV / idle' }}
                icon: >-
                  {{ 'mdi:transmission-tower-import' if is_state('binary_sensor.smart_energy_manager_plan_slot_3_charge', 'on') else 'mdi:solar-power' }}
                icon_color: >-
                  {{ 'red' if is_state('binary_sensor.smart_energy_manager_plan_slot_3_charge', 'on') else 'green' }}
              - type: custom:mushroom-template-card
                primary: "Slot 4 · {{ states('sensor.smart_energy_manager_plan_slot_4_start') }}"
                secondary: >-
                  {{ states('sensor.smart_energy_manager_plan_slot_4_target_soc') }}%
                  · {{ 'Grid charge' if is_state('binary_sensor.smart_energy_manager_plan_slot_4_charge', 'on') else 'PV / idle' }}
                icon: >-
                  {{ 'mdi:transmission-tower-import' if is_state('binary_sensor.smart_energy_manager_plan_slot_4_charge', 'on') else 'mdi:solar-power' }}
                icon_color: >-
                  {{ 'red' if is_state('binary_sensor.smart_energy_manager_plan_slot_4_charge', 'on') else 'green' }}
              - type: custom:mushroom-template-card
                primary: "Slot 5 · {{ states('sensor.smart_energy_manager_plan_slot_5_start') }}"
                secondary: >-
                  {{ states('sensor.smart_energy_manager_plan_slot_5_target_soc') }}%
                  · {{ 'Grid charge' if is_state('binary_sensor.smart_energy_manager_plan_slot_5_charge', 'on') else 'PV / idle' }}
                icon: >-
                  {{ 'mdi:transmission-tower-import' if is_state('binary_sensor.smart_energy_manager_plan_slot_5_charge', 'on') else 'mdi:solar-power' }}
                icon_color: >-
                  {{ 'red' if is_state('binary_sensor.smart_energy_manager_plan_slot_5_charge', 'on') else 'green' }}
              - type: custom:mushroom-template-card
                primary: "Slot 6 · {{ states('sensor.smart_energy_manager_plan_slot_6_start') }}"
                secondary: >-
                  {{ states('sensor.smart_energy_manager_plan_slot_6_target_soc') }}%
                  · {{ 'Grid charge' if is_state('binary_sensor.smart_energy_manager_plan_slot_6_charge', 'on') else 'PV / idle' }}
                icon: >-
                  {{ 'mdi:transmission-tower-import' if is_state('binary_sensor.smart_energy_manager_plan_slot_6_charge', 'on') else 'mdi:solar-power' }}
                icon_color: >-
                  {{ 'red' if is_state('binary_sensor.smart_energy_manager_plan_slot_6_charge', 'on') else 'green' }}

      # ── Controls ─────────────────────────────────────────
      - type: grid
        columns: 3
        square: false
        cards:
          - type: custom:mushroom-entity-card
            entity: switch.smart_energy_manager_eco_mode
            name: Eco
            icon: mdi:leaf
            tap_action:
              action: toggle
          - type: custom:mushroom-entity-card
            entity: switch.smart_energy_manager_winter_mode
            name: Winter
            icon: mdi:snowflake
            tap_action:
              action: toggle
          - type: custom:mushroom-entity-card
            entity: switch.smart_energy_manager_auto_apply_recommendations
            name: Auto-apply
            icon: mdi:upload-network
            tap_action:
              action: toggle
          - type: custom:mushroom-number-card
            entity: number.smart_energy_manager_min_soc_override
            name: Min SoC
            icon: mdi:battery-low
          - type: custom:mushroom-number-card
            entity: number.smart_energy_manager_target_soc_override
            name: Target SoC
            icon: mdi:target

  # ════════════════════════════════════════════════════════════
  # VIEW 2 — History (7-day trends)
  # ════════════════════════════════════════════════════════════
  - title: History
    path: history
    icon: mdi:chart-line
    cards:

      - type: custom:apexcharts-card
        header:
          show: true
          title: Forecast Balance — last 7 days (kWh)
        graph_span: 7d
        series:
          - entity: sensor.smart_energy_manager_forecast_balance
            name: Forecast balance
            type: area
            color: "#00b0ff"
            fill_raw: "null"
            stroke_width: 2
            show:
              legend_value: true

      - type: custom:apexcharts-card
        header:
          show: true
          title: Energy Score & Grid Dependency — last 7 days (%)
        graph_span: 7d
        apex_config:
          yaxis:
            min: 0
            max: 100
        series:
          - entity: sensor.smart_energy_manager_energy_score
            name: Energy Score
            type: line
            color: "#43a047"
            stroke_width: 2
            show:
              legend_value: true
          - entity: sensor.smart_energy_manager_grid_dependency
            name: Grid Dependency
            type: line
            color: "#e53935"
            stroke_width: 2
            show:
              legend_value: true

      - type: custom:apexcharts-card
        header:
          show: true
          title: Bad Weather Risk — last 7 days (%)
        graph_span: 7d
        apex_config:
          yaxis:
            min: 0
            max: 100
        series:
          - entity: sensor.smart_energy_manager_bad_weather_risk
            name: Bad weather risk
            type: area
            color: "#ff8f00"
            stroke_width: 2
            show:
              legend_value: true
```

### Notes

- Replace all `sensor.deye_*` entities with the entity IDs you entered during integration setup.
- **Power Flow Card Plus**: `battery_power` sign convention — positive = charging, negative = discharging. Check your inverter sensor and add `invert_state: true` under `battery:` if the signs are reversed.
- **Slot tiles**: colour coding — red = grid-charge slot, green = PV / idle slot. Tiles show `unknown` until the first plan is generated after HA restart.
- **History view**: sensors must have `state_class: measurement` recorded by the HA Recorder. `forecast_balance`, `energy_score`, `grid_dependency`, and `bad_weather_risk` all qualify. History depth depends on your Recorder `purge_keep_days` setting (default 10 days).
- The integration recomputes the plan periodically; all tiles and charts refresh automatically.

---

## Architecture

```
coordinator.py          ← DataUpdateCoordinator, builds DecisionContext
decision/
  context.py            ← pure input container (no hass, no I/O)
  signals.py            ← derived metrics (deficit, headroom, weather risk …)
  plan.py               ← plan manipulation helpers (snap, collapse, savings)
  strategies/
    balanced.py         ← cost-aware default
    eco.py              ← PV-only, weather-aware SoC boost
    backup.py           ← maximum battery fill
adapters/
  noop.py               ← publish-only (log)
  sunsynk.py            ← kellerza/sunsynk TOU entities
  solarman.py           ← davidrapan/ha-solarman TOU entities
sensor.py               ← plan + telemetry read-only entities
binary_sensor.py        ← plan slot charge flags
switch.py               ← mode + auto-apply controls
number.py               ← SoC overrides
config_flow.py          ← setup + options UI
```

---

## Requirements

- Home Assistant ≥ 2024.1.0
- Python ≥ 3.11
- For Sunsynk adapter: [kellerza/sunsynk](https://github.com/kellerza/sunsynk) integration installed and configured
- For Solarman adapter: [davidrapan/ha-solarman](https://github.com/davidrapan/ha-solarman) integration installed and configured with a Deye inverter

---

## License

MIT
