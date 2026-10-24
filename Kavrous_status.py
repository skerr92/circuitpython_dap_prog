"""128x64 I2C OLED programming status using CircuitPython displayio.

SPDX-License-Identifier: MIT
Copyright (c) 2026 Seth Kerr
"""
import time

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/skerr92/circuitpython_dap_prog.git"


class StatusDisplay:
    """Own one OLED display; keep the last result visible between jobs.

    Creating a display releases prior displayio displays. It does not release
    the persistent USB host. Refreshes are throttled within a stage so display
    updates do not dominate programming time.
    """

    def __init__(self, scl, sda, *, controller="ssd1306", address=0x3C,
                 width=128, height=64, rotation=0, title="BREAD PROG"):
        import busio
        import displayio
        import terminalio
        from i2cdisplaybus import I2CDisplayBus
        from adafruit_display_text.label import Label

        if controller == "ssd1306":
            from adafruit_displayio_ssd1306 import SSD1306 as Driver
        elif controller == "sh1106":
            from adafruit_displayio_sh1106 import SH1106 as Driver
        else:
            raise ValueError("Unknown OLED controller: " + controller)
        if width != 128 or height != 64 or rotation not in (0, 180):
            raise ValueError("Status display requires 128x64 and rotation 0 or 180")
        displayio.release_displays()
        self._i2c = busio.I2C(scl, sda, frequency=400000)
        try:
            bus = I2CDisplayBus(self._i2c, device_address=address)
            self.display = Driver(bus, width=width, height=height, rotation=rotation,
                                  auto_refresh=False)
            group = displayio.Group()
            self._labels = []
            for y in (7, 23, 39, 55):
                label = Label(terminalio.FONT, text=" ", color=0xFFFFFF, x=0, y=y)
                self._labels.append(label)
                group.append(label)
            self.display.root_group = group
        except BaseException:
            displayio.release_displays()
            self._i2c.deinit()
            raise
        self._title = title[:21]
        self._last_stage = None
        self._updated_at = 0

    def show(self, stage, done=0, total=0, *, detail=""):
        """Render a stage, progress counters, or a two-line detail message."""
        now = time.monotonic()
        if (stage == self._last_stage and now - self._updated_at < 0.1
                and (not total or done != total)):
            return
        lines = [self._title, stage.replace("_", " ").upper()[:21], "", ""]
        if total:
            lines[2] = "%d/%d %d%%" % (done, total, min(100, done * 100 // total))
            lines[3] = detail[:21]
        elif detail:
            parts = str(detail).split("\n", 1)
            if len(parts) == 2:
                lines[2], lines[3] = parts[0][:21], parts[1][:21]
            else:
                lines[2], lines[3] = parts[0][:21], parts[0][21:42]
        for label, text in zip(self._labels, lines):
            label.text = text or " "
        self.display.refresh(minimum_frames_per_second=0)
        self._last_stage = stage
        self._updated_at = now

    def show_checks(self, checks, *, finished=False, failed=False):
        """Show a persistent POWER/CMSIS/USB checklist and its final outcome."""
        passed = all(check["state"] == "PASS" for check in checks)
        headline = "CHECKING"
        if failed:
            headline = "FAILED - POWER OFF"
        elif finished:
            headline = "SUCCESS - POWER OFF" if passed else "INCOMPLETE"
        self._labels[0].text = headline
        for label, check in zip(self._labels[1:], checks):
            text = check["name"] + " " + check["state"]
            if check.get("detail"):
                text += " " + check["detail"]
            label.text = text[:21]
        self.display.refresh(minimum_frames_per_second=0)
        self._last_stage = None
