"""BREAD startup: check power, CMSIS/SWD and USB, then leave power off."""
import supervisor
import time
import traceback
from Kavrous_board import load_board

supervisor.runtime.autoreload = False


def status(stage, done, total):
    print("Board check:", stage, done, total)


try:
    profile = load_board("/boards/samd11_shim_usb.json")
    result = profile.check(status=status)
    print("SUCCESS: power, CMSIS/SWD and USB %04X:%04X; power OFF" %
          (result["usb"]["vid"], result["usb"]["pid"]))
except Exception as error:
    print("Board check FAILED:", error)
    traceback.print_exception(type(error), error, error.__traceback__)

# Keep the result visible; reset or run a new job explicitly to repeat.
while True:
    time.sleep(0.1)
