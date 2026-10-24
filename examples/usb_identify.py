"""Read existing firmware's USB VID/PID without flashing the target."""
from Kavrous_board import load_board

board = load_board("/boards/samd11_shim_usb.json")
device = board.identify_usb()
if device is None:
    print("No matching USB device found")
else:
    print("USB %04x:%04x" % (device["vid"], device["pid"]))
print("Type-A power OFF")
