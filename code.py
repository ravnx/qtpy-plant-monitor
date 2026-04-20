# Soil Moisture Monitor
#
# Moisture  | Light
# ----------|---------------------------
# < 400     | Solid red
# 400 - 499 | Blinking yellow
# >= 500    | Green blink every 30 min
#
# Publishes moisture + temperature to Home Assistant via MQTT Discovery.
# Configure broker credentials and thresholds in settings.toml.

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
DRY_THRESHOLD = int(os.getenv("DRY_THRESHOLD", "400"))
WET_THRESHOLD = int(os.getenv("WET_THRESHOLD", "500"))
GREEN_BLINK_INTERVAL = int(os.getenv("GREEN_BLINK_INTERVAL", "1800"))  # seconds
YELLOW_BLINK_INTERVAL = int(os.getenv("YELLOW_BLINK_INTERVAL", "120"))  # seconds
PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL", "60"))           # seconds between MQTT publishes
SMOOTHING_SAMPLES = int(os.getenv("SMOOTHING_SAMPLES", "9"))          # rolling average window

DEVICE_ID = os.getenv("MQTT_DEVICE_ID", "plant_monitor")
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

STATE_TOPIC = f"{DEVICE_ID}/state"
AVAILABILITY_TOPIC = f"{DEVICE_ID}/availability"

# Lets print out config values on startup for easy debugging
print("DRY_THRESHOLD =", DRY_THRESHOLD)
print("WET_THRESHOLD =", WET_THRESHOLD)
print("PUBLISH_INTERVAL =", PUBLISH_INTERVAL)
print("GREEN_BLINK_INTERVAL =", GREEN_BLINK_INTERVAL)
print("YELLOW_BLINK_INTERVAL =", YELLOW_BLINK_INTERVAL)
print("SMOOTHING_SAMPLES =", SMOOTHING_SAMPLES)

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
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
    },
    {
        "unique_id": f"{DEVICE_ID}_temperature",
        "name": "Soil Temperature",
        "state_topic": STATE_TOPIC,
        "value_template": "{{ value_json.temperature }}",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
    },
]:
    sensor["device"] = device_info
    topic = f"homeassistant/sensor/{sensor['unique_id']}/config"
    mqtt_client.publish(topic, json.dumps(sensor), retain=True)

print("HA discovery published")
mqtt_client.publish(AVAILABILITY_TOPIC, "online", retain=True)

# --- Main loop ---
last_green_blink = 0
last_yellow_blink = 0
last_publish = 0
yellow_state = False
moisture_samples = []

while True:
    raw_moisture = ss.moisture_read()
    temp_c = ss.get_temp()

    # Median smoothing - resistant to spikes
    moisture_samples.append(raw_moisture)
    if len(moisture_samples) > SMOOTHING_SAMPLES:
        moisture_samples.pop(0)
    sorted_samples = sorted(moisture_samples)
    mid = len(sorted_samples) // 2
    if len(sorted_samples) % 2:
        moisture = sorted_samples[mid]
    else:
        moisture = (sorted_samples[mid - 1] + sorted_samples[mid]) // 2

    print("Moisture:", moisture, "(raw:", raw_moisture, ") Temp C:", round(temp_c, 2))

    # Publish to MQTT on interval
    now = time.monotonic()
    if now - last_publish >= PUBLISH_INTERVAL:
        payload = json.dumps({"moisture": moisture, "temperature": round(temp_c, 2)})
        try:
            mqtt_client.publish(STATE_TOPIC, payload, retain=True)
            print("Published:", payload)
        except Exception as e:
            print("MQTT error:", e)
            try:
                mqtt_client.reconnect()
                mqtt_client.publish(AVAILABILITY_TOPIC, "online", retain=True)
            except Exception:
                pass
        last_publish = now

    # LED status
    if moisture < DRY_THRESHOLD:
        # Solid red - dry / in air
        pixel[0] = (255, 0, 0)
        time.sleep(2)

    elif moisture < WET_THRESHOLD:
        # Blinking yellow - not quite wet enough, reminder on interval
        if now - last_yellow_blink >= YELLOW_BLINK_INTERVAL:
            yellow_state = not yellow_state
            pixel[0] = (255, 150, 0) if yellow_state else (0, 0, 0)
            time.sleep(0.5)
            pixel[0] = (0, 0, 0)
            last_yellow_blink = now
        else:
            pixel[0] = (0, 0, 0)
        time.sleep(2)

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