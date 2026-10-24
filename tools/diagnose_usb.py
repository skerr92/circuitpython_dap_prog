"""Inspect USB enumeration and SAMD11 runtime state without changing flash."""
import board
from microcontroller import pin
import supervisor
import time
from Kavrous_usb import USBHost
from Kavrous_cmsis_dap import Programmer
from Kavrous_power import PowerControl

supervisor.runtime.autoreload = False
with PowerControl(board.A2, board.A1) as power:
    try:
        host = USBHost(pin.GPIO16, pin.GPIO17)
        power.wait_until_ready()
        time.sleep(2)
        for _ in range(6):
            print("USB scan", host.scan())
            time.sleep(0.5)
        with Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2) as dap:
            print("SWD with USB host", hex(dap.swd.connect()))
            print("DHCSR", hex(dap.arm.read32(0xE000EDF0)))
            print("DSU", hex(dap.arm.read32(0x41002100)))
            print("USB CTRLA", hex(dap.arm.read32(0x41005000)))
            print("USB CTRLB", hex(dap.arm.read32(0x41005008)))
            dap.connect()
            dap.arm.write32(0xE000EDF4, 15)
            dap.arm.wait(0xE000EDF0, 0x10000, 0x10000)
            print("Halted PC", hex(dap.arm.read32(0xE000EDF8)))
            dap.arm.reset()
        for _ in range(6):
            print("USB after reset", host.scan())
            time.sleep(0.5)
    finally:
        power.shutdown()
        print("POWER OFF", power._enable.value)
