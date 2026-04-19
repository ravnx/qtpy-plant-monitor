# Soil Moisture Monitor

CircuitPython project for an Adafruit STEMMA soil sensor. Reads moisture and temperature, shows LED status, and publishes to Home Assistant via MQTT. I fit the QT Py in a clear film canister, helps show the LED blinks.


## Hardware

- CircuitPython board with WiFi (e.g. Feather ESP32-S2/S3)
- [Adafruit STEMMA Soil Sensor](https://www.adafruit.com/product/4026) (I2C, address `0x36`)

## LED Status

| Moisture  | Light                      |
|-----------|----------------------------|
| < 400     | Solid red                  |
| 400–499   | Blinking yellow            |
| ≥ 500     | Brief green blink every 30 min |

The sensor reads ~345 when held in air (not in soil).

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

### 3. Deploy code

```bash
cp code.py /Volumes/CIRCUITPY/code.py
```

### 4. Home Assistant

Install the **Mosquitto broker** add-on in Home Assistant, create an MQTT user under *Settings → People*, and use those credentials in `settings.toml`.

The device publishes via **MQTT Discovery** — it will auto-appear under *Settings → Devices & Services → MQTT* as **Plant Monitor** with two sensors:
- `sensor.soil_moisture`
- `sensor.soil_temperature`

## Tuning

All thresholds are at the top of `code.py`:

| Variable              | Default | Description                          |
|-----------------------|---------|--------------------------------------|
| `DRY_THRESHOLD`       | 400     | Below this = dry (red LED)           |
| `WET_THRESHOLD`       | 500     | Below this = marginal (yellow LED)   |
| `GREEN_BLINK_INTERVAL`| 1800 s  | How often to blink green when wet    |
| `PUBLISH_INTERVAL`    | 60 s    | How often to publish to MQTT         |

## Files

| File                   | Where                    | Notes                        |
|------------------------|--------------------------|------------------------------|
| `code.py`              | `/Volumes/CIRCUITPY/`    | Main program                 |
| `settings.toml.example`| repo root                | Safe template to commit      |
| `requirements.txt`     | repo root                | circup library list          |
