"""Separate target power settling from reset-pin initialization and SWD attach."""
import board
import digitalio
from microcontroller import pin
import supervisor
import time
from Kavrous_cmsis_dap import SWD, ARMTarget, Programmer
from Kavrous_power import PowerControl

supervisor.runtime.autoreload = False
with PowerControl(board.A2, board.A1) as power:
    for mode in ("swd-only", "reset-pin", "programmer", "programmer-wait"):
        power.shutdown()
        time.sleep(1)
        power.arm()
        try:
            power.wait_until_ready()
            time.sleep(2)
            print("CASE", mode)
            reset = None
            dap = None
            swd = None
            try:
                if mode.startswith("programmer"):
                    dap = Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2)
                    swd = dap.swd
                    print("Reset immediately after Programmer init", dap._reset_pin.value)
                    if mode.endswith("wait"):
                        time.sleep(1)
                        print("Reset after 1s", dap._reset_pin.value)
                else:
                    if mode == "reset-pin":
                        reset = digitalio.DigitalInOut(pin.GPIO2)
                        reset.switch_to_output(value=True, drive_mode=digitalio.DriveMode.OPEN_DRAIN)
                        print("Reset after open drain init", reset.value)
                    swd = SWD(pin.GPIO1, pin.GPIO0)
                for retry in range(2):
                    try:
                        print("DPIDR", hex(swd.connect()), "retry", retry)
                        break
                    except Exception as error:
                        print("FAIL", retry, repr(error))
                        time.sleep(1)
            finally:
                if dap is not None:
                    dap.deinit()
                elif swd is not None:
                    swd.deinit()
                if reset is not None:
                    reset.deinit()
        finally:
            power.shutdown()
            print("OFF", power._enable.value)
