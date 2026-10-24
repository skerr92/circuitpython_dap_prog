"""Compare cold-power SWD attach delays without erasing or writing flash."""
import board
import digitalio
from microcontroller import pin
import supervisor
import time
from Kavrous_cmsis_dap import Programmer
from Kavrous_power import PowerControl

supervisor.runtime.autoreload = False


def reset_level():
    with digitalio.DigitalInOut(pin.GPIO2) as reset:
        reset.switch_to_input(pull=None)
        return reset.value


with PowerControl(board.A2, board.A1) as power:
    for delay in (0.02, 0.1, 0.25, 0.5, 1.0, 0.1, 0.5, 1.0):
        power.shutdown()
        time.sleep(1)
        power.arm()
        try:
            power.wait_until_ready()
            enabled_at = time.monotonic()
            time.sleep(delay)
            print("COLD", delay, "reset level", reset_level(), "A2", power.voltage)
            with Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2,
                            frequency=1000000) as dap:
                for retry_delay in (0, 1):
                    time.sleep(retry_delay)
                    try:
                        print("PASS", delay, "retry", retry_delay,
                              "ID", hex(dap.connect()),
                              "since power", time.monotonic() - enabled_at)
                        dap.arm.reset()
                        break
                    except Exception as error:
                        print("FAIL", delay, "retry", retry_delay, repr(error))
        finally:
            power.shutdown()
            print("OFF", power._enable.value)
