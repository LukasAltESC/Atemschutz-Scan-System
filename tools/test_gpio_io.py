#!/usr/bin/env python3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import ACTIVE_GPIO_CONFIG, GREEN_LED_PIN, MODE_BUTTON_PIN, PRINT_BUTTON_PIN, RED_LED_PIN, RESET_BUTTON_PIN

try:
    import RPi.GPIO as GPIO
except Exception as exc:
    raise SystemExit(f'RPi.GPIO nicht verfügbar: {exc}')

print(f'Projektpfad: {PROJECT_ROOT}')
print(f'Aktive GPIO-Konfiguration: {ACTIVE_GPIO_CONFIG}')

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(GREEN_LED_PIN, GPIO.OUT)
GPIO.setup(RED_LED_PIN, GPIO.OUT)
GPIO.setup(PRINT_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(RESET_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(MODE_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print('Teste grüne LED ...')
for _ in range(3):
    GPIO.output(GREEN_LED_PIN, GPIO.HIGH)
    time.sleep(0.2)
    GPIO.output(GREEN_LED_PIN, GPIO.LOW)
    time.sleep(0.2)

print('Teste rote LED ...')
for _ in range(3):
    GPIO.output(RED_LED_PIN, GPIO.HIGH)
    time.sleep(0.2)
    GPIO.output(RED_LED_PIN, GPIO.LOW)
    time.sleep(0.2)

print('Tastertest läuft. STRG+C zum Beenden.')
last = None
try:
    while True:
        state = (
            GPIO.input(PRINT_BUTTON_PIN),
            GPIO.input(RESET_BUTTON_PIN),
            GPIO.input(MODE_BUTTON_PIN),
        )
        if state != last:
            print(
                f'PRINT={"gedrückt" if state[0] == GPIO.LOW else "offen"} | '
                f'RESET={"gedrückt" if state[1] == GPIO.LOW else "offen"} | '
                f'MODE={"gedrückt" if state[2] == GPIO.LOW else "offen"}'
            )
            last = state
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    GPIO.output(GREEN_LED_PIN, GPIO.LOW)
    GPIO.output(RED_LED_PIN, GPIO.LOW)
    GPIO.cleanup()
