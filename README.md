# circuitpython_dap_prog

A CircuitPython library for programming ARM Cortex-M boards from a BREAD RP2040.
Put the firmware on `CIRCUITPY`, connect SWD, and program the target from Python.
PIO handles the SWD clock and data transfers.

On BREAD Prog, the library also controls target power, reads USB VID/PID, and
shows progress on a 128x64 OLED. It runs on the programmer itself; the USB port
connected to your computer isn't a CMSIS-DAP probe interface.

## Setup

Use CircuitPython with `rp2pio` support. USB identification also needs the
built-in `usb_host` and `usb.core` modules.

1. Copy the `Kavrous_*.py` files into `/lib` on `CIRCUITPY`.
2. From the [Adafruit library bundle](https://circuitpython.org/libraries), add
   `adafruit_pioasm.mpy`. For the OLED, also add `adafruit_displayio_ssd1306.mpy`
   and the `adafruit_display_text` directory.
3. Copy the `boards` directory onto the drive.
4. Copy your firmware onto the drive and set `firmware` in the board's JSON file
   to its path, such as `/firmware.bin`.

The example profiles use this BREAD Prog wiring:

| BREAD pin | Connection |
| --- | --- |
| GPIO0 | Target SWDIO |
| GPIO1 | Target SWCLK |
| GPIO2 | Target nRESET / NRST |
| GPIO8 | OLED SDA |
| GPIO9 | OLED SCL |
| GPIO16 | Type-A USB D+ |
| GPIO17 | Type-A USB D- |
| A1 | TPS22917 power enable |
| A2 | USB-C power-input voltage divider |

Connect target and programmer grounds. SWD signals must be 3.3 V compatible;
RP2040 GPIO isn't 5 V tolerant. Reset is driven low with an open-drain output,
so the target needs a reset pull-up. Some chips also need their reset-pin
function enabled in the device configuration.

The OLED profiles use an SSD1306 at **0x3D**. Change the address for your module.
BREAD's default `board.I2C()` uses GPIO0/1, so the display uses explicit GPIO8/9
assignments to keep it separate from SWD.

## Program a board

Choose a profile:

- [samd11_shim.json](boards/samd11_shim.json) programs over SWD with a power-only
  USB cable to the target.
- [samd11_shim_usb.json](boards/samd11_shim_usb.json) also reads USB VID/PID after
  programming. Use a USB data cable for this one.

```python
from Kavrous_board import load_board

profile = load_board("/boards/samd11_shim_usb.json")
result = profile.program()
print("Programmed", result["written"], "bytes")
print("USB", result["usb"])
```

This turns on target power, writes the image, compares flash readback, resets
the target, and reads its USB identity if enabled. Power turns off when the job
finishes, including on an error or interruption. The OLED shows the current
step and progress, then keeps the result on screen.

**Erasing affects whole pages or rows.** Bytes outside the image but inside a
touched page are erased too, including any bootloader in that space. Gaps in
those pages are left as `0xFF`.

To use another image or binary load address:

```python
result = profile.program("/application.bin", address=0x00001000)
```

See [configured_program.py](examples/configured_program.py) for the full
profile-based example, or [bread_prog.py](examples/bread_prog.py) for a small
example with pins supplied directly.

## Startup checklist

Copy [examples/bread_power.py](examples/bread_power.py) to `code.py` to run the
power, CMSIS/SWD, and USB checks once after reset. It uses
`/boards/samd11_shim_usb.json` and leaves the target's existing firmware in place.

Each OLED row changes from `WAIT` to `RUN` to `PASS`. When all three pass and
power has been shut off, the screen looks like this:

```text
SUCCESS - POWER OFF
POWER PASS 2.32V
CMSIS PASS
USB PASS 1209:0001
```

A failed step gets `FAIL`, and the heading becomes `FAILED - POWER OFF`.
The serial console has the full error. Reset to try again; this startup script
disables file-copy autoreload so copying a file won't start another check.

You can also run the sequence yourself:

```python
result = profile.check()
```

`check()` requires all three steps to pass. To read only the USB identity of the
existing firmware, use `profile.identify_usb()` instead.

## Board profiles

Edit one of the JSON examples for each target board. The main settings are:

| Section | Settings |
| --- | --- |
| Root | `version: 1`, board `name`, flash-driver `target`, and `firmware` path |
| `swd` | `swclk`, `swdio`, `reset`, `frequency`, `timeout` |
| `power` | `sense`, `enable`, voltage thresholds, `settle_time`, `power_timeout`, `startup_delay` |
| `usb` | `enabled`, `dp`, `dm`, expected `vid`/`pid`, `timeout`, `required`, `reset_before_scan` |
| `display` | `enabled`, `controller`, `sda`, `scl`, `address`, dimensions, `rotation` |

`GPIO` names refer to physical RP2040 pins. Names such as `A2` come from the
programmer's `board` module. Relative firmware paths start from the JSON file's
directory; paths beginning with `/` start at the drive root.

The USB example expects `1209:0001`, the IDs used by the AnyHAL SAMD11 example
firmware. Replace them with your firmware's IDs. Set `usb.enabled` to `false`
for a power-only connection. With USB enabled, `required: false` lets a
programming job finish with `usb: None` if no matching device appears. With
`required: true`, a missing device fails the job. At that point the new firmware
has already been written.

`reset_before_scan` makes `identify_usb()` connect over SWD and reset the target
before looking for USB. The SAMD11 USB profile enables it. A programming job
already resets the target before enumeration.

For a different OLED, change its address or select `controller: "sh1106"` and
install `adafruit_displayio_sh1106.mpy`. The status screen uses 128x64 pixels
with rotation `0` or `180`. Set `display.enabled` to `false` to leave it out.

## Supported targets and files

| Target name | Main flash supported |
| --- | --- |
| `samd11` | SAMD11, up to 16 KiB; 256-byte erase rows |
| `samd21` | SAMD21 with 64-byte pages; 256-byte erase rows |
| `stm32f1`, `stm32f103` | Low/medium-density STM32F1, IDs 0x410/0x412, up to 128 KiB; 1 KiB erase pages |
| `nrf52` | nRF52832 and nRF52840; 4 KiB erase pages |
| `nrf52832`, `nrf52840` | The named nRF52 part |

Other parts need a flash driver for their controller. Option bytes, fuses,
UICR, and security settings are left alone. Unlock protected devices separately.

Binary images default to address `0x00000000` on SAMD and nRF52, or
`0x08000000` on STM32F1. Intel HEX files (`.hex` or `.ihex`) carry their own
addresses; records must be in ascending order without overlaps. Extended
segment and linear addresses are supported. Start-address records are ignored.

Convert ELF or UF2 files before using them. Other extensions are treated as
binary. Keep the file unchanged while programming; it is read from storage in
small chunks rather than loaded into RAM all at once.

## Using the SWD library directly

For a separately powered target, pass the pins and image straight to `program()`:

```python
from microcontroller import pin
from Kavrous_cmsis_dap import program

written = program(pin.GPIO1, pin.GPIO0, "/firmware.bin",
                  target="samd11", reset_pin=pin.GPIO2)
```

Omit `target` to try automatic identification among the supported drivers.
Without `reset_pin`, reset uses the Cortex-M system reset register.

| Option | Default | Purpose |
| --- | --- | --- |
| `address` | Target flash base | Binary load address; omit for HEX |
| `verify`, `reset` | `True`, `True` | Read back the image, then reset the target |
| `frequency` | `1000000` | SWCLK burst rate in Hz; accepts 1 kHz–10 MHz |
| `timeout`, `retries` | `2`, `100` | Connection/transfer timeout in seconds and SWD WAIT attempts |
| `reset_hold`, `reset_delay` | `0.01`, `0.01` | Seconds to hold reset low and wait after release |
| `progress` | `None` | Callback receiving `(processed_bytes, total_bytes)` |
| `status` | `None` | Callback receiving `(stage, done, total)` |

PIO clocks the transfers; Python adds gaps between bursts, so `frequency`
isn't the overall programming speed. Lower it for a slower debug port or
longer wires. The `progress` count includes buffered data; use a successful
return from `program()` as the completion signal.

For a reusable connection, use `Programmer` as a context manager. Its `arm`
object provides memory access and core control; `deinit()` releases the pins.
`DAPError` covers SWD, flash-controller, and readback errors. Bad arguments or
images raise `ValueError`, and file errors raise `OSError`.

## Power and USB helpers

`PowerControl` uses A2's divider reading to qualify the separate USB-C supply
and drives the TPS22917 through A1. Defaults are 2.2 V for 100 ms to enable,
2.0 V to disable, and a two-second target startup delay before programming.
The voltage is measured at A2, after the divider.

Use `power.program(...)` to wrap a direct SWD programming call with power
control. `shutdown()` holds the output off until `arm()` or another explicit
programming job. Call `update()` when using the voltage monitor in your own
loop; it doesn't run in the background.

For USB discovery without a board profile, create
`USBHost(pin.GPIO16, pin.GPIO17)` from `Kavrous_usb`. `scan()` lists enumerated
VID/PID pairs; `wait_for_device(vid=..., pid=..., timeout=5)` waits for a match.
IDs accept integers or hexadecimal strings. The caller supplies target power.

Create the USB host before allocating SWD state machines. CircuitPython's PIO
USB port persists across soft reloads and has no `deinit()`. Reuse the same
pins, or perform a hardware reset to change them or release its resources.

## Contributing

Keep changes compatible with CircuitPython and small enough for the RP2040.
USB and display imports should stay optional, and firmware processing should
stay bounded in memory.

To add a target, subclass `FlashTarget` and register it with `register_target()`.
Include the exact part names, device-ID checks, flash geometry, and a reference
manual link. Implement the probe, erase, and write routines with bounded busy
waits and controller-error handling. Use `attach()` and `release_reset()` when
the part needs a special debug-entry sequence.

## Reporting issues

Include the BREAD revision, CircuitPython version, target part number, wiring,
board profile, firmware format/load address, and full traceback. Say what you
expected and what happened. A small HEX file that reproduces a parsing problem
is useful; leave proprietary firmware out of the report.

## License

MIT. See [LICENSE](LICENSE).
