"""Run on BREAD to identify the connected SAMD11 without changing flash."""
from microcontroller import pin
import supervisor
from Kavrous_cmsis_dap import Programmer

supervisor.runtime.autoreload = False
with Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2,
                frequency=100000) as dap:
    print("Connecting SWCLK=GP1 SWDIO=GP0 nRESET=GP2")
    print("DPIDR %08x" % dap.connect())
    print("DSU DID %08x" % dap.arm.read32(0x41002118))
    print("NVM PARAM %08x" % dap.arm.read32(0x41004008))
    print("Flash size", dap.target.flash_size)
    print("Vector %08x %08x" % (dap.arm.read32(0), dap.arm.read32(4)))
    dap.arm.reset()
    print("Probe complete")

