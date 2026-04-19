# Soil Moisture Monitor
#
# Moisture  | Light
# ----------|---------------------------
# < 400     | Solid red
# 400 - 499 | Blinking yellow
# >= 500    | Green blink every 30 min
#
# Publishes moisture + temperature to Home Assistant via MQTT Discovery.
# Configure broker credentials in settings.toml.

import time
import os
import json
import board
import busio
import wifi
import socketpool
import neopixel
from adafruit_seesaw.seesaw import Seesaw
import adafruit_minimqtt.adafruit_minimqtt as MQTT

# --- Config ---
DRY_THRESHOLD = 400
WET_THRESHOLD = 500
GREEN_BLINK_INTERVAL = 30 * 60  # seconds
PUBLISH_INTERVAL = 60           # seconds between MQTT publishes

DEVICE_ID = os.getenv("MQTT_DEVICE_ID", "plant_monitor")
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

STATE_TOPIC = f"{DEVICE_ID}/state"

# --- Hardware setup ---
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2, auto_write=True)
i2c = busio.I2C(board.SCL, board.SDA)
ss = Seesaw(i2c, addr=0x36)

# --- WiFi ---
print("Connecting to WiFi...")
pixel[0] = (0, 0, 50)  # dim blue while connecting
wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
print("WiFi connected:", wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)

# --- MQTT ---
mqtt_client = MQTT.MQTT(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    username=MQTT_USERNAME,
    password=MQTT_PASSWORD,
    socket_pool=pool,
)

mqtt_client.connect()
print("MQTT connected")

# --- Home Assistant MQTT Discovery ---
device_info = {
    "identifiers": [DEVICE_ID],
    "name": "Plant Monitor",
    "model": "Adafruit STEMMA Soil Sensor",
    "manufacturer": "Adafruit",
}

for sensor in [
    {
        "unique_id": f"{DEVICE_ID}_moisture",
        "name": "Soil Moisture",
        "state_topic": STATE_TOPIC,
        "value_template": "{{ value_json.moisture }}",
        "unit_of_measurement": "",
        "icon": "mdi:water",
    },
    {
        "unique_id": f"{DEVICE_ID}_temperature",
        "name": "Soil Temperature",
        "state_topic": STATE_TOPIC,
        "value_template": "{{ value_json.temperature }}",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
    },
]:
    sensor["device"] = device_info
    topic = f"homeassistant/sensor/{sensor['unique_id']}/config"
    mqtt_client.publish(topic, json.dumps(sensor), retain=True)

print("HA discovery published")

# --- Main loop ---
last_green_blink = 0
last_publish = 0
yellow_state = False

while True:
    moisture = ss.moisture_read()
    temp_c = ss.get_temp()
    print("Moisture:", moisture, "Temp C:", round(temp_c, 2))

    # Publish to MQTT on interval
    now = time.monotonic()
    if now - last_publish >= PUBLISH_INTERVAL:
        payload = json.dumps({"moisture": moisture, "temperature": round(temp_c, 2)})
        try:
            mqtt_client.publish(STATE_TOPIC, payload)
            print("Published:", payload)
        except Exception as e:
            print("MQTT error:", e)
            try:
                mqtt_client.reconnect()
            except Exception:
                pass
        last_publish = now

    # LED status
    if moisture < DRY_THRESHOLD:
        # Solid red - dry / in air
        pixel[0] = (255, 0, 0)
        time.sleep(2)

    elif moisture < WET_THRESHOLD:
        # Blinking yellow - not quite wet enough
        yellow_state = not yellow_state
        pixel[0] = (255, 150, 0) if yellow_state else (0, 0, 0)
        time.sleep(0.5)

    else:
        # Wet enough - brief green blink every 30 minutes
        if now - last_green_blink >= GREEN_BLINK_INTERVAL:
            pixel[0] = (0, 255, 0)
            time.sleep(0.5)
            pixel[0] = (0, 0, 0)
            last_green_blink = now
        else:
            pixel[0] = (0, 0, 0)
        time.sleep(2)