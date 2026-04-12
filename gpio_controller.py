"""GPIO-Steuerung fuer Taster und Status-LEDs.

Das Modul nutzt bewusst Polling statt komplexer Interrupt-Logik, damit das
Verhalten auf Raspberry-Pi-Systemen nachvollziehbar und robust bleibt.
"""

import threading
import time
from typing import Callable, Dict

from config import (
    ACTIVE_GPIO_CONFIG,
    DUPLICATE_ERROR_BLINKS,
    ERROR_BLINK_OFF_SECONDS,
    ERROR_BLINK_ON_SECONDS,
    GENERIC_ERROR_BLINKS,
    GPIO_POLL_INTERVAL_SECONDS,
    GREEN_LED_PIN,
    LISTING_MODE_BLINK_INTERVAL_SECONDS,
    MODE_BUTTON_PIN,
    PRINT_BUTTON_PIN,
    RED_LED_PIN,
    RESET_BUTTON_PIN,
    RESET_LONG_PRESS_SECONDS,
    SUCCESS_BLINK_OFF_SECONDS,
    SUCCESS_BLINK_ON_SECONDS,
    SYSTEM_ERROR_BLOCKING_BLINK_OFF_SECONDS,
    SYSTEM_ERROR_BLOCKING_BLINK_ON_SECONDS,
    SYSTEM_ERROR_TIME_WARNING_BLINK_OFF_SECONDS,
    SYSTEM_ERROR_TIME_WARNING_BLINK_ON_SECONDS,
)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO = None
    GPIO_AVAILABLE = False


class GPIOController:
    """GPIO-Steuerung mit robustem Polling für LEDs und drei Taster."""

    def __init__(
        self,
        on_print_pressed: Callable = None,
        on_reset_pressed: Callable = None,
        on_reset_long_pressed: Callable = None,
        on_mode_pressed: Callable = None,
    ):
        self.on_print_pressed = on_print_pressed
        self.on_reset_pressed = on_reset_pressed
        self.on_reset_long_pressed = on_reset_long_pressed
        self.on_mode_pressed = on_mode_pressed
        self.initialized = False
        self.stop_event = threading.Event()
        self.blink_lock = threading.Lock()
        self.ready_state = False
        self.listing_mode_active = False
        self.system_fault_level = 'none'
        self._green_override_active = False
        self._red_override_active = False
        self._button_state: Dict[int, int] = {}
        self._button_pressed_since: Dict[int, float] = {}
        self._last_dummy_green = None
        self._last_dummy_red = None
        self._last_callback_error = ''
        self.poll_thread = None
        self.green_thread = None
        self.red_thread = None

    def initialize(self) -> None:
        """Initialisiert GPIOs und startet Polling- sowie LED-Threads."""
        if not GPIO_AVAILABLE:
            print('[GPIO] Dummy-Modus aktiv (RPi.GPIO nicht verfügbar).')
            return

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(GREEN_LED_PIN, GPIO.OUT)
        GPIO.setup(RED_LED_PIN, GPIO.OUT)
        GPIO.setup(PRINT_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(RESET_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(MODE_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.output(GREEN_LED_PIN, GPIO.LOW)
        GPIO.output(RED_LED_PIN, GPIO.LOW)

        self._button_state = {
            PRINT_BUTTON_PIN: GPIO.input(PRINT_BUTTON_PIN),
            RESET_BUTTON_PIN: GPIO.input(RESET_BUTTON_PIN),
            MODE_BUTTON_PIN: GPIO.input(MODE_BUTTON_PIN),
        }
        self.stop_event.clear()
        self.initialized = True
        self.poll_thread = threading.Thread(target=self._poll_buttons_worker, daemon=True)
        self.green_thread = threading.Thread(target=self._green_indicator_worker, daemon=True)
        self.red_thread = threading.Thread(target=self._red_indicator_worker, daemon=True)
        self.poll_thread.start()
        self.green_thread.start()
        self.red_thread.start()
        print(f'[GPIO] Initialisiert (Polling-Modus): {ACTIVE_GPIO_CONFIG}')

    def cleanup(self) -> None:
        self.stop_event.set()
        if GPIO_AVAILABLE and self.initialized:
            GPIO.cleanup()

    def _poll_buttons_worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._poll_single_button(PRINT_BUTTON_PIN)
                self._poll_single_button(RESET_BUTTON_PIN)
                self._poll_single_button(MODE_BUTTON_PIN)
            except Exception as exc:
                self._last_callback_error = str(exc)
                print(f'[GPIO] Polling-Fehler: {exc}')
            time.sleep(GPIO_POLL_INTERVAL_SECONDS)

    def _poll_single_button(self, pin: int) -> None:
        if not GPIO_AVAILABLE:
            return
        current_state = GPIO.input(pin)
        previous_state = self._button_state.get(pin, current_state)
        if current_state == previous_state:
            return
        self._button_state[pin] = current_state
        now = time.monotonic()

        if current_state == GPIO.LOW:
            # Gedrueckt merken; ausgewertet wird erst beim Loslassen, damit sich
            # Kurz- und Langdruck sauber unterscheiden lassen.
            self._button_pressed_since[pin] = now
            return

        pressed_since = self._button_pressed_since.pop(pin, now)
        duration = now - pressed_since

        if pin == PRINT_BUTTON_PIN:
            if duration >= 0.03 and self.on_print_pressed:
                self._safe_invoke_callback(self.on_print_pressed, source='print_button')
            return

        if pin == RESET_BUTTON_PIN:
            if duration >= RESET_LONG_PRESS_SECONDS:
                if self.on_reset_long_pressed:
                    self._safe_invoke_callback(self.on_reset_long_pressed, source='reset_button_long')
            elif duration >= 0.03:
                if self.on_reset_pressed:
                    self._safe_invoke_callback(self.on_reset_pressed, source='reset_button')
            return

        if pin == MODE_BUTTON_PIN and duration >= 0.03:
            if self.on_mode_pressed:
                self._safe_invoke_callback(self.on_mode_pressed, source='mode_button')

    def _safe_invoke_callback(self, callback: Callable, **kwargs) -> None:
        try:
            callback(**kwargs)
            self._last_callback_error = ''
        except Exception as exc:
            self._last_callback_error = str(exc)
            print(f'[GPIO] Callback-Fehler: {exc}')

    def set_ready(self, ready: bool) -> None:
        self.ready_state = bool(ready)
        if not GPIO_AVAILABLE:
            self._dummy_green('AN' if self.ready_state else 'AUS')

    def set_listing_mode(self, active: bool) -> None:
        self.listing_mode_active = bool(active)
        if not GPIO_AVAILABLE:
            self._dummy_green('SCHNELL BLINKEN' if active else ('AN' if self.ready_state else 'AUS'))

    def set_system_fault(self, active: bool) -> None:
        self.set_system_fault_level('blocking' if active else 'none')

    def set_system_fault_level(self, level: str) -> None:
        normalized = str(level or 'none').strip().lower()
        if normalized not in {'none', 'blocking', 'time_warning'}:
            normalized = 'none'
        self.system_fault_level = normalized
        if not GPIO_AVAILABLE:
            text = {
                'none': 'AUS',
                'blocking': 'SCHNELL BLINKEN',
                'time_warning': 'LANGSAM BLINKEN',
            }[self.system_fault_level]
            self._dummy_red(text)

    def signal_green_success(self, blink_count: int = 1) -> None:
        threading.Thread(target=self._green_success_worker, args=(max(1, int(blink_count)),), daemon=True).start()

    def signal_generic_error(self) -> None:
        self._blink_error_led(GENERIC_ERROR_BLINKS)

    def signal_duplicate_error(self) -> None:
        self._blink_error_led(DUPLICATE_ERROR_BLINKS)

    def _green_success_worker(self, blink_count: int) -> None:
        with self.blink_lock:
            self._green_override_active = True
            for _ in range(blink_count):
                self._set_green_led(True)
                time.sleep(SUCCESS_BLINK_ON_SECONDS)
                self._set_green_led(False)
                time.sleep(SUCCESS_BLINK_OFF_SECONDS)
            self._green_override_active = False

    def _blink_error_led(self, blink_count: int) -> None:
        threading.Thread(target=self._blink_error_worker, args=(blink_count,), daemon=True).start()

    def _blink_error_worker(self, blink_count: int) -> None:
        with self.blink_lock:
            self._red_override_active = True
            for _ in range(blink_count):
                self._set_red_led(True)
                time.sleep(ERROR_BLINK_ON_SECONDS)
                self._set_red_led(False)
                time.sleep(ERROR_BLINK_OFF_SECONDS)
            self._red_override_active = False

    def _green_indicator_worker(self) -> None:
        """Hintergrundlogik fuer Bereitschafts- und Lieferscheinanzeige."""
        state = False
        while not self.stop_event.is_set():
            if self._green_override_active:
                time.sleep(0.02)
                continue
            if self.listing_mode_active:
                state = not state
                self._set_green_led(state)
                time.sleep(LISTING_MODE_BLINK_INTERVAL_SECONDS)
                continue
            self._set_green_led(self.ready_state)
            time.sleep(0.08)

    def _red_indicator_worker(self) -> None:
        """Hintergrundlogik fuer Warn- und Fehleranzeige."""
        state = False
        while not self.stop_event.is_set():
            if self._red_override_active:
                time.sleep(0.02)
                continue
            if self.system_fault_level == 'blocking':
                state = not state
                self._set_red_led(state)
                time.sleep(SYSTEM_ERROR_BLOCKING_BLINK_ON_SECONDS if state else SYSTEM_ERROR_BLOCKING_BLINK_OFF_SECONDS)
                continue
            if self.system_fault_level == 'time_warning':
                state = not state
                self._set_red_led(state)
                time.sleep(SYSTEM_ERROR_TIME_WARNING_BLINK_ON_SECONDS if state else SYSTEM_ERROR_TIME_WARNING_BLINK_OFF_SECONDS)
                continue
            state = False
            self._set_red_led(False)
            time.sleep(0.08)

    def _set_green_led(self, enabled: bool) -> None:
        if GPIO_AVAILABLE and self.initialized:
            GPIO.output(GREEN_LED_PIN, GPIO.HIGH if enabled else GPIO.LOW)
        else:
            self._dummy_green('AN' if enabled else 'AUS')

    def _set_red_led(self, enabled: bool) -> None:
        if GPIO_AVAILABLE and self.initialized:
            GPIO.output(RED_LED_PIN, GPIO.HIGH if enabled else GPIO.LOW)
        else:
            self._dummy_red('AN' if enabled else 'AUS')

    def _dummy_green(self, value: str) -> None:
        if value != self._last_dummy_green:
            print(f'[GPIO] Grüne LED: {value}')
            self._last_dummy_green = value

    def _dummy_red(self, value: str) -> None:
        if value != self._last_dummy_red:
            print(f'[GPIO] Rote LED: {value}')
            self._last_dummy_red = value

    def get_status(self) -> Dict:
        return {
            'available': bool(GPIO_AVAILABLE),
            'initialized': bool(self.initialized),
            'ready_state': bool(self.ready_state),
            'listing_mode_active': bool(self.listing_mode_active),
            'system_fault_active': self.system_fault_level != 'none',
            'system_fault_level': self.system_fault_level,
            'pins': dict(ACTIVE_GPIO_CONFIG),
            'last_callback_error': self._last_callback_error,
        }
