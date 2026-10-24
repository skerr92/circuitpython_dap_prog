"""Program the existing SAMD11 RGB image through the managed-power API."""
import board
from microcontroller import pin
import supervisor
import time
from Kavrous_power import PowerControl

supervisor.runtime.autoreload = False


def progress(done, total):
    if done % 2048 == 0 or done == total:
        print("Image bytes", done, "/", total)


with PowerControl(board.A2, board.A1) as power:
    started = time.monotonic()
    try:
        count = power.program(pin.GPIO1, pin.GPIO0, "/samd11_shim_rgb.bin", "samd11",
                              reset_pin=pin.GPIO2, progress=progress)
        print("PROGRAM COMPLETE", count, "bytes; elapsed", time.monotonic() - started)
        print("A2", power.voltage, "A1", power._enable.value,
              "inhibited", power._inhibited)
        time.sleep(0.2)
        power.update()
        print("After update: A1", power._enable.value, "enabled", power.enabled)
    finally:
        power.shutdown()
        print("POWER OFF A1", power._enable.value)
