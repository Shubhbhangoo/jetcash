#!/usr/bin/env python3
"""Package only explicitly selected source files; exclude runtime state and keys."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ["LICENSE", "NOTICE", "README.md", "CONTRIBUTING.md", "CMakeLists.txt",
         ".gitignore", ".gitattributes", "jetcash", "jetcash.ps1"]
PATTERNS = ["include/jetcash/*.hpp", "src/*.cpp", "tests/*.cpp", "engine/*.py", "engine/*.cpp",
            "engine/upstream.json", "engine/jetcash.patch", "engine/LICENSE.monero",
            "network/*.json", "scripts/*.ps1", "docs/*.md", ".github/workflows/*.yml"]

def source_files():
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing: raise RuntimeError("Source package is missing required files: " + ", ".join(missing))
    paths = {ROOT / name for name in FILES}
    for pattern in PATTERNS: paths.update(ROOT.glob(pattern))
    for path in sorted(paths):
        if path.is_symlink(): raise RuntimeError(f"Refusing source symlink: {path}")
        if path.is_file(): yield path

def package(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    checksums = {}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_files():
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            checksums[name] = hashlib.sha256(data).hexdigest()
            entry = zipfile.ZipInfo("jetcash/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.external_attr = ((0o100755 if name == "jetcash" else 0o100644) << 16)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
        archive.writestr("jetcash/SOURCE-MANIFEST.json", json.dumps(checksums, sort_keys=True, indent=2) + "\n")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name + ".sha256").write_text(digest + "  " + output.name + "\n")
    return len(checksums), digest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist/jetcash-source.zip")
    args = parser.parse_args()
    count, digest = package(args.output.resolve())
    print(f"Source files: {count}\nArchive: {args.output.resolve()}\nSHA256: {digest}")

if __name__ == "__main__": main()
