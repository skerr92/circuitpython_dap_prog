"""BREAD Prog read-only-flash connection matrix; power is always shut down."""
import board
import digitalio
from microcontroller import pin
import supervisor
import time
from Kavrous_cmsis_dap import Programmer
from Kavrous_power import PowerControl

supervisor.runtime.autoreload = False


def levels():
    values = []
    for gpio in (pin.GPIO0, pin.GPIO1, pin.GPIO2):
        with digitalio.DigitalInOut(gpio) as io:
            io.switch_to_input(pull=None)
            values.append(io.value)
    return values


with PowerControl(board.A2, board.A1) as power:
    try:
        power.update()
        print("Before enable: A2", power.voltage, "levels DIO/CLK/RESET", levels())
        power.wait_until_ready()
        print("Enabled: A2", power.voltage, "A1", power._enable.value)
        time.sleep(1)
        print("After 1s: levels DIO/CLK/RESET", levels())
        for frequency, mode in ((1000000, "hot"), (100000, "hot"),
                                (100000, "reset"), (10000, "reset"),
                                (100000, "held-reset")):
            print("ATTEMPT", frequency, mode)
            with Programmer(pin.GPIO1, pin.GPIO0, "samd11", reset_pin=pin.GPIO2,
                            frequency=frequency, reset_hold=0.05, reset_delay=0.1) as dap:
                try:
                    if mode == "reset":
                        dap.hardware_reset()
                    elif mode == "held-reset":
                        dap._reset_pin.value = False
                        time.sleep(0.05)
                        print("Held-reset DPIDR", hex(dap.swd.connect()))
                        dap._reset_pin.value = True
                        time.sleep(0.1)
                    print("DPIDR", hex(dap.connect()))
                    print("DID", hex(dap.arm.read32(0x41002118)),
                          "NVM", hex(dap.arm.read32(0x41004008)))
                    dap.arm.reset()
                    print("PASS", frequency, mode)
                except Exception as error:
                    print("FAIL", frequency, mode, repr(error))
                finally:
                    dap._reset_pin.value = True
            power.update()
            print("A2", power.voltage, "A1", power._enable.value)
    finally:
        power.shutdown()
        print("POWER OFF A1", power._enable.value)
