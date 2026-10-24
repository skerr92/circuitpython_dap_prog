"""Power qualification and GPIO cleanup checks using simulated ADC readings."""
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "power_module", pathlib.Path(__file__).resolve().parents[1] / "Kavrous_power.py")
power_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(power_module)


class PowerTests(unittest.TestCase):
    def setUp(self):
        self.adc = types.SimpleNamespace(value=0, reference_voltage=3.3,
                                         deinit=lambda: None)
        self.output = types.SimpleNamespace(value=True, deinit=lambda: None)
        self.output.switch_to_output = lambda **kwargs: setattr(self.output, "value", kwargs["value"])
        self.now = 0
        modules = patch.dict(sys.modules,
            analogio=types.SimpleNamespace(AnalogIn=lambda _: self.adc),
            digitalio=types.SimpleNamespace(DigitalInOut=lambda _: self.output))
        modules.start()
        self.addCleanup(modules.stop)
        clock = patch.object(power_module.time, "monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.control = power_module.PowerControl("sense", "enable")
        self.addCleanup(self.control.deinit)

    def sample(self, voltage, now):
        self.adc.value = round(voltage * 65535 / 3.3)
        self.now = now
        return self.control.update()

    def enable(self):
        self.assertFalse(self.sample(2.5, 0))
        self.assertTrue(self.sample(2.5, 0.11))

    def test_startup_and_absent_supply(self):
        self.assertFalse(self.output.value)
        self.assertFalse(self.sample(0.1, 1))
        self.assertAlmostEqual(self.control.voltage, 0.1, places=3)

    def test_stable_voltage_required(self):
        self.assertFalse(self.sample(2.5, 0))
        self.assertFalse(self.sample(2.5, 0.05))
        self.assertTrue(self.sample(2.5, 0.11))
        self.assertTrue(self.output.value)

    def test_noise_restarts_qualification(self):
        self.assertFalse(self.sample(2.5, 0))
        self.assertFalse(self.sample(2.1, 0.09))
        self.assertFalse(self.sample(2.5, 0.12))
        self.assertFalse(self.sample(2.5, 0.20))
        self.assertTrue(self.sample(2.5, 0.23))

    def test_hysteresis_and_power_loss(self):
        self.enable()
        self.assertTrue(self.sample(2.1, 0.15))
        self.assertFalse(self.sample(1.9, 0.17))
        self.assertFalse(self.output.value)
        self.assertFalse(self.sample(2.1, 0.5))

    def test_adc_error_turns_output_off(self):
        self.enable()
        class BrokenADC:
            @property
            def value(self):
                raise OSError("ADC read failed")
            def deinit(self):
                pass
        self.control._adc = BrokenADC()
        with self.assertRaises(OSError):
            self.control.update()
        self.assertFalse(self.output.value)
        self.assertFalse(self.control.enabled)

    def test_cleanup_turns_output_off_and_is_idempotent(self):
        self.enable()
        self.control.deinit()
        self.control.deinit()
        self.assertFalse(self.output.value)
        with self.assertRaises(RuntimeError):
            self.control.update()

    def test_invalid_settings(self):
        for kwargs in ({"on_voltage": 2, "off_voltage": 2.1},
                       {"settle_time": -1}, {"samples": 0}, {"samples": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                power_module.PowerControl("sense", "enable", **kwargs)

    def test_adc_initialization_failure_disables_output(self):
        with patch.object(sys.modules["analogio"], "AnalogIn", side_effect=OSError("ADC init")):
            with self.assertRaises(OSError):
                power_module.PowerControl("sense", "enable")
        self.assertFalse(self.output.value)

    def test_shutdown_stays_off_until_explicitly_rearmed(self):
        self.enable()
        self.control.shutdown()
        self.assertFalse(self.sample(2.5, 1))
        self.assertFalse(self.sample(2.5, 2))
        self.control.arm()
        self.assertFalse(self.sample(2.5, 3))
        self.assertTrue(self.sample(2.5, 3.11))

    def test_program_success_and_failures_always_latch_off(self):
        for error in (None, OSError("missing image"), KeyboardInterrupt()):
            with self.subTest(error=error):
                def ready(*_):
                    self.output.value = True
                    self.control.enabled = True
                def program(*args, **kwargs):
                    self.assertTrue(self.output.value)
                    if error is not None:
                        raise error
                    return 64
                module = types.SimpleNamespace(program=program)
                with patch.dict(sys.modules, Kavrous_cmsis_dap=module), \
                     patch.object(self.control, "wait_until_ready", side_effect=ready), \
                     patch.object(power_module.time, "sleep"):
                    if error is None:
                        self.assertEqual(self.control.program("clk", "dio", "file.bin"), 64)
                    else:
                        with self.assertRaises(type(error)):
                            self.control.program("clk", "dio", "file.bin")
                self.assertFalse(self.output.value)
                self.assertFalse(self.sample(2.5, self.now + 1))

    def test_power_timeout_latches_off(self):
        with patch.object(power_module.time, "monotonic", side_effect=[0, 6]), \
             patch.object(self.control, "update", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                self.control.wait_until_ready(5)
        self.assertFalse(self.output.value)
        self.assertTrue(self.control._inhibited)


if __name__ == "__main__":
    unittest.main()
