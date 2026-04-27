# Soil Moisture Monitor
#
# LED behavior is controlled by:
# - DRY_THRESHOLD
# - WET_THRESHOLD
# - HYSTERESIS
# - WARNING_MODE ("glow" or "blink")
#
# State machine:
#   dry     -> solid red
#   warning -> configurable amber glow/blink
#   wet     -> brief green blink every GREEN_BLINK_INTERVAL

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
PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL", "60"))           # seconds between MQTT publishes
SMOOTHING_SAMPLES = int(os.getenv("SMOOTHING_SAMPLES", "9"))          # rolling average window
HYSTERESIS = int(os.getenv("HYSTERESIS", "50"))                         # band around thresholds to prevent flickering
READ_DELAY = int(os.getenv("READ_DELAY", "2"))                            # seconds between sensor reads (firmware Jan 2020 recommends >= 1s)
_wc = os.getenv("WARNING_COLOR", "50,30,0").split(",")
WARNING_COLOR = (int(_wc[0].strip()), int(_wc[1].strip()), int(_wc[2].strip()))  # RGB for marginal state
WARNING_MODE = os.getenv("WARNING_MODE", "glow")           # "glow" or "blink"
WARNING_BLINK_INTERVAL = int(os.getenv("WARNING_BLINK_INTERVAL", "120"))  # seconds (blink mode only)

CALIBRATE = int(os.getenv("CALIBRATE", "0"))

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
print("SMOOTHING_SAMPLES =", SMOOTHING_SAMPLES)
print("WARNING_COLOR =", WARNING_COLOR)
print("WARNING_MODE =", WARNING_MODE)
if WARNING_MODE == "blink":
    print("WARNING_BLINK_INTERVAL =", WARNING_BLINK_INTERVAL)
print("HYSTERESIS =", HYSTERESIS)
print("READ_DELAY =", READ_DELAY)

# --- Hardware setup ---
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2, auto_write=True)
i2c = busio.I2C(board.SCL, board.SDA)
ss = Seesaw(i2c, addr=0x36)

# --- Calibration mode: print smoothed readings, skip WiFi/MQTT/state machine ---
if CALIBRATE:
    print("=== CALIBRATION MODE ===")
    print("Hold probe in air, then submerge gold pad up to the line.")
    print("Watch the smoothed reading and record air-min and water-max.")
    pixel[0] = (0, 0, 50)
    samples = []
    window = 9
    while True:
        try:
            raw = ss.moisture_read()
            temp_c = ss.get_temp()
        except Exception as e:
            print("Sensor error:", e)
            time.sleep(1)
            continue
        samples.append(raw)
        if len(samples) > window:
            samples.pop(0)
        s = sorted(samples)
        med = s[len(s) // 2] if len(s) % 2 else (s[len(s)//2 - 1] + s[len(s)//2]) // 2
        print("raw:", raw, " smoothed:", med, " temp C:", round(temp_c, 2))
        time.sleep(1)

import microcontroller
import supervisor

# --- WiFi (with retry) ---
def connect_wifi():
    print("Connecting to WiFi...")
    pixel[0] = (0, 0, 50)  # dim blue while connecting
    for attempt in range(5):
        try:
            wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
            print("WiFi connected:", wifi.radio.ipv4_address)
            return
        except Exception as e:
            print("WiFi connect failed (attempt", attempt + 1, "):", e)
            time.sleep(5)
    print("WiFi unreachable, hard reset")
    time.sleep(2)
    microcontroller.reset()

connect_wifi()
pool = socketpool.SocketPool(wifi.radio)

# --- MQTT ---
mqtt_client = MQTT.MQTT(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    username=MQTT_USERNAME,
    password=MQTT_PASSWORD,
    socket_pool=pool,
    keep_alive=120,
)

def mqtt_connect():
    for attempt in range(5):
        try:
            mqtt_client.connect()
            print("MQTT connected")
            return True
        except Exception as e:
            print("MQTT connect failed (attempt", attempt + 1, "):", e)
            time.sleep(5)
    return False

if not mqtt_connect():
    print("MQTT unreachable, hard reset")
    time.sleep(2)
    microcontroller.reset()

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
    try:
        mqtt_client.publish(topic, json.dumps(sensor), retain=True)
    except Exception as e:
        print("HA discovery publish failed:", e)

print("HA discovery published")
try:
    mqtt_client.publish(AVAILABILITY_TOPIC, "online", retain=True)
except Exception as e:
    print("Availability publish failed:", e)

# --- Main loop ---
last_green_blink = 0
last_warning_blink = 0
last_publish = 0
moisture_samples = []
state = None  # "dry" | "warning" | "wet"

last_loop = 0
sensor_error_count = 0

while True:
    try:
        raw_moisture = ss.moisture_read()
        temp_c = ss.get_temp()
        sensor_error_count = 0
    except Exception as e:
        sensor_error_count += 1
        print("Sensor read error (", sensor_error_count, "):", e)
        if sensor_error_count >= 10:
            print("Too many sensor errors, hard reset")
            time.sleep(2)
            microcontroller.reset()
        time.sleep(READ_DELAY)
        continue

    # Service MQTT (pings, server packets) so the broker doesn't drop us
    now = time.monotonic()
    if now - last_loop >= 15:
        try:
            mqtt_client.loop(timeout=1)
        except Exception as e:
            print("MQTT loop error:", e)
            try:
                mqtt_client.reconnect()
                mqtt_client.publish(AVAILABILITY_TOPIC, "online", retain=True)
            except Exception as e2:
                print("MQTT reconnect failed:", e2)
                if not wifi.radio.connected:
                    print("WiFi dropped, hard reset")
                    time.sleep(2)
                    microcontroller.reset()
        last_loop = now

    # Median smoothing - resistant to spikes
    moisture_samples.append(raw_moisture)
    if len(moisture_samples) > SMOOTHING_SAMPLES:
        moisture_samples.pop(0)

    if len(moisture_samples) < SMOOTHING_SAMPLES:
        print("Warming up samples:", len(moisture_samples), "/", SMOOTHING_SAMPLES)
        time.sleep(READ_DELAY)
        continue

    sorted_samples = sorted(moisture_samples)
    mid = len(sorted_samples) // 2
    if len(sorted_samples) % 2:
        moisture = sorted_samples[mid]
    else:
        moisture = (sorted_samples[mid - 1] + sorted_samples[mid]) // 2

    # State transition with hysteresis to prevent flickering at threshold boundaries
    prev_state = state
    if state is None:
        # Initial state - derive directly from thresholds with no hysteresis
        if moisture < DRY_THRESHOLD:
            state = "dry"
        elif moisture < WET_THRESHOLD:
            state = "warning"
        else:
            state = "wet"
    elif state == "dry":
        if moisture >= DRY_THRESHOLD + HYSTERESIS:
            state = "warning"
    elif state == "warning":
        if moisture < DRY_THRESHOLD - HYSTERESIS:
            state = "dry"
        elif moisture >= WET_THRESHOLD + HYSTERESIS:
            state = "wet"
    elif state == "wet":
        if moisture < WET_THRESHOLD - HYSTERESIS:
            state = "warning"

    if state != prev_state:
        print("State:", prev_state, "->", state)

    print("Moisture:", moisture, "(raw:", raw_moisture, ") Temp C:", round(temp_c, 2), "State:", state)

    # Publish to MQTT on interval
    now = time.monotonic()
    if now - last_publish >= PUBLISH_INTERVAL:
        payload = json.dumps({"moisture": moisture, "temperature": round(temp_c, 2), "state": state})
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
    if state == "dry":
        # Solid red - dry / in air
        pixel[0] = (255, 0, 0)
        time.sleep(READ_DELAY)

    elif state == "warning":
        if WARNING_MODE == "blink":
            if now - last_warning_blink >= WARNING_BLINK_INTERVAL:
                pixel[0] = WARNING_COLOR
                time.sleep(0.5)
                pixel[0] = (0, 0, 0)
                last_warning_blink = now
            else:
                pixel[0] = (0, 0, 0)
        else:  # glow
            pixel[0] = WARNING_COLOR
        time.sleep(READ_DELAY)

    else:  # wet
        # Wet enough - brief green blink every 30 minutes
        if now - last_green_blink >= GREEN_BLINK_INTERVAL:
            pixel[0] = (0, 255, 0)
            time.sleep(0.5)
            pixel[0] = (0, 0, 0)
            last_green_blink = now
        else:
            pixel[0] = (0, 0, 0)
        time.sleep(READ_DELAY)