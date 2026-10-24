"""Program using a definition stored on CIRCUITPY; power always ends off."""
from Kavrous_board import load_board

board = load_board("/boards/samd11_shim_usb.json")
result = board.program()
print("Programmed", result["written"], "bytes")
if result["usb"] is not None:
    print("USB %04x:%04x" % (result["usb"]["vid"], result["usb"]["pid"]))
print("Type-A power OFF")
