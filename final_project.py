import RPi.GPIO as GPIO
import time
import Adafruit_DHT
import requests
import json
import threading
from RPLCD.i2c import CharLCD

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Pin Configuration
PIR_PIN = 18
LED_GREEN_PIN = 23
LED_RED_PIN = 24
LED_BLUE_PIN = 25
BUTTON_UP_PIN = 17
BUTTON_DOWN_PIN = 27
BUTTON_SENSOR_PIN = 22

# LCD Setup
lcd = CharLCD('PCF8574', address=0x3f, port=1, backlight_enabled=True)

# BMS Variables
temperature = 0.0
humidity = 0.0
desired_temperature = 29
weather_index = 0.0
hvac_status = "OFF"
old_status = "OFF"
door_status = "CLOSED"
window_status = "CLOSED"
energy_consumption = 0.0
energy_cost = 0.0
is_fire_alarm_active = False
max_temp_for_fire = 20

# GPIO Setup
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(LED_GREEN_PIN, GPIO.OUT)
GPIO.setup(LED_RED_PIN, GPIO.OUT)
GPIO.setup(LED_BLUE_PIN, GPIO.OUT)
GPIO.setup(BUTTON_UP_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_DOWN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def toggle_led(pin, state):
    GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)

def update_lcd(lines):
    lcd.clear()
    for i, line in enumerate(lines):
        lcd.cursor_pos = (i, 0)
        lcd.write_string(line)

def read_temperature_humidity():
    global temperature, humidity
    humidity, temperature = Adafruit_DHT.read_retry(Adafruit_DHT.DHT11, 4)
    if humidity is not None and temperature is not None:
        temperature, humidity = round(temperature, 1), round(humidity, 1)

def get_cimis_humidity():
    params = {
        'appKey': '17ab4aac-00b7-4ffc-a2d8-06086ca5780e',
        'targets': '71',
        'startDate': '2023-05-01',
        'endDate': '2023-05-29',
        'dataItems': 'humidity'
    }
    response = requests.get('http://et.water.ca.gov/api/data', params=params)
    if response.status_code == 200:
        data = response.json()
        return round(data['Data'][0]['humidity'], 1) if 'Data' in data and data['Data'] else None
    return None

def calculate_weather_index():
    global weather_index
    weather_index = round(temperature + 0.05 * humidity, 1)

def update_hvac_status():
    global hvac_status, old_status
    old_status, hvac_status = hvac_status, "OFF"
    if weather_index > desired_temperature + 3:
        hvac_status = "AC"
        toggle_led(LED_BLUE_PIN, True)
        toggle_led(LED_RED_PIN, False)
    elif weather_index < desired_temperature - 3:
        hvac_status = "HEAT"
        toggle_led(LED_BLUE_PIN, False)
        toggle_led(LED_RED_PIN, True)
    else:
        toggle_led(LED_BLUE_PIN, False)
        toggle_led(LED_RED_PIN, False)

def update_energy_consumption():
    global energy_consumption, energy_cost
    consumption_rate = 0.001 * (18000 if hvac_status == "AC" else 36000 if hvac_status == "HEAT" else 0)
    energy_consumption += consumption_rate
    energy_cost = round(energy_consumption * 0.5, 2)

def handle_fire_alarm():
    global is_fire_alarm_active, door_status, window_status, max_temp_for_fire, hvac_status
    if is_fire_alarm_active:
        max_temp_for_fire = 35
        update_lcd(["FIRE ALARM!", "EVACUATE!"])
        time.sleep(3)
        door_status, window_status, hvac_status = "OPEN", "OPEN", "OFF"
        for _ in range(10):
            toggle_led(LED_GREEN_PIN, True)
            toggle_led(LED_RED_PIN, True)
            toggle_led(LED_BLUE_PIN, True)
            time.sleep(1)
            toggle_led(LED_GREEN_PIN, False)
            toggle_led(LED_RED_PIN, False)
            toggle_led(LED_BLUE_PIN, False)
            time.sleep(1)
        is_fire_alarm_active = False
    toggle_led(LED_GREEN_PIN, False)

def bms_control():
    global desired_temperature, is_fire_alarm_active
    while True:
        motion_detected = GPIO.input(PIR_PIN) == GPIO.HIGH
        toggle_led(LED_GREEN_PIN, motion_detected)
        update_lcd(["LED: ON" if motion_detected else "LED: OFF"])
        time.sleep(10 if motion_detected else 5)

        read_temperature_humidity()
        cimis_humidity = get_cimis_humidity()
        if cimis_humidity:
            humidity = cimis_humidity
        calculate_weather_index()
        update_hvac_status()
        update_energy_consumption()
        update_lcd([f"T:{temperature}C H:{humidity}%", f"W:{weather_index}C D:{desired_temperature}C"])

        if weather_index > max_temp_for_fire:
            is_fire_alarm_active = True
            handle_fire_alarm()

GPIO.add_event_detect(BUTTON_UP_PIN, GPIO.FALLING, callback=lambda _: desired_temperature + 1, bouncetime=200)
GPIO.add_event_detect(BUTTON_DOWN_PIN, GPIO.FALLING, callback=lambda _: desired_temperature - 1, bouncetime=200)
GPIO.add_event_detect(BUTTON_SENSOR_PIN, GPIO.BOTH, callback=lambda _: None, bouncetime=200)

bms_thread = threading.Thread(target=bms_control, daemon=True)
bms_thread.start()

try:
    while True:
        pass
except KeyboardInterrupt:
    GPIO.cleanup()
