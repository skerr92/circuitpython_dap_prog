"""Read the shim's USB ID through the example config and leave OLED result up."""
from Kavrous_board import load_board

definition = load_board("/boards/samd11_shim_usb.json")
print("Definition", definition.name)
print("OLED address", hex(definition.display["address"]))
print("USB result", definition.identify_usb())
print("Type-A power OFF")
