"""Load board definitions and run powered SWD jobs with optional USB discovery.

SPDX-License-Identifier: MIT
Copyright (c) 2026 Seth Kerr
"""
import json
import math
import time


def _keys(value, allowed, required, where):
    if not isinstance(value, dict):
        raise ValueError(where + " must be an object")
    for key in value:
        if key not in allowed:
            raise ValueError("Unknown field: " + where + "." + key)
    for key in required:
        if key not in value:
            raise ValueError("Missing field: " + where + "." + key)


def _number(value, where, minimum=0, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < minimum or (positive and value == 0)):
        raise ValueError("Invalid number: " + where)
    return value


def _pin_name(value):
    if (not isinstance(value, str) or not value
            or value[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789"
                   for char in value)):
        raise ValueError("Pins must be names such as GPIO1 or A2")
    return value


def _pin(value):
    if value.startswith("GPIO"):
        from microcontroller import pin
        namespace = pin
    else:
        import board
        namespace = board
    try:
        return getattr(namespace, value)
    except AttributeError:
        raise ValueError("Pin is unavailable on this programmer: " + value)


class BoardDefinition:
    """Version-1 JSON configuration. Loading never claims pins or enables power."""

    def __init__(self, data, directory=""):
        from Kavrous_cmsis_dap import TARGETS
        from Kavrous_usb import usb_id

        _keys(data, ("version", "name", "target", "firmware", "swd", "power", "usb", "display"),
              ("version", "name", "target", "firmware", "swd", "power"), "board")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("Unsupported board definition version")
        for field in ("name", "target", "firmware"):
            if not isinstance(data[field], str) or not data[field]:
                raise ValueError(field + " must be a nonempty string")
        self.name = data["name"]
        self.target = data["target"].lower()
        if self.target not in TARGETS:
            raise ValueError("Unknown target: " + self.target)
        firmware = data["firmware"]
        self.firmware = (directory + "/" + firmware if directory and not firmware.startswith("/")
                         else firmware)
        swd = dict(data["swd"]) if isinstance(data["swd"], dict) else data["swd"]
        _keys(swd, ("swclk", "swdio", "reset", "frequency", "timeout"),
              ("swclk", "swdio"), "swd")
        swd.setdefault("reset", None)
        swd.setdefault("frequency", 1000000)
        swd.setdefault("timeout", 2)
        if not 1000 <= _number(swd["frequency"], "swd.frequency") <= 10000000:
            raise ValueError("swd.frequency must be between 1000 and 10000000")
        _number(swd["timeout"], "swd.timeout", positive=True)
        power = dict(data["power"]) if isinstance(data["power"], dict) else data["power"]
        _keys(power, ("sense", "enable", "on_voltage", "off_voltage", "settle_time",
                      "power_timeout", "startup_delay"), ("sense", "enable"), "power")
        defaults = {"on_voltage": 2.2, "off_voltage": 2.0, "settle_time": 0.1,
                    "power_timeout": 5, "startup_delay": 2}
        for key in defaults:
            power.setdefault(key, defaults[key])
            _number(power[key], "power." + key, positive=key == "power_timeout")
        if not power["off_voltage"] < power["on_voltage"] <= 3.3:
            raise ValueError("Power thresholds must satisfy 0 <= off < on <= 3.3")
        usb = dict(data.get("usb", {})) if isinstance(data.get("usb", {}), dict) else data["usb"]
        _keys(usb, ("enabled", "dp", "dm", "vid", "pid", "timeout", "required",
                    "reset_before_scan"), (), "usb")
        for key, default in (("enabled", False), ("required", False), ("timeout", 5),
                             ("reset_before_scan", False)):
            usb.setdefault(key, default)
        for key in ("enabled", "required", "reset_before_scan"):
            if type(usb[key]) is not bool:
                raise ValueError("usb." + key + " must be true or false")
        if usb["required"] and not usb["enabled"]:
            raise ValueError("Required USB identification must be enabled")
        if usb["reset_before_scan"] and swd["reset"] is None:
            raise ValueError("usb.reset_before_scan requires an SWD reset pin")
        _number(usb["timeout"], "usb.timeout")
        for key in ("vid", "pid"):
            usb[key] = None if usb.get(key) is None else usb_id(usb[key])
        if usb["enabled"] and ("dp" not in usb or "dm" not in usb):
            raise ValueError("Enabled USB requires dp and dm pins")
        display = data.get("display", {})
        _keys(display, ("enabled", "controller", "scl", "sda", "address", "width", "height",
                        "rotation"), (), "display")
        display = dict(display)
        for key, default in (("enabled", False), ("controller", "ssd1306"), ("address", 0x3C),
                             ("width", 128), ("height", 64), ("rotation", 0)):
            display.setdefault(key, default)
        if type(display["enabled"]) is not bool:
            raise ValueError("display.enabled must be true or false")
        if display["controller"] not in ("ssd1306", "sh1106"):
            raise ValueError("display.controller must be ssd1306 or sh1106")
        display["address"] = usb_id(display["address"])
        if not 0x08 <= display["address"] <= 0x77:
            raise ValueError("OLED address must be a 7-bit I2C address")
        if display["width"] != 128 or display["height"] != 64 or display["rotation"] not in (0, 180):
            raise ValueError("OLED must be 128x64, rotation 0 or 180")
        if display["enabled"] and ("scl" not in display or "sda" not in display):
            raise ValueError("Enabled OLED requires explicit scl and sda pins")
        pins = [swd["swclk"], swd["swdio"], power["sense"], power["enable"]]
        if swd["reset"] is not None:
            pins.append(swd["reset"])
        for key in ("dp", "dm"):
            if key in usb:
                pins.append(usb[key])
        for key in ("scl", "sda"):
            if key in display:
                pins.append(display[key])
        for name in pins:
            _pin_name(name)
        if len(set(pins)) != len(pins):
            raise ValueError("Board pins must be distinct")
        if usb["enabled"] and usb["dp"].startswith("GPIO") and usb["dm"].startswith("GPIO"):
            try:
                adjacent = abs(int(usb["dp"][4:]) - int(usb["dm"][4:])) == 1
            except ValueError:
                adjacent = False
            if not adjacent:
                raise ValueError("RP2040 USB data pins must be adjacent GPIOs")
        self.swd = swd
        self.power = power
        self.usb = usb
        self.display = display

    def _pins(self):
        values = {"swclk": _pin(self.swd["swclk"]), "swdio": _pin(self.swd["swdio"]),
                  "sense": _pin(self.power["sense"]), "enable": _pin(self.power["enable"])}
        values["reset"] = None if self.swd["reset"] is None else _pin(self.swd["reset"])
        if self.usb["enabled"]:
            values["dp"] = _pin(self.usb["dp"])
            values["dm"] = _pin(self.usb["dm"])
        if self.display["enabled"]:
            values["scl"] = _pin(self.display["scl"])
            values["sda"] = _pin(self.display["sda"])
        used = [value for value in values.values() if value is not None]
        if len(set(used)) != len(used):
            raise ValueError("Pin aliases refer to the same physical pin")
        return values

    def _power_control(self, pins):
        from Kavrous_power import PowerControl
        return PowerControl(pins["sense"], pins["enable"],
                            on_voltage=self.power["on_voltage"],
                            off_voltage=self.power["off_voltage"],
                            settle_time=self.power["settle_time"])

    def _usb_host(self, pins):
        if not self.usb["enabled"]:
            return None
        from Kavrous_usb import USBHost
        return USBHost(pins["dp"], pins["dm"])

    def _identify(self, host):
        if host is None:
            return None
        found = host.wait_for_device(vid=self.usb["vid"], pid=self.usb["pid"],
                                     timeout=self.usb["timeout"])
        if found is None and self.usb["required"]:
            raise RuntimeError("Expected USB device did not enumerate before timeout")
        return found

    def _status_display(self, pins):
        if not self.display["enabled"]:
            return None
        from Kavrous_status import StatusDisplay
        return StatusDisplay(pins["scl"], pins["sda"], controller=self.display["controller"],
                             address=self.display["address"], width=self.display["width"],
                             height=self.display["height"], rotation=self.display["rotation"],
                             title=self.name)

    def create_status_display(self):
        """Initialize the configured OLED without enabling power or USB host."""
        return self._status_display(self._pins())

    def identify_usb(self):
        """Power the existing firmware, discover its USB IDs, then shut down."""
        if not self.usb["enabled"]:
            raise ValueError("USB identification is disabled in this board definition")
        return self._run_job(False)["usb"]

    def check(self, *, status=None):
        """Check power, SWD device connection/reset, and USB; do not write flash.

        All three must pass regardless of usb.required. Leaves power off and
        displays SUCCESS only after all checks pass and shutdown completes.
        """
        if not self.usb["enabled"]:
            raise ValueError("The complete board check requires USB identification enabled")
        return self._run_job(False, check_job=True, status=status)

    def program(self, filename=None, *, address=None, verify=True, reset=True, progress=None,
                status=None):
        """Program, optionally identify running USB firmware, then latch power off.

        Returns {"written": byte_count, "usb": {"vid": ..., "pid": ...} or None}.
        USB-required failures occur after successful flashing; they do not undo
        flash contents. USB discovery requires reset=True to run the firmware.
        """
        if self.usb["enabled"] and not reset:
            raise ValueError("USB identification after programming requires reset=True")
        return self._run_job(True, filename, address=address, verify=verify, reset=reset,
                             progress=progress, status=status)

    def _run_job(self, program_job, filename=None, *, address=None, verify=True, reset=True,
                 progress=None, status=None, check_job=False):
        from Kavrous_cmsis_dap import Programmer
        pins = self._pins()
        screen = None
        written = 0
        found = None
        identity = None
        checks = [{"name": name, "state": "WAIT", "detail": ""}
                  for name in ("POWER", "CMSIS", "USB")]
        active_check = 0
        host = None

        def report(stage, done=0, total=0, detail=""):
            nonlocal active_check
            if status is not None:
                status(stage, done, total)
            if check_job:
                changes = {"power": (0, "RUN"), "power_pass": (0, "PASS"),
                           "connect": (1, "RUN"), "reset": (1, "RUN"),
                           "cmsis_pass": (1, "PASS"), "usb": (2, "RUN"),
                           "usb_pass": (2, "PASS")}
                if stage in changes:
                    active_check, state = changes[stage]
                    checks[active_check]["state"] = state
                    checks[active_check]["detail"] = detail
                if screen is not None:
                    screen.show_checks(checks, finished=stage == "done")
                return
            if screen is not None:
                final = "SUCCESS - POWER OFF" if verify and (host is None or found) else "DONE - POWER OFF"
                screen.show(final if stage == "done" else stage,
                            done, total, detail=detail)

        with self._power_control(pins) as power:
            try:
                screen = self._status_display(pins)
                report("power", detail="Qualifying USB-C")
                # PIO USB needs a whole free instruction bank. Reserve it before SWD.
                active_check = 2
                host = self._usb_host(pins)
                active_check = 0
                power.wait_until_ready(self.power["power_timeout"])
                report("power", detail="Target startup")
                time.sleep(self.power["startup_delay"])
                if check_job:
                    report("power_pass", detail="%.2fV" % power.voltage)
                if program_job or check_job or self.usb["reset_before_scan"]:
                    report("connect")
                    with Programmer(pins["swclk"], pins["swdio"], self.target,
                                    reset_pin=pins["reset"], frequency=self.swd["frequency"],
                                    timeout=self.swd["timeout"]) as programmer:
                        if program_job:
                            written = programmer.program(self.firmware if filename is None else filename,
                                                         address=address, verify=verify, reset=reset,
                                                         progress=progress, status=report)
                        else:
                            identity = programmer.connect()
                            report("reset")
                            programmer.arm.reset()
                            if check_job:
                                report("cmsis_pass")
                if host is not None:
                    report("usb", detail="Reading VID/PID")
                    found = self._identify(host)
                    if check_job:
                        if found is None:
                            raise RuntimeError("USB enumeration did not complete")
                        report("usb_pass", detail="%04X:%04X" % (found["vid"], found["pid"]))
            except BaseException as error:
                power.shutdown()
                if screen is not None:
                    try:
                        if check_job:
                            checks[active_check]["state"] = "FAIL"
                            screen.show_checks(checks, failed=True)
                        else:
                            screen.show("ERROR - POWER OFF", detail=str(error))
                    except Exception:
                        pass  # Preserve the original failure after powering off.
                raise
            finally:
                power.shutdown()
            detail = "USB %04X:%04X" % (found["vid"], found["pid"]) if found else ""
            report("done", written, written, detail)
            if check_job:
                return {"power": True, "cmsis": True, "dpidr": identity, "usb": found}
            return {"written": written, "usb": found}


def load_board(filename):
    """Read a local JSON definition; relative firmware paths use its directory."""
    with open(filename, "r") as source:
        data = json.load(source)
    directory = filename.rsplit("/", 1)[0] if "/" in filename else ""
    return BoardDefinition(data, directory)
