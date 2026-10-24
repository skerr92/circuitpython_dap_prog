"""Build source/MPY bundles using Adafruit's mpy-cross downloader.

The explicit release.toml manifest keeps local board files, firmware, backups,
and bench scripts out of downloadable releases. Requires host Python 3.11+.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = '"0.0.0+auto.0"'


def manifest(root):
    with (root / "release.toml").open("rb") as source:
        data = tomllib.load(source)
    bundle = data["bundle"]
    if not re.fullmatch(r"[a-z0-9-]+", bundle["prefix"]):
        raise ValueError("Invalid bundle prefix")
    with (root / "pyproject.toml").open("rb") as source:
        metadata = tomllib.load(source)
    declared = {name + ".py" for name in metadata["tool"]["setuptools"]["py-modules"]}
    if set(bundle["modules"]) != declared:
        raise ValueError("release.toml must include every pyproject module")
    for section in ("modules", "examples", "profiles", "documents"):
        for name in bundle[section]:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or name.startswith("."):
                raise ValueError("Unsafe manifest path: " + name)
            if not (root / path).is_file():
                raise ValueError("Missing release file: " + name)
    return data


def git_commit(root):
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def development_version(root):
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    commit = git_commit(root)
    return "0.0.0.dev" + date + ("+g" + commit[:8] if commit else "")


def stamped(source, version):
    if PLACEHOLDER not in source:
        raise ValueError("Module is missing its release version placeholder")
    return source.replace(PLACEHOLDER, json.dumps(version))


def add_file(archive, name, data):
    # Fixed metadata makes identical source/versions produce identical archives.
    info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def build_bundle(root, output, target, version, compiler=None):
    config = manifest(root)
    bundle = config["bundle"]
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+-]*", version):
        raise ValueError("Version must be a filename-safe release version")
    compiler_version = None
    if target != "source":
        compiler_version = config["circuitpython"][target]
        if compiler is None:
            from circuitpython_build_tools.build import mpy_cross
            compiler = mpy_cross({"tag": compiler_version, "name": target})
    output.mkdir(parents=True, exist_ok=True)
    kind = "py" if target == "source" else target + "-mpy"
    destination = output / (bundle["prefix"] + "-" + kind + "-" + version + ".zip")
    with tempfile.TemporaryDirectory(prefix="dap-bundle-", dir=output) as temporary:
        temporary = Path(temporary)
        staged_zip = temporary / destination.name
        with zipfile.ZipFile(staged_zip, "w") as archive:
            for name in bundle["modules"]:
                source = stamped((root / name).read_text(encoding="utf-8"), version)
                filename = Path(name).name
                if target == "source":
                    add_file(archive, "lib/" + filename, source.encode("utf-8"))
                else:
                    input_file = temporary / filename
                    input_file.write_text(source, encoding="utf-8")
                    compiled = input_file.with_suffix(".mpy")
                    subprocess.run([str(compiler), "-s", filename, "-o", str(compiled),
                                    str(input_file)], check=True)
                    data = compiled.read_bytes()
                    if len(data) < 4 or not data.startswith(b"C"):
                        raise ValueError("Compiler did not produce a CircuitPython MPY file: " + filename)
                    add_file(archive, "lib/" + compiled.name, data)
            for name in bundle["examples"] + bundle["documents"]:
                add_file(archive, name, (root / name).read_bytes())
            for name in bundle["profiles"]:
                data = (root / name).read_bytes()
                add_file(archive, name, data)
                add_file(archive, "boards/" + Path(name).name, data)
            details = {"version": version, "commit": git_commit(root), "target": target,
                       "compiler": compiler_version, "modules": bundle["modules"]}
            add_file(archive, "bundle.json", json.dumps(details, indent=2).encode("utf-8"))
        staged_zip.replace(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("matrix")
    build = subcommands.add_parser("build")
    build.add_argument("--target", default="source")
    build.add_argument("--version")
    build.add_argument("--output", type=Path, default=ROOT / "bundles")
    build.add_argument("--mpy-cross", type=Path)
    args = parser.parse_args()
    config = manifest(ROOT)
    if args.command == "matrix":
        print(json.dumps(list(config["circuitpython"])))
    else:
        if args.target not in ("source", *config["circuitpython"]):
            parser.error("Unknown CircuitPython target: " + args.target)
        version = args.version or development_version(ROOT)
        print(build_bundle(ROOT, args.output, args.target, version, args.mpy_cross))


if __name__ == "__main__":
    main()
