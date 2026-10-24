# CondensedContext

## Context Freshness
Last Verified Commit: cac7c0add9b06ddb1a71ce3c25b165560ff9ed47
Current HEAD: cac7c0add9b06ddb1a71ce3c25b165560ff9ed47
Status: partial (uncommitted implementation and documentation).

## Current Focus
Standalone CircuitPython SWD programming on BREAD RP2040, using PIO exclusively
for pin clocking, shifting, and bidirectional turnaround.
Added BREAD Prog power control: A2 senses external USB-C divider, A1 drives
active-high TPS22917 feeding the Type-A port.
Added JSON board definitions, optional PIO USB VID/PID discovery and I2C OLED
status. User connected a USB data cable and SSD1306 OLED on SDA GPIO8/SCL GPIO9.

## Constraints
- README covers usage and contribution/issue guidance; no validation language.
- User asked for a more human README: favor the actual setup/workflow, concise
  explanations, and practical reference; avoid repeated caveats and formal filler.
- Hardware now available: BREAD RP2040 on BREAD Prog, SWDIO GPIO0,
  SWCLK GPIO1, nRESET GPIO2; connected SAMD11 shim (DID 0x10030100).
- User explicitly requires PIO for speed; no bit-banged GPIO fallback.
- Existing README edits and empty library belong to user; preserve intended API.

## Handoff
Implemented: reusable ARM AHB-AP layer; SAMD11/SAMD21, STM32F1 low/medium density,
nRF52832/nRF52840 flash drivers; custom driver registration; streaming BIN/HEX;
preflight before erase; page erase; readback; reset; pin/state-machine cleanup.
Optional reset_pin uses digitalio open-drain active-low nRESET with target
pull-up. reset_hold/reset_delay default to 10 ms each. arm.reset() releases
halt and chooses hardware reset when wired, otherwise AIRCR. hardware_reset()
is a raw pulse usable before SWD connection. With a known target it reconnects
SWD and invokes release_reset(). Connection does not pulse reset. SAM D attach
requests halt, clears DSU STATUSA.CRSTEXT with byte access, then waits for halt.
DSU DID uses external address 0x41002118. SAMD11 shares D21 NVM sequencing but
checks family 0x1003 and limits main flash to 16 KiB; autodetection distinguishes
D11 and D21 by DID. ARMTarget.write8 handles byte lanes for DSU writes.
Reset pin is released during cleanup, initialization failures, and interrupted
pulses. SWD clocking/shifting remains entirely PIO.
Dependencies: built-in rp2pio/digitalio and bundled adafruit_pioasm. One state machine,
four PIO cycles per burst bit; interpreter adds low-clock inter-command gaps.
AP SELECT/CSW/TAR caching reduces setup overhead and handles 1 KiB TAR wrap.
Hardware result: AnyHAL samd11_shim_rgb (15,532 bytes) programmed/readback/reset
in 27.50812 s at 1 MHz burst clock. DSU 0x10120000 and DHCSR 0x03000000 after
reset; user row unchanged. Target left running RGB firmware; no visual or target
USB-console check (only BREAD COM7 enumerated).
Latest managed-power run: RGB 15,532 bytes programmed/readback/reset successfully
in 31.9079 s including qualification/startup; A1 False afterward and remained
False after update() with A2=2.315261 V. Target intentionally powered off.
Next useful step: user observes next powered job; add other requested SAMx parts.
Latest combined job loaded boards/samd11_shim_usb.json, programmed/readback
15,532 bytes, reset, matched USB 1209:0001, and shut power off. OLED final result
retained. Display address is 0x3D (scan), not default 0x3C. User confirmed text
looks correct with SSD1306 settings.
Configuration/dependencies/examples installed on BREAD. Current startup runs
profile.check(): POWER qualification, CMSIS/SWD connection/reset, and required
USB enumeration once per reset. OLED keeps three WAIT/RUN/PASS rows, then
SUCCESS - POWER OFF only after all pass and shutdown completes. Failure marks
the failed row and shows FAILED - POWER OFF. No flash writes during check().
Startup autoreload disabled; final result retained in a sleep loop, power off.
Live startup passed power, CMSIS, USB 1209:0001, and shut power off. Log:
.hardware/startup-checklist.log. Replaces earlier READY-only startup.
tools/start_board.ps1 captures six seconds by default; use -ReadSeconds 15 to
capture complete startup checks including display imports and enumeration.
PowerControl.program() rearms, qualifies USB-C (5 s timeout), waits 2 seconds for
target startup, then calls SWD program(); finally shutdown() latches off on
success/error/interruption. update() cannot reenable while inhibited; arm() or
another explicit programming call rearms. examples/bread_prog.py and the SAMD11
hardware programming script now manage power for the job and always turn it off.
Without the inhibition latch, voltage qualification works as follows:
averages 8 ADC samples, enables after >=2.2 V for 100 ms, disables <=2.0 V,
polls every 20 ms. Hysteresis preserves enabled state between thresholds.
Read errors/exit disable output. update() is cooperative; blocking application
work pauses monitoring. No PIO resources consumed by power control.

## File Map
- Kavrous_cmsis_dap.py: public program(), Programmer, SWD, ARMTarget, FlashTarget,
  target drivers and register_target().
- tests/test_programmer.py: host unittest suite; requires adafruit_pioasm.
- Kavrous_power.py: PowerControl voltage qualification, hysteresis and GPIO/ADC
  ownership. examples/bread_power.py is deployed as the BREAD startup code.py.
- tests/test_power.py: simulated ADC/time checks for qualification, dropout,
  hysteresis, read/init errors and cleanup.
- Kavrous_usb.py: USBHost wraps built-in usb_host.Port/usb.core, optional ID
  filters and bounded discovery. No interface claims or endpoint setup.
- Kavrous_board.py: version-1 JSON loader, schema/pin conflict checks before
  enabling power, managed jobs and optional USB/display stages.
- Kavrous_status.py: displayio SSD1306/SH1106 status, progress throttled to 10 Hz
  within stages; keeps final result visible; replaces previous displayio display.
- boards/samd11_shim.json: USB disabled; boards/samd11_shim_usb.json: required
  1209:0001, reset_before_scan true. Both configure current OLED 0x3D GPIO8/9.
- examples/configured_program.py and usb_identify.py: configuration-driven usage.
- tests/test_board_usb.py: schema, pin aliases, power-finally, USB filtering,
  OLED status, and PIO reservation order. SWD status callback counts committed
  image bytes and verified bytes, not padded writes or buffered bytes.
- tools/: PowerShell raw-REPL runner, SAMD11 probe/backup/program scripts,
  host backup decoder. examples/bread_prog.py is the ordinary programming sample.
- .hardware/ (ignored): original BREAD code, converted RGB binary, full target
  flash/user-row backups, backup/program logs. Preserve these local artifacts.
- README.md: wiring, dependencies, API, supported targets, driver contribution
  contract, issue reporting. No project validation section or claims.

## Validation Memory
Temporary Python 3.13.7 embedded runtime and upstream adafruit_pioasm downloaded
outside repository because installed Python aliases are unusable.
Run: python -m unittest discover -s tests -v.
Result: 64 tests passed; git diff --check passed.
Includes actual PIO assembly and an instruction model for direction/edge/bit
order, SWD protocol, AP addressing, firmware preflight, and driver sequencing.
Hardware programming, readback, reset release, and user-row preservation passed
on BREAD CircuitPython 10.3.1 / ATSAMD11D14A. No waveform measurement.
BREAD mounted D: (UID E66618810B416623), COM7; board module exposes D names,
so SWD examples use microcontroller.pin.GPIO*. Power control uses board.A1
(GPIO27) and board.A2 (GPIO28). Original Hello World code.py backed up in
.hardware/bread-original-code.py and .hardware/bread-before-power-code.py.
Current code.py runs power control; D:/lib/Kavrous_power.py is installed.
Latest startup is idle/off, replacing the earlier automatic enable loop. Raw
REPL runner waits for the prompt and retries entry across file-copy autoreload.
Cold-attach ACK 7 diagnosed: reset sampled low through 500 ms after enabling;
100 ms startup delay insufficient. Even initial ID success can precede valid
DP setup and AHB access. Delayed retries succeed; two-second cold startup passed
SWD-only/reset-pin/Programmer cases and the full managed-power programming job.
SWD.connect() now retries only idempotent debug-port setup within timeout;
target memory/flash writes are not replayed. PowerControl.program() defaults
power_delay=2.0, also used by tools/program_samd11.py. No waveform measurements
to separate load-switch/rail ramp from target reset circuitry.
GPIO16 (Type-A D+) and GPIO17 (D-) were unclaimed inputs; no USB host initialized.
Power-only cable has no target USB data path; successful full job needed no PIO USB.
User later attached a data cable. USB host now initialized on GPIO16/17 and
persists across soft reloads. No Port.deinit() exists; changing its pins/releasing
resources requires hardware reset. Reserve USB before SWD (whole PIO instruction
bank, three SMs; SWD uses other bank). CPU remained at 125 MHz; USB enumeration
and concurrent USB/SWD worked. Do not change CPU frequency while USB is active.
Cold USB enumeration initially absent; SWD halted PC 0xC4 maps to AnyHAL
runtime DefaultHandler. Target reset after host initialization allowed enumeration.
Do not infer exception cause without reading exception state. USB JSON's
reset_before_scan explicitly uses SWD connect/reset for identify_usb() only;
program() already resets after flash. No AnyHAL sources were changed.
OLED: Adafruit displayio SSD1306 and adafruit_display_text (init/label) installed
on D:/lib from upstream, not vendored in repo. SH1106 driver optional/not installed.
I2C GPIO8 SDA / GPIO9 SCL, 400 kHz, 128x64; board.I2C defaults GPIO0/1 conflict
with SWD, so use explicit config pins. OLED detected 0x3D and driver initialized.
Combined log: .hardware/configured-usb-oled-program.log; USB/display identity:
.hardware/usb-display.log. Target power off; no final reboot to preserve OLED result.
Diagnostic logs: .hardware/swd-diagnosis.log, power-timing.log,
cold-attach.log, cold-connect-trace.log, managed-program-fixed.log.
When replacing library files with autoreload off, soft reboot to reload modules;
sys.modules.pop alone did not reliably replace already-referenced objects.
adafruit_pioasm.py and library installed in D:/lib; probe, backup and program
scripts plus samd11_shim_rgb.bin staged on D:. Autoreload disabled for session.
CircuitPython print(flush=True) produced EINVAL; use plain print. CIRCUITPY is
host-owned/read-only to device, so backups stream over REPL to host; do not
disable filesystem write protection to work around this.
Power measurements: before external USB-C connection A2 ~0.089 V and enable
off; after user connected power A2 ~2.315 V and A1 high. Startup run logged
"Type-A power ON A2 2.317 V" and serial closed without interrupting it.
No direct Type-A output-voltage measurement or live unplug test performed.
Startup log: .hardware/power-startup.log. tools/start_board.ps1 restarts code.py
and leaves it running; run_board.ps1 interrupts code.py (which disables power).

## Recent Changes
- 2026-10-24: Rewrote README around setup, BREAD Prog wiring, programming and
  startup checklist. Removed repetition and stale idle-script description;
  condensed API/configuration reference. Documentation only; local links and
  git diff --check pass. No project validation claims in README. Uncommitted.
- 2026-10-24: Startup now runs POWER/CMSIS/USB checks, keeps a cumulative OLED
  checklist, and displays SUCCESS only after all pass and power off. check() is
  reusable and never writes flash. Live sequence succeeded; 4 added host checks.
  Uncommitted.
- 2026-10-24: Fixed reset/startup OLED: code.py now loads the configured display,
  shows READY - POWER OFF plus USB-C presence/A2 voltage at 2 Hz, without
  enabling power or USB host. Added create_status_display() and two-line detail.
  Uncommitted.
- 2026-10-24: Added optional USB descriptor helper, strict local JSON profiles,
  required/optional USB matching, explicit pre-scan reset, SSD1306/SH1106 OLED
  status and stage callbacks. Combined USB/OLED/SWD job succeeded with power off;
  17 additional host tests pass. Uncommitted.
- 2026-10-24: Diagnosed cold-power startup ACK 7; added bounded debug-port setup
  retry, raised managed power startup delay to 2 s, checked USB pins unclaimed,
  and completed a full RGB programming/readback/reset job with final power off.
  Added read-only diagnostic scripts and 3 host checks. Uncommitted.
- 2026-10-24: Programming completion now latches Type-A power off (also on
  error/interruption). Added managed-power program helper, idle-off startup,
  examples/docs and 3 host tests. Hardware SWD failure path confirmed A1 low.
  Uncommitted.
- 2026-10-24: Added/deployed A2/A1 TPS22917 power controller with hysteresis,
  startup qualification, averaging and fail-off cleanup. Live power-present
  transition commanded A1 high; 8 new host tests passed. Uncommitted.
- 2026-10-24: Added SAMD11 driver, reset-extension hooks/reconnection, actual
  BREAD Prog pin examples and hardware tooling. Programmed AnyHAL RGB via PIO;
  flash readback and user-row preservation passed. Uncommitted.
- 2026-10-24: Added optional reset_pin, configurable pulse/release timing,
  hardware reset routing and cleanup, reset usage docs, and six host checks.
  Uncommitted.
- 2026-10-24: Added library, PIO transport, initial target drivers, README,
  host checks, and Python cache ignores. Uncommitted; no push requested.
