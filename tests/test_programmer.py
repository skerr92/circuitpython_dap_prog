"""Host-side checks: python -m unittest discover -s tests -v.

Install the assembler with: pip install adafruit-circuitpython-pioasm
"""

import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from collections import deque

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dap", ROOT / "Kavrous_cmsis_dap.py")
dap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dap)


def hex_record(address, kind, data=b""):
    record = bytes([len(data), address >> 8, address & 255, kind]) + data
    return ":" + (record + bytes([-sum(record) & 255])).hex() + "\n"


class MemoryDriver(dap.FlashTarget):
    flash_size = 1024
    page_size = 256
    write_size = 64

    def __init__(self, arm):
        super().__init__(arm)
        self.memory = bytearray(b"\x00" * self.flash_size)
        self.events = []

    def erase_page(self, address):
        self.events.append(("erase", address))
        self.memory[address:address + self.page_size] = b"\xff" * self.page_size

    def write(self, address, data):
        assert address % self.write_size == 0
        assert len(data) == self.write_size
        self.events.append(("write", address))
        self.memory[address:address + len(data)] = data

    def begin(self):
        self.events.append(("begin",))

    def finish(self):
        self.events.append(("finish",))


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.p = object.__new__(dap.Programmer)
        self.p.arm = types.SimpleNamespace(halt=lambda: None, reset=lambda: None)
        self.p.target = MemoryDriver(self.p.arm)
        self.p.arm.read32 = lambda address: int.from_bytes(
            self.p.target.memory[address:address + 4], "little")

    def file(self, contents, name="image.hex"):
        path = pathlib.Path(self.temp.name) / name
        if isinstance(contents, str):
            path.write_text(contents)
        else:
            path.write_bytes(contents)
        return str(path)

    def test_sparse_hex_coalesces_units_and_erases_only_touched_rows(self):
        filename = self.file(hex_record(1, 0, b"abc") + hex_record(16, 0, b"def")
                             + hex_record(513, 0, b"xyz") + hex_record(0, 1))
        self.assertEqual(self.p.program(filename), 9)
        driver = self.p.target
        self.assertEqual(driver.events, [("begin",), ("erase", 0), ("erase", 512),
                                        ("write", 0), ("write", 512), ("finish",)])
        self.assertEqual(driver.memory[1:4], b"abc")
        self.assertEqual(driver.memory[4:16], b"\xff" * 12)
        self.assertEqual(driver.memory[256:512], b"\x00" * 256)

    def test_binary_unaligned_tail_and_page_crossing(self):
        filename = self.file(bytes(range(100)), "image.bin")
        self.assertEqual(self.p.program(filename, address=253), 100)
        self.assertEqual(self.p.target.memory[253:353], bytes(range(100)))
        self.assertEqual(self.p.target.memory[353:384], b"\xff" * 31)

    def test_bad_images_fail_before_begin(self):
        images = [hex_record(0, 0, b"ab"),  # Missing EOF.
                  ":0100000001ff\n" + hex_record(0, 1),  # Bad checksum.
                  hex_record(10, 0, b"abc") + hex_record(11, 0, b"x") + hex_record(0, 1),
                  hex_record(1024, 0, b"x") + hex_record(0, 1),
                  hex_record(0, 1) + hex_record(0, 0, b"x"),
                  hex_record(0, 1)]
        for image in images:
            with self.subTest(image=image), self.assertRaises(ValueError):
                self.p.program(self.file(image))
            self.assertEqual(self.p.target.events, [])

    def test_extended_hex_address(self):
        filename = self.file(hex_record(0, 4, b"\x08\x00") +
                             hex_record(32, 0, b"abc") + hex_record(0, 1))
        self.assertEqual(list(dap._segments(filename, 0)), [(0x08000020, b"abc")])

    def test_cleanup_on_flash_failure(self):
        def fail(*_):
            raise dap.DAPError("flash failure")
        self.p.target.write = fail
        with self.assertRaises(dap.DAPError):
            self.p.program(self.file(b"a", "image.bin"))
        self.assertEqual(self.p.target.events[-1], ("finish",))

    def test_readback_mismatch(self):
        self.p.arm.read32 = lambda _: 0
        with self.assertRaisesRegex(dap.DAPError, "Readback mismatch"):
            self.p.program(self.file(b"a", "image.bin"))

    def test_status_reports_committed_programming_and_readback(self):
        events = []
        def status(stage, done, total):
            events.append((stage, done, total))
            if stage == "program" and done == total:
                self.assertEqual(self.p.target.memory[:100], bytes(range(100)))
        self.p.program(self.file(bytes(range(100)), "image.bin"), status=status)
        self.assertIn(("erase", 1, 1), events)
        self.assertIn(("program", 100, 100), events)
        self.assertIn(("verify", 100, 100), events)
        self.assertEqual(events[-1], ("complete", 100, 100))


class ScriptedSWD(dap.SWD):
    def __init__(self, inputs):
        self.inputs = deque(inputs)
        self.outputs = []
        self.retries = 3
        self.timeout = 1
        self._select = None

    def _out(self, value, count):
        self.outputs.append((value, count))

    def _in(self, count):
        expected_count, value = self.inputs.popleft()
        assert count == expected_count, (count, expected_count)
        return value


class SWDTests(unittest.TestCase):
    def test_connect_retries_initial_no_response_before_powerup(self):
        swd = ScriptedSWD([])
        swd.read_dp = unittest.mock.Mock(side_effect=[
            dap.DAPError("Invalid SWD ACK 0x7"), 0x0BC11477, 0xA0000000])
        swd.write_dp = unittest.mock.Mock()
        with patch.object(dap.time, "sleep") as sleep:
            self.assertEqual(swd.connect(), 0x0BC11477)
        sleep.assert_called_once_with(0.01)
        self.assertEqual(swd.write_dp.call_args_list,
                         [unittest.mock.call(0, 0x1E), unittest.mock.call(8, 0),
                          unittest.mock.call(4, 0x50000000)])

    def test_connect_no_response_timeout_is_bounded(self):
        swd = ScriptedSWD([])
        swd.read_dp = unittest.mock.Mock(side_effect=dap.DAPError("Invalid SWD ACK 0x7"))
        swd.write_dp = unittest.mock.Mock()
        with patch.object(dap.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(dap.DAPError, "connection timed out.*ACK 0x7"):
                swd.connect()
        swd.write_dp.assert_not_called()

    def test_connect_retries_when_id_responds_before_setup_is_ready(self):
        swd = ScriptedSWD([])
        swd.read_dp = unittest.mock.Mock(side_effect=[0x0BC11477, 0x0BC11477, 0xA0000000])
        swd.write_dp = unittest.mock.Mock(side_effect=[
            dap.DAPError("Invalid SWD ACK 0x7"), None, None, None])
        with patch.object(dap.time, "sleep"):
            self.assertEqual(swd.connect(), 0x0BC11477)
        self.assertEqual(swd.write_dp.call_args_list,
                         [unittest.mock.call(0, 0x1E), unittest.mock.call(0, 0x1E),
                          unittest.mock.call(8, 0), unittest.mock.call(4, 0x50000000)])

    def test_read_and_header_parity(self):
        swd = ScriptedSWD([(4, 2), (32, 0x12345678), (2, dap._parity(0x12345678))])
        self.assertEqual(swd.read_dp(0), 0x12345678)
        self.assertEqual(swd.outputs, [(0xA5, 8), (0, 8)])

    def test_write_turnaround(self):
        swd = ScriptedSWD([(4, 2), (1, 0)])
        swd.write_dp(8, 0x123)
        self.assertEqual(swd.outputs[1:], [(0x123, 32), (dap._parity(0x123), 1), (0, 8)])

    def test_wait_retry(self):
        swd = ScriptedSWD([(4, 4), (1, 0), (4, 2), (32, 1), (2, 1)])
        self.assertEqual(swd.read_dp(0), 1)

    def test_fault_and_invalid_ack(self):
        for ack, count in ((4, 1), (7, 34)):
            with self.subTest(ack=ack), self.assertRaises(dap.DAPError):
                ScriptedSWD([(4, ack << 1), (count, 0)]).read_dp(0)

    def test_parity_error(self):
        with self.assertRaisesRegex(dap.DAPError, "parity"):
            ScriptedSWD([(4, 2), (32, 1), (2, 0)]).read_dp(0)

    def test_posted_ap_read(self):
        swd = ScriptedSWD([])
        calls = []
        swd.transfer = lambda *args: calls.append(args) or 0x42
        self.assertEqual(swd.read_ap(0xFC, 2), 0x42)
        self.assertEqual(calls, [(False, False, 8, 0x020000F0),
                                 (True, True, 0xFC), (False, True, 12)])

    def test_tar_wrap(self):
        calls = []
        swd = types.SimpleNamespace(write_ap=lambda *args: calls.append(args),
                                    read_ap=lambda *_: 0)
        arm = dap.ARMTarget(swd)
        arm.read32(0x200003FC)
        arm.read32(0x20000400)
        arm.read32(0x20000404)
        self.assertEqual(calls, [(0, 0x23000052, 0), (4, 0x200003FC, 0),
                                 (4, 0x20000400, 0)])

    def test_halfword_lane(self):
        calls = []
        swd = types.SimpleNamespace(write_ap=lambda *args: calls.append(args))
        dap.ARMTarget(swd).write16(0x08000002, 0x1234)
        self.assertEqual(calls[-1], (12, 0x12340000, 0))


class DriverTests(unittest.TestCase):
    def arm(self, registers):
        calls = []
        arm = types.SimpleNamespace(
            read32=lambda address: registers.get(address, 0),
            write32=lambda address, value: calls.append(("w32", address, value)),
            write16=lambda address, value: calls.append(("w16", address, value)),
            write8=lambda address, value: calls.append(("w8", address, value)),
            halt=lambda: calls.append(("halt",)),
            wait=lambda address, mask, expected: registers.get(address, expected),
        )
        return arm, calls

    def test_nrf_geometry_modes_and_word_write(self):
        arm, calls = self.arm({0x10000100: 0x52840, 0x10000010: 4096,
                               0x10000014: 256})
        target = dap.NRF52(arm)
        target.probe()
        self.assertEqual(target.flash_size, 1048576)
        target.erase_page(4096)
        target.write(4096, b"\x12\x34\x56\x78")
        target.finish()
        self.assertEqual(calls, [("w32", 0x4001E504, 2),
                                 ("w32", 0x4001E508, 4096),
                                 ("w32", 0x4001E504, 1),
                                 ("w32", 4096, 0x78563412),
                                 ("w32", 0x4001E504, 0)])

    def test_stm_geometry_halfwords_and_lock(self):
        arm, calls = self.arm({0xE0042000: 0x410, 0x1FFFF7E0: 64})
        target = dap.STM32F1(arm)
        target.probe()
        target.begin()
        target.erase_page(0x08000000)
        target.write(0x08000000, b"\x12\x34\x56\x78")
        target.finish()
        self.assertEqual(target.flash_size, 65536)
        self.assertIn(("w16", 0x08000000, 0x3412), calls)
        self.assertIn(("w16", 0x08000002, 0x7856), calls)
        self.assertEqual(calls[-1], ("w32", 0x40022010, 0x80))

    def test_samd_manual_page_write_and_restore(self):
        arm, calls = self.arm({0x41002118: 0x10010005,
                               0x41004008: (3 << 16) | 4096,
                               0x41004004: 2})
        target = dap.SAMD21(arm)
        target.probe()
        target.begin()
        target.erase_page(256)
        target.write(256, bytes(range(64)))
        target.finish()
        self.assertEqual(target.flash_size, 262144)
        self.assertEqual(calls[0], ("w32", 0x41004004, 0x82))
        self.assertIn(("w32", 0x4100401C, 128), calls)
        self.assertIn(("w16", 0x41004000, 0xA544), calls)
        self.assertIn(("w16", 0x41004000, 0xA504), calls)
        self.assertEqual(calls[-1], ("w32", 0x41004004, 2))

    def test_unknown_identity_is_rejected(self):
        for driver in (dap.NRF52, dap.SAMD11, dap.SAMD21, dap.STM32F1):
            arm, calls = self.arm({})
            with self.subTest(driver=driver), self.assertRaises(dap.DAPError):
                driver(arm).probe()
            self.assertEqual(calls, [])

    def test_samd11_geometry_and_reset_extension(self):
        arm, calls = self.arm({0x41002118: 0x10030100, 0x41004008: 0x00030100})
        target = dap.SAMD11(arm)
        target.probe()
        self.assertEqual(target.flash_size, 16384)
        target.attach()
        self.assertEqual(calls, [("w32", 0xE000EDF0, 0xA05F0003),
                                 ("w8", 0x41002101, 2), ("halt",)])
        with self.assertRaises(dap.DAPError):
            dap.SAMD21(arm).probe()

    def test_samd11_rejects_oversize_geometry(self):
        arm, _ = self.arm({0x41002118: 0x10030100, 0x41004008: 0x00030200})
        with self.assertRaisesRegex(dap.DAPError, "flash size"):
            dap.SAMD11(arm).probe()


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        events = self.events

        class Pin:
            def __init__(self, pin):
                events.append(("pin", pin))

            def switch_to_output(self, **kwargs):
                events.append(("output", kwargs))

            @property
            def value(self):
                return True

            @value.setter
            def value(self, value):
                events.append(("reset", value))

            def deinit(self):
                events.append(("release",))

        digitalio = types.SimpleNamespace(DigitalInOut=Pin,
                                         DriveMode=types.SimpleNamespace(OPEN_DRAIN="open_drain"))
        self.digitalio_patch = patch.dict(sys.modules, digitalio=digitalio)
        self.digitalio_patch.start()
        self.addCleanup(self.digitalio_patch.stop)
        self.transport_patch = patch.object(dap, "SWD")
        self.transport = self.transport_patch.start()
        self.addCleanup(self.transport_patch.stop)
        self.sleep_patch = patch.object(dap.time, "sleep", side_effect=lambda delay:
                                        events.append(("sleep", delay)))
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    def test_hardware_reset_and_cleanup(self):
        with dap.Programmer("clk", "dio", reset_pin="rst", reset_hold=0.02,
                            reset_delay=0.03) as programmer:
            programmer.arm.write32 = lambda *args: self.events.append(("write",) + args)
            programmer.arm.reset()
            self.assertIsNone(programmer.arm._tar)
        self.assertEqual(self.events, [
            ("pin", "rst"), ("output", {"value": True, "drive_mode": "open_drain"}),
            ("write", 0xE000EDF0, 0xA05F0001), ("reset", False), ("sleep", 0.02),
            ("reset", True), ("sleep", 0.03), ("reset", True), ("release",)])
        self.transport.return_value.deinit.assert_called_once()

    def test_software_fallback(self):
        with dap.Programmer("clk", "dio") as programmer:
            programmer.arm.write32 = lambda *args: self.events.append(args)
            programmer.arm.reset()
        self.assertEqual(self.events, [(0xE000EDF0, 0xA05F0001),
                                       (0xE000ED0C, 0x05FA0004)])

    def test_interrupted_pulse_releases_reset(self):
        with dap.Programmer("clk", "dio", reset_pin="rst") as programmer:
            dap.time.sleep.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                programmer.hardware_reset()
            self.assertEqual(self.events[-1], ("reset", True))

    def test_reset_configuration_failure_releases_resources(self):
        def fail(*_args, **_kwargs):
            raise RuntimeError("configuration failed")
        sys.modules["digitalio"].DigitalInOut.switch_to_output = fail
        with self.assertRaises(RuntimeError):
            dap.Programmer("clk", "dio", reset_pin="rst")
        self.assertEqual(self.events[-1], ("release",))
        self.transport.return_value.deinit.assert_called_once()

    def test_reset_pin_and_timing_arguments(self):
        for kwargs in ({"reset_pin": "clk"}, {"reset_pin": "dio"},
                       {"reset_hold": 0}, {"reset_delay": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                dap.Programmer("clk", "dio", **kwargs)
        self.transport.assert_not_called()

    def test_helper_forwards_reset_configuration(self):
        with patch.object(dap, "Programmer") as constructor:
            dap.program("clk", "dio", "firmware.bin", reset_pin="rst",
                        reset_hold=0.02, reset_delay=0.03, reset=False)
            constructor.assert_called_once_with("clk", "dio", None,
                                                reset_pin="rst", reset_hold=0.02,
                                                reset_delay=0.03)
            self.assertFalse(constructor.return_value.__enter__.return_value.program.call_args.kwargs["reset"])


    def test_known_target_reset_reconnects_before_release(self):
        with dap.Programmer("clk", "dio", reset_pin="rst") as programmer:
            programmer.target = types.SimpleNamespace(
                release_reset=lambda: self.events.append(("release_extension",)))
            programmer.swd.connect.side_effect = lambda: self.events.append(("connect",))
            programmer.hardware_reset()
            self.assertEqual(self.events[-2:], [("connect",), ("release_extension",)])


class PIOTests(unittest.TestCase):
    def test_assemble_and_command_packing(self):
        # Use the actual assembler; rp2pio itself exists only on the board.
        import adafruit_pioasm
        captured = {}

        class StateMachine:
            def __init__(self, code, **kwargs):
                captured["code"] = code
                captured["kwargs"] = kwargs
                self.commands = []

            def write_readinto(self, tx, rx):
                self.commands.append(list(tx))
                rx[0] = 0xA0000000 if tx[0] & 0x20 else 0

            def deinit(self):
                captured["released"] = True

        sys.modules["rp2pio"] = types.SimpleNamespace(StateMachine=StateMachine)
        self.addCleanup(sys.modules.pop, "rp2pio")
        swd = dap.SWD("clk", "dio", frequency=2000000)
        self.addCleanup(swd.deinit)
        self.assertLessEqual(len(captured["code"]), 32)
        self.assertEqual(captured["kwargs"]["frequency"], 8000000)
        self.assertFalse(captured["kwargs"]["wait_for_txstall"])
        swd.line_reset()
        self.assertEqual(swd._sm.commands, [[31, 0xFFFFFFFF], [23, 0xFFFFFF]])
        self.assertEqual(swd._in(4), 0xA)
        self.assertEqual(swd._sm.commands[-1], [0x23])

    def test_pio_instruction_direction_and_bit_order(self):
        """Execute the assembled instructions, including side-set clock edges."""
        import adafruit_pioasm

        class PIOModel:
            def __init__(self, code, **kwargs):
                self.code = code
                self.pc = self.x = self.y = self.osr = self.isr = 0
                self.pin = self.direction = 1
                self.clock = 0
                self.input = deque()
                self.edges = []
                self.tx = deque()

            def write_readinto(self, tx, rx):
                self.tx.extend(tx)
                for _ in range(1000):
                    instruction = self.code[self.pc]
                    opcode = instruction >> 13
                    arg = instruction & 255
                    clock = (instruction >> 12) & 1
                    if clock and not self.clock:
                        self.edges.append((self.direction, self.pin))
                    self.clock = clock
                    next_pc = (self.pc + 1) % len(self.code)
                    if opcode == 0:  # JMP.
                        condition = arg >> 5
                        jump = condition == 0 or (condition == 3 and self.y == 0)
                        if condition == 2:
                            jump = self.x != 0
                            self.x = (self.x - 1) & 0xFFFFFFFF
                        if jump:
                            next_pc = arg & 31
                    elif opcode == 2:  # IN pins, count.
                        self.isr = (self.isr >> 1) | (self.input.popleft() << 31)
                    elif opcode == 3:  # OUT.
                        count = (arg & 31) or 32
                        value = self.osr & ((1 << count) - 1)
                        self.osr >>= count
                        destination = arg >> 5
                        if destination == 0:
                            self.pin = value
                        elif destination == 1:
                            self.x = value
                        elif destination == 2:
                            self.y = value
                        else:
                            raise AssertionError("Unexpected OUT destination")
                    elif opcode == 4:
                        if arg & 0x80:  # PULL.
                            if not self.tx:
                                return
                            self.osr = self.tx.popleft()
                        else:  # PUSH clears ISR.
                            rx[0] = self.isr
                            self.isr = 0
                    elif opcode == 5:
                        if arg == 0xC3:  # MOV ISR, NULL.
                            self.isr = 0
                        else:
                            assert arg == 0x42  # NOP = MOV Y, Y.
                    elif opcode == 7:
                        assert arg >> 5 == 4
                        self.direction = arg & 31
                    else:
                        raise AssertionError("Unexpected PIO instruction")
                    self.pc = next_pc
                raise AssertionError("PIO did not stall for next command")

            def deinit(self):
                pass

        sys.modules["rp2pio"] = types.SimpleNamespace(StateMachine=PIOModel)
        self.addCleanup(sys.modules.pop, "rp2pio")
        swd = dap.SWD("clk", "dio")
        self.addCleanup(swd.deinit)
        swd._out(0xA5, 8)
        self.assertEqual(swd._sm.edges, [(1, (0xA5 >> bit) & 1) for bit in range(8)])
        swd._sm.edges.clear()
        # Turnaround followed by OK ACK, LSB first.
        swd._sm.input.extend([0, 1, 0, 0])
        self.assertEqual(swd._in(4), 2)
        self.assertEqual(swd._sm.edges, [(0, 1)] * 4)
        swd._sm.edges.clear()
        swd._out(0x12345678, 32)
        self.assertEqual(swd._sm.edges,
                         [(1, (0x12345678 >> bit) & 1) for bit in range(32)])
        self.assertEqual(swd._sm.clock, 0)


if __name__ == "__main__":
    unittest.main()
