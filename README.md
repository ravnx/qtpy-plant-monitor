# Soil Moisture Monitor

CircuitPython project for an Adafruit STEMMA soil sensor. Reads moisture and temperature, shows LED status, and publishes to Home Assistant via MQTT. I fit the QT Py in a clear film canister, helps show the LED blinks.


## Hardware

- CircuitPython board with WiFi (e.g. Feather ESP32-S2/S3)
- [Adafruit STEMMA Soil Sensor](https://www.adafruit.com/product/4026) (I2C, address `0x36`)

## LED Status

The LED is driven by a state machine with hysteresis — the state only changes when moisture crosses a threshold by more than `HYSTERESIS` points, preventing flickering at boundaries.

| State     | Condition                         | Light                                    |
|-----------|-----------------------------------|------------------------------------------|
| `dry`     | moisture < `DRY_THRESHOLD`        | Solid red                                |
| `warning` | between dry and wet thresholds    | Configurable amber glow or periodic blink |
| `wet`     | moisture ≥ `WET_THRESHOLD`        | Brief green blink every `GREEN_BLINK_INTERVAL` |

The sensor reads ~345 when held in air (not in soil).

On startup the board collects `SMOOTHING_SAMPLES` readings before entering normal operation ("warming up").

## Setup

### 1. Install libraries

Install [circup](https://github.com/adafruit/circup), then with the board connected:

```bash
circup install -r requirements.txt
```

### 2. Configure credentials

Copy `settings.toml.example` to your board as `settings.toml` and fill in your values:

```bash
cp settings.toml.example /Volumes/CIRCUITPY/settings.toml
```

Edit `/Volumes/CIRCUITPY/settings.toml`:
- `CIRCUITPY_WIFI_SSID` / `CIRCUITPY_WIFI_PASSWORD` — your WiFi network
- `MQTT_BROKER` — your Home Assistant IP address
- `MQTT_USERNAME` / `MQTT_PASSWORD` — MQTT broker credentials (set up in HA)
- `MQTT_DEVICE_ID` — unique ID for this device (default: `plant_monitor`)
- `DRY_THRESHOLD` / `WET_THRESHOLD` — moisture thresholds for LED state
- `HYSTERESIS` — dead-band around each threshold to prevent flickering (default: `50`)
- `PUBLISH_INTERVAL` — seconds between MQTT publishes (default: `60`)
- `GREEN_BLINK_INTERVAL` — seconds between green blinks when wet (default: `1800`)
- `WARNING_COLOR` — RGB color for the marginal state as `"R,G,B"` (default: `"50,30,0"` amber)
- `WARNING_MODE` — `glow` (steady) or `blink` (default: `glow`)
- `WARNING_BLINK_INTERVAL` — seconds between blinks when `WARNING_MODE=blink` (default: `120`)
- `SMOOTHING_SAMPLES` — median window size to reduce sensor noise (default: `9`)

### 3. Deploy code

```bash
cp code.py /Volumes/CIRCUITPY/code.py
```

### 4. Home Assistant

Install the **Mosquitto broker** add-on in Home Assistant, create an MQTT user under *Settings → People*, and use those credentials in `settings.toml`.

The device publishes via **MQTT Discovery** — it will auto-appear under *Settings → Devices & Services → MQTT* as **Plant Monitor** with two sensors:
- `sensor.soil_moisture`
- `sensor.soil_temperature`

Each MQTT payload also includes a `state` field (`dry`, `warning`, or `wet`) you can use in automations.

## Tuning

All settings live in `settings.toml` (copy from `settings.toml.example`):

| Variable                | Default   | Description                                             |
|-------------------------|-----------|---------------------------------------------------------|
| `DRY_THRESHOLD`         | 400       | Below this = dry (red LED)                              |
| `WET_THRESHOLD`         | 500       | Above this = wet (green LED)                            |
| `HYSTERESIS`            | 50        | Dead-band around thresholds to prevent state flickering |
| `GREEN_BLINK_INTERVAL`  | 1800 s    | How often to blink green when wet                       |
| `WARNING_COLOR`         | `50,30,0` | RGB color for marginal state (`"R,G,B"`)                |
| `WARNING_MODE`          | `glow`    | `glow` (steady) or `blink`                              |
| `WARNING_BLINK_INTERVAL`| 120 s     | Seconds between blinks (only when `WARNING_MODE=blink`) |
| `PUBLISH_INTERVAL`      | 60 s      | How often to publish to MQTT                            |
| `SMOOTHING_SAMPLES`     | 9         | Median window size to filter sensor noise; also warmup sample count |

Capacitive soil sensors are noisy. Increasing `SMOOTHING_SAMPLES` (e.g. to `15` or `21`) gives a cleaner MQTT graph without affecting responsiveness much, since soil moisture changes slowly.

## Files

| File                    | Where                 | Notes                        |
|-------------------------|-----------------------|------------------------------|
| `code.py`               | `/Volumes/CIRCUITPY/` | Main program                 |
| `settings.toml.example` | repo root             | Configuration Template       |
| `requirements.txt`      | repo root             | circup library list          |
