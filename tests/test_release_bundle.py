"""Release archive contents, version stamping, and failure handling."""
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_builder", ROOT / "tools/build_release.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)

    def test_source_bundle_has_all_modules_profiles_and_no_bench_files(self):
        bundle = builder.build_bundle(ROOT, self.output, "source", "1.2.3")
        with zipfile.ZipFile(bundle) as archive:
            modules = {"lib/" + name for name in builder.manifest(ROOT)["bundle"]["modules"]}
            self.assertEqual({name for name in archive.namelist() if name.startswith("lib/")}, modules)
            for module in modules:
                self.assertIn(b'__version__ = "1.2.3"', archive.read(module))
                self.assertNotIn(b'0.0.0+auto.0', archive.read(module))
            for path in ("boards/samd11_shim.json", "boards/samd11_shim_usb.json"):
                profile = json.loads(archive.read(path))
                self.assertEqual(profile["firmware"], "/firmware.bin")
            self.assertIn("examples/configured_program.py", archive.namelist())
            self.assertFalse(any(name.startswith(("tools/", ".hardware/", "tests/"))
                                 or name.endswith((".bin", ".elf")) for name in archive.namelist()))
            self.assertEqual(json.loads(archive.read("bundle.json"))["version"], "1.2.3")
            for link in re.findall(r"\]\(([^)]+)\)", archive.read("README.md").decode("utf-8")):
                if not link.startswith(("https://", "http://", "#")):
                    self.assertIn(link.split("#", 1)[0], archive.namelist())

    def test_source_archives_are_reproducible(self):
        first = builder.build_bundle(ROOT, self.output, "source", "1.2.3").read_bytes()
        second = builder.build_bundle(ROOT, self.output, "source", "1.2.3").read_bytes()
        self.assertEqual(first, second)

    def test_mpy_bundle_keeps_examples_as_python(self):
        def compiler(command, **kwargs):
            output = Path(command[command.index("-o") + 1])
            output.write_bytes(b"C\x06\x00\x1fcompiled")
        with patch.object(builder.subprocess, "run", side_effect=compiler), \
             patch.object(builder, "git_commit", return_value="12345678"):
            bundle = builder.build_bundle(ROOT, self.output, "10.x", "1.2.3", "compiler")
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(len([name for name in archive.namelist() if name.endswith(".mpy")]), 5)
            self.assertFalse(any(name.endswith(".py") for name in archive.namelist() if name.startswith("lib/")))
            self.assertIn("examples/bread_power.py", archive.namelist())
            self.assertEqual(json.loads(archive.read("bundle.json"))["compiler"], "10.3.1")

    def test_failed_compile_preserves_previous_release(self):
        destination = self.output / "circuitpython-dap-prog-10.x-mpy-1.2.3.zip"
        destination.write_bytes(b"previous release")
        with patch.object(builder.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "compiler")):
            with self.assertRaises(subprocess.CalledProcessError):
                builder.build_bundle(ROOT, self.output, "10.x", "1.2.3", "compiler")
        self.assertEqual(destination.read_bytes(), b"previous release")
        self.assertEqual(list(self.output.iterdir()), [destination])

    def test_invalid_versions_cannot_escape_output_directory(self):
        with self.assertRaises(ValueError):
            builder.build_bundle(ROOT, self.output, "source", "../../outside")


if __name__ == "__main__":
    unittest.main()
