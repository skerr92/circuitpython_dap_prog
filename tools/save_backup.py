"""Decode run_board.ps1 BACKUP output: python tools/save_backup.py log directory."""
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1]).read_bytes()
text = source.decode("utf-16" if source.startswith(b"\xff\xfe") else "utf-8-sig")
if "BACKUP COMPLETE" not in text or "Traceback" in text:
    raise RuntimeError("Backup stream did not complete")
destination = pathlib.Path(sys.argv[2])
for name, base, size in (("flash", 0, 16384), ("user-row", 0x00804000, 64)):
    output = bytearray()
    for address, data in re.findall(r"BACKUP:" + name + r":([0-9a-f]+):([0-9a-f]+)", text):
        if int(address, 16) != base + len(output):
            raise RuntimeError("Missing or overlapping backup data")
        output.extend(bytes.fromhex(data))
    if len(output) != size:
        raise RuntimeError("Incomplete " + name + " backup")
    path = destination / ("samd11-before-" + name + ".bin")
    with path.open("xb") as target:
        target.write(output)
    print(path, len(output), "bytes")
