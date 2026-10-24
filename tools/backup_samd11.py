"""Stream read-only backups over the REPL; capture BACKUP records on the host."""
from microcontroller import pin
import supervisor
from Kavrous_cmsis_dap import Programmer

supervisor.runtime.autoreload = False
with Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2,
                frequency=1000000) as dap:
    dap.connect()
    for name, address, size in (("flash", 0, dap.target.flash_size),
                                ("user-row", 0x00804000, 64)):
        for start in range(address, address + size, 256):
            data = bytearray()
            for offset in range(start, min(start + 256, address + size), 4):
                data.extend(dap.arm.read32(offset).to_bytes(4, "little"))
            print("BACKUP:%s:%08x:%s" % (name, start, data.hex()))
    dap.arm.reset()
    print("BACKUP COMPLETE")
