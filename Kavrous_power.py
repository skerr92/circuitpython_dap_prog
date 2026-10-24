"""Voltage-qualified, active-high load-switch control for CircuitPython.

SPDX-License-Identifier: MIT
Copyright (c) 2026 Seth Kerr
"""
import time


class PowerControl:
    """Enable a load switch after the sense input has settled above a threshold.

    Voltages refer to the ADC pin, after the divider. Call update() regularly;
    this controller does not run in the background. Falling below off_voltage
    disables immediately on the next update. Intermediate readings retain the
    enabled state. Startup, read errors, and deinit leave the output disabled.
    """

    def __init__(self, sense_pin, enable_pin, *, on_voltage=2.2,
                 off_voltage=2.0, settle_time=0.1, samples=8):
        if sense_pin == enable_pin:
            raise ValueError("Sense and enable pins must differ")
        if not 0 <= off_voltage < on_voltage or settle_time < 0:
            raise ValueError("Invalid voltage thresholds or settle time")
        if not isinstance(samples, int) or samples < 1:
            raise ValueError("samples must be a positive integer")
        import analogio
        import digitalio

        self.on_voltage = on_voltage
        self.off_voltage = off_voltage
        self.settle_time = settle_time
        self.samples = samples
        self.voltage = 0.0
        self.enabled = False
        self._inhibited = False
        self._good_since = None
        self._adc = None
        self._enable = digitalio.DigitalInOut(enable_pin)
        try:
            self._enable.switch_to_output(value=False)
            self._adc = analogio.AnalogIn(sense_pin)
            if on_voltage > self._adc.reference_voltage:
                raise ValueError("Enable threshold exceeds ADC reference voltage")
        except BaseException:
            self.deinit()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.deinit()

    def disable(self):
        """Disable the output and restart the power qualification interval."""
        self._enable.value = False
        self.enabled = False
        self._good_since = None

    def shutdown(self):
        """Latch power off until arm() or an explicit new programming job."""
        self._inhibited = True
        self.disable()

    def arm(self):
        """Allow voltage-qualified power again, starting a fresh settle interval."""
        self.disable()
        self._inhibited = False

    def wait_until_ready(self, timeout=5):
        """Wait for qualified power; call arm() first if power is inhibited."""
        if timeout <= 0:
            raise ValueError("Power timeout must be positive")
        deadline = time.monotonic() + timeout
        while not self.update():
            if time.monotonic() >= deadline:
                self.shutdown()
                raise RuntimeError("External USB-C power did not become ready")
            time.sleep(0.02)

    def program(self, swclk, swdio, filename, target=None, *, power_timeout=5,
                power_delay=2.0, **kwargs):
        """Power a target for one programming job, then latch power off.

        Each explicit call rearms power. Completion, failure, or interruption
        always shuts down. power_delay allows target startup after enabling.
        Other options are forwarded to Kavrous_cmsis_dap.program().
        """
        try:
            if power_delay < 0:
                raise ValueError("Power startup delay must be nonnegative")
            from Kavrous_cmsis_dap import program

            self.arm()
            self.wait_until_ready(power_timeout)
            time.sleep(power_delay)
            return program(swclk, swdio, filename, target, **kwargs)
        finally:
            self.shutdown()

    def update(self):
        """Sample voltage and apply hysteresis; return the enabled state."""
        if self._adc is None or self._enable is None:
            raise RuntimeError("Power controller has been deinitialized")
        try:
            reading = 0
            for _ in range(self.samples):
                reading += self._adc.value
            self.voltage = reading * self._adc.reference_voltage / (65535 * self.samples)
            if self._inhibited:
                self.disable()
                return False
            now = time.monotonic()
            if self.enabled:
                if self.voltage <= self.off_voltage:
                    self.disable()
            elif self.voltage >= self.on_voltage:
                if self._good_since is None:
                    self._good_since = now
                if now - self._good_since >= self.settle_time:
                    self._enable.value = True
                    self.enabled = True
            else:
                self._good_since = None
            return self.enabled
        except BaseException:
            self.disable()
            raise

    def deinit(self):
        """Turn off the load switch and release both pins."""
        try:
            if self._enable is not None:
                try:
                    self.disable()
                finally:
                    self._enable.deinit()
                    self._enable = None
        finally:
            if self._adc is not None:
                self._adc.deinit()
                self._adc = None
