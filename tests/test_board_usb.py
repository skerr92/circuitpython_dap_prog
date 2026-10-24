"""Board-definition contracts and optional USB/OLED job sequencing."""
import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


usb = module("Kavrous_usb")
boards = module("Kavrous_board")
status_module = module("Kavrous_status")


class USBTests(unittest.TestCase):
    def setUp(self):
        parent = types.ModuleType("usb")
        parent.core = types.ModuleType("usb.core")
        self.find = Mock(return_value=[])
        parent.core.find = self.find
        self.port = Mock()
        modules = patch.dict(sys.modules, {"usb": parent, "usb.core": parent.core,
                                          "usb_host": types.SimpleNamespace(Port=self.port)})
        modules.start()
        self.addCleanup(modules.stop)

    def test_reads_ids_and_passes_filters_without_claiming_interfaces(self):
        host = usb.USBHost("dp", "dm")
        device = types.SimpleNamespace(idVendor=0x1209, idProduct=1)
        self.find.return_value = iter([device])
        self.assertEqual(host.scan(vid="0x1209", pid="0001"), [{"vid": 0x1209, "pid": 1}])
        self.find.assert_called_once_with(find_all=True, idVendor=0x1209, idProduct=1)

    def test_polling_waits_for_enumeration(self):
        host = usb.USBHost("dp", "dm")
        self.find.side_effect = [[], [types.SimpleNamespace(idVendor=2, idProduct=3)]]
        with patch.object(usb.time, "sleep") as sleep:
            self.assertEqual(host.wait_for_device(), {"vid": 2, "pid": 3})
        sleep.assert_called_once()

    def test_no_device_timeout_and_invalid_ids(self):
        host = usb.USBHost("dp", "dm")
        self.assertIsNone(host.wait_for_device(timeout=0))
        for value in (-1, 65536, True, "not-hex"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                host.scan(vid=value)

    def test_missing_firmware_module_has_clear_error(self):
        with patch.dict(sys.modules, {"usb_host": None}):
            with self.assertRaisesRegex(RuntimeError, "build needs usb_host"):
                usb.USBHost("dp", "dm")


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "examples/board_definitions/samd11_shim_usb.json").read_text())
        self.data["display"]["enabled"] = False
        self.events = []
        self.found = {"vid": 0x1209, "pid": 1}
        self.program_error = None
        self.connect_error = None
        case = self

        class Power:
            def __init__(self, *args, **kwargs):
                case.events.append("power_init")
                self.voltage = 2.315
            def __enter__(self):
                return self
            def __exit__(self, *_):
                case.events.append("power_exit")
            def wait_until_ready(self, *_):
                case.events.append("power_ready")
            def shutdown(self):
                case.events.append("power_off")

        class Programmer:
            def __init__(self, *args, **kwargs):
                case.events.append("programmer")
                self.arm = types.SimpleNamespace(reset=lambda: case.events.append("reset"))
            def __enter__(self):
                return self
            def __exit__(self, *_):
                case.events.append("swd_release")
            def connect(self):
                case.events.append("connect")
                if case.connect_error is not None:
                    raise case.connect_error
                return 0x0BC11477
            def program(self, filename, **kwargs):
                case.events.append("flash")
                if case.program_error is not None:
                    raise case.program_error
                for stage in ("erase", "program", "verify", "reset", "complete"):
                    kwargs["status"](stage, 64, 64)
                return 64

        def host(*_):
            self.events.append("usb_host")
            return types.SimpleNamespace(wait_for_device=identify)

        def identify(**_):
            self.events.append("usb_scan")
            return self.found

        modules = patch.dict(sys.modules, {
            "Kavrous_usb": usb,
            "Kavrous_cmsis_dap": types.SimpleNamespace(TARGETS={"samd11": object}, Programmer=Programmer),
            "Kavrous_power": types.SimpleNamespace(PowerControl=Power),
            "board": types.SimpleNamespace(A1=27, A2=28),
            "microcontroller": types.SimpleNamespace(pin=types.SimpleNamespace(
                **{"GPIO%d" % i: i for i in range(30)})),
        })
        modules.start()
        self.addCleanup(modules.stop)
        host_patch = patch.object(usb, "USBHost", side_effect=host)
        host_patch.start()
        self.addCleanup(host_patch.stop)
        clock = patch.object(boards.time, "sleep")
        clock.start()
        self.addCleanup(clock.stop)

    def test_relative_paths_and_example_ids(self):
        data = copy.deepcopy(self.data)
        data["firmware"] = "image.bin"
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "board.json"
            path.write_text(json.dumps(data))
            board = boards.load_board(path.as_posix())
            self.assertEqual(board.firmware, path.parent.as_posix() + "/image.bin")
            self.assertEqual(board.usb["vid"], 0x1209)
        self.assertEqual(self.events, [])

    def test_invalid_configuration_is_rejected_before_hardware(self):
        variants = []
        for section, key, value in (
                (None, "version", 2), (None, "version", True), (None, "typo", 1),
                ("swd", "swclk", "GPIO0"), ("power", "off_voltage", 3),
                ("usb", "vid", "0x10000"), ("usb", "enabled", "yes"),
                ("usb", "dm", "GPIO20"), ("swd", "timeout", float("nan")),
                ("display", "address", "0x80")):
            data = copy.deepcopy(self.data)
            (data if section is None else data[section])[key] = value
            variants.append(data)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ValueError):
                boards.BoardDefinition(data)
        self.assertEqual(self.events, [])

    def test_pin_alias_collision_is_rejected_before_power(self):
        self.data["swd"]["swclk"] = "GPIO27"
        board = boards.BoardDefinition(self.data)
        with self.assertRaisesRegex(ValueError, "same physical pin"):
            board.program()
        self.assertEqual(self.events, [])

    def test_success_reserves_usb_before_swd_and_shuts_down(self):
        board = boards.BoardDefinition(self.data)
        self.assertEqual(board.program(), {"written": 64, "usb": self.found})
        self.assertLess(self.events.index("usb_host"), self.events.index("programmer"))
        self.assertLess(self.events.index("swd_release"), self.events.index("usb_scan"))
        self.assertEqual(self.events[-2:], ["power_off", "power_exit"])

    def test_optional_usb_timeout_does_not_fail_programming(self):
        self.data["usb"]["required"] = False
        self.found = None
        self.assertEqual(boards.BoardDefinition(self.data).program(), {"written": 64, "usb": None})

    def test_required_usb_failure_leaves_power_off_after_flashing(self):
        self.found = None
        with self.assertRaisesRegex(RuntimeError, "did not enumerate"):
            boards.BoardDefinition(self.data).program()
        self.assertIn("flash", self.events)
        self.assertEqual(self.events[-2:], ["power_off", "power_exit"])

    def test_flash_failure_never_scans_usb_and_disables_power(self):
        self.program_error = OSError("bad image")
        with self.assertRaises(OSError):
            boards.BoardDefinition(self.data).program()
        self.assertNotIn("usb_scan", self.events)
        self.assertEqual(self.events[-2:], ["power_off", "power_exit"])

    def test_identify_resets_if_requested_without_flashing(self):
        self.assertEqual(boards.BoardDefinition(self.data).identify_usb(), self.found)
        self.assertIn("connect", self.events)
        self.assertIn("reset", self.events)
        self.assertNotIn("flash", self.events)

    def test_power_only_does_not_initialize_usb(self):
        self.data["usb"] = {"enabled": False}
        self.assertEqual(boards.BoardDefinition(self.data).program(), {"written": 64, "usb": None})
        self.assertNotIn("usb_host", self.events)

    def test_oled_final_result_is_displayed_after_power_off(self):
        board = boards.BoardDefinition(self.data)
        screen = types.SimpleNamespace(show=lambda stage, *_args, **_kwargs:
                                       self.events.append("display:" + stage))
        with patch.object(board, "_status_display", return_value=screen):
            board.program()
        self.assertLess(self.events.index("power_off"), self.events.index("display:SUCCESS - POWER OFF"))
        self.assertIn("display:verify", self.events)

    def test_oled_error_cannot_prevent_shutdown_or_hide_original_failure(self):
        board = boards.BoardDefinition(self.data)
        screen = types.SimpleNamespace(show=Mock(side_effect=OSError("display disconnected")))
        with patch.object(board, "_status_display", return_value=screen):
            with self.assertRaisesRegex(OSError, "display disconnected"):
                board.program()
        self.assertEqual(self.events[-2:], ["power_off", "power_exit"])

    def test_complete_check_passes_all_steps_without_writing_flash(self):
        result = boards.BoardDefinition(self.data).check()
        self.assertEqual(result, {"power": True, "cmsis": True,
                                  "dpidr": 0x0BC11477, "usb": self.found})
        self.assertNotIn("flash", self.events)
        self.assertLess(self.events.index("connect"), self.events.index("usb_scan"))
        self.assertEqual(self.events[-2:], ["power_off", "power_exit"])

    def test_check_requires_usb_even_when_profile_marks_it_optional(self):
        self.data["usb"]["required"] = False
        self.found = None
        with self.assertRaisesRegex(RuntimeError, "enumeration did not complete"):
            boards.BoardDefinition(self.data).check()
        self.assertEqual(self.events[-2:], ["power_off", "power_exit"])

    def test_cmsis_failure_marks_failed_stage_and_never_scans_usb(self):
        self.connect_error = OSError("no SWD response")
        board = boards.BoardDefinition(self.data)
        screen = types.SimpleNamespace(show_checks=Mock())
        with patch.object(board, "_status_display", return_value=screen):
            with self.assertRaisesRegex(OSError, "no SWD response"):
                board.check()
        final = screen.show_checks.call_args
        self.assertTrue(final.kwargs["failed"])
        self.assertEqual(final.args[0][1]["state"], "FAIL")
        self.assertEqual(final.args[0][2]["state"], "WAIT")
        self.assertNotIn("usb_scan", self.events)
        self.assertEqual(self.events[-2:], ["power_off", "power_exit"])


class DisplayTests(unittest.TestCase):
    def test_checklist_never_shows_success_for_incomplete_checks(self):
        display = object.__new__(status_module.StatusDisplay)
        display._labels = [types.SimpleNamespace(text="") for _ in range(4)]
        display.display = types.SimpleNamespace(refresh=Mock())
        checks = [{"name": name, "state": state} for name, state in
                  (("POWER", "PASS"), ("CMSIS", "PASS"), ("USB", "WAIT"))]
        display.show_checks(checks, finished=True)
        self.assertEqual(display._labels[0].text, "INCOMPLETE")
        checks[2]["state"] = "PASS"
        display.show_checks(checks, finished=True)
        self.assertEqual(display._labels[0].text, "SUCCESS - POWER OFF")
        self.assertEqual([label.text for label in display._labels[1:]],
                         ["POWER PASS", "CMSIS PASS", "USB PASS"])

    def test_progress_throttles_but_final_and_stage_changes_refresh(self):
        display = object.__new__(status_module.StatusDisplay)
        display._labels = [types.SimpleNamespace(text="") for _ in range(4)]
        display._title = "SHIM"
        display._last_stage = None
        display._updated_at = 0
        display.display = types.SimpleNamespace(refresh=Mock())
        with patch.object(status_module.time, "monotonic", side_effect=[0, 0.01, 0.02, 0.03]):
            display.show("erase", 0, 10)
            display.show("erase", 5, 10)
            display.show("erase", 10, 10)
            display.show("verify", 0, 64)
        self.assertEqual(display.display.refresh.call_count, 3)
        self.assertEqual(display._labels[1].text, "VERIFY")
        self.assertEqual(display._labels[2].text, "0/64 0%")
