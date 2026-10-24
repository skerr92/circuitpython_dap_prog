"""Copy firmware.bin to CIRCUITPY, then run this script once to program a shim."""
from microcontroller import pin
import board
from Kavrous_power import PowerControl

with PowerControl(board.A2, board.A1) as power:
    written = power.program(pin.GPIO1, pin.GPIO0, "/firmware.bin", "samd11",
                            reset_pin=pin.GPIO2, frequency=1000000)
print("Programmed", written, "bytes")
print("Type-A power OFF")
