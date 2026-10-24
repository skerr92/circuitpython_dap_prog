"""USB VID/PID discovery using CircuitPython's RP2040 PIO USB host.

SPDX-License-Identifier: MIT
Copyright (c) 2026 Seth Kerr
"""
import time

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/skerr92/circuitpython_dap_prog.git"


def usb_id(value):
    """Accept a 16-bit integer or a hexadecimal string such as '0x1209'."""
    if isinstance(value, str):
        value = int(value, 16)
    if type(value) is not int or not 0 <= value <= 0xFFFF:
        raise ValueError("USB IDs must be 16-bit integers or hexadecimal strings")
    return value


class USBHost:
    """Discover device IDs without opening interfaces or changing configuration.

    Construct before SWD to reserve the PIO USB resources first. CircuitPython
    owns the persistent port: it has no deinit(), and survives soft reloads.
    Reconstructing with the same pins reuses the port; different pins require
    a hardware reset. The caller owns VBUS power and must turn it off afterward.
    """

    def __init__(self, dp, dm):
        if dp == dm:
            raise ValueError("USB D+ and D- must be different pins")
        try:
            import usb_host
            import usb.core
        except ImportError:
            raise RuntimeError("This CircuitPython build needs usb_host and usb.core support")
        self._core = usb.core
        self.port = usb_host.Port(dp, dm)

    def scan(self, *, vid=None, pid=None):
        """Return currently enumerated devices as dictionaries with vid/pid."""
        vid = None if vid is None else usb_id(vid)
        pid = None if pid is None else usb_id(pid)
        devices = self._core.find(find_all=True, idVendor=vid, idProduct=pid)
        if devices is None:
            return []
        return [{"vid": device.idVendor, "pid": device.idProduct} for device in devices]

    def wait_for_device(self, *, vid=None, pid=None, timeout=5, poll_interval=0.05):
        """Return the first matching VID/PID, or None when the timeout expires."""
        if timeout < 0 or poll_interval <= 0:
            raise ValueError("Invalid USB discovery timing")
        vid = None if vid is None else usb_id(vid)
        pid = None if pid is None else usb_id(pid)
        deadline = time.monotonic() + timeout
        while True:
            devices = self.scan(vid=vid, pid=pid)
            if devices:
                return devices[0]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(poll_interval, remaining))
