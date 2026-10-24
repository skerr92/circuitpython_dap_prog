from microcontroller import pin
import busio
import time

print("SCL", pin.GPIO9, "SDA", pin.GPIO8)
bus = busio.I2C(pin.GPIO9, pin.GPIO8)
deadline = time.monotonic() + 2
while not bus.try_lock():
    if time.monotonic() >= deadline:
        raise RuntimeError("I2C bus busy")
try:
    print("I2C addresses", [hex(address) for address in bus.scan()])
finally:
    bus.unlock()
    bus.deinit()
