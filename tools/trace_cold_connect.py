"""Trace the initial DP registers and inspect unused Type-A data pins."""
import board
import digitalio
from microcontroller import pin
import supervisor
import time
import Kavrous_cmsis_dap as library
from Kavrous_power import PowerControl

supervisor.runtime.autoreload = False
print("Library version", library.__version__)
for usb_pin in (pin.GPIO16, pin.GPIO17):
    try:
        with digitalio.DigitalInOut(usb_pin) as io:
            print("USB pin unclaimed", usb_pin, "direction", io.direction)
    except Exception as error:
        print("USB pin claimed", usb_pin, repr(error))

with PowerControl(board.A2, board.A1) as power:
    try:
        power.wait_until_ready()
        time.sleep(0.1)
        with library.Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2) as dap:
            original_read = dap.swd.read_dp
            original_write = dap.swd.write_dp

            def read(address):
                print("DP READ", hex(address))
                result = original_read(address)
                print("DP RESULT", hex(result))
                return result

            def write(address, value):
                print("DP WRITE", hex(address), hex(value))
                original_write(address, value)
                print("DP WRITE OK")

            dap.swd.read_dp = read
            dap.swd.write_dp = write
            try:
                print("CONNECTED", hex(dap.connect()))
                print("DID", hex(dap.arm.read32(0x41002118)))
            except Exception as error:
                import traceback
                traceback.print_exception(type(error), error, error.__traceback__)
    finally:
        power.shutdown()
        print("POWER OFF", power._enable.value)
