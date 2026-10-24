"""Run on BREAD Prog after backing up the target with backup_samd11.py."""
from microcontroller import pin
import board
import supervisor
import time
from Kavrous_cmsis_dap import Programmer
from Kavrous_power import PowerControl

supervisor.runtime.autoreload = False


def user_row(arm):
    return [arm.read32(address) for address in range(0x00804000, 0x00804040, 4)]


def progress(done, total):
    if done % 2048 == 0 or done == total:
        print("Image bytes", done, "/", total)


with PowerControl(board.A2, board.A1) as power:
    try:
        power.wait_until_ready()
        time.sleep(2)
        with Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2,
                        frequency=1000000) as dap:
            print("DPIDR", hex(dap.connect()))
            print("DID", hex(dap.arm.read32(0x41002118)))
            before = user_row(dap.arm)
            started = time.monotonic()
            count = dap.program("/samd11_shim_rgb.bin", progress=progress)
            print("PROGRAM COMPLETE", count, "bytes; elapsed", time.monotonic() - started)
            print("DSU after reset", hex(dap.arm.read32(0x41002100)))
            print("DHCSR after reset", hex(dap.arm.read32(0xE000EDF0)))
            if before != user_row(dap.arm):
                raise RuntimeError("User row changed")
            print("User row unchanged")
    finally:
        power.shutdown()
        print("Type-A power OFF; A1", power._enable.value)
