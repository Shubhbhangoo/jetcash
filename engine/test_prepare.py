#!/usr/bin/env python3
"""Check patch reproducibility and protection against overwriting local source edits."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(os.environ.get("JETCASH_ENGINE_DIR", Path.home() / ".cache/jetcash/engine")) / "source")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="jetcash-overlay-", dir=args.source.parent) as directory:
        checkout = Path(directory) / "source"
        subprocess.run(["git", "clone", "--quiet", "--shared", str(args.source), str(checkout)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(checkout), "apply", "--check", str(ROOT / "engine/jetcash.patch")], check=True)
        prepare = [sys.executable, str(ROOT / "engine/prepare.py"), str(checkout)]
        subprocess.run(prepare, check=True, stdout=subprocess.DEVNULL)
        edited = checkout / "src/cryptonote_core/blockchain.cpp"
        first = edited.read_bytes()
        timestamp = edited.stat().st_mtime_ns
        subprocess.run(prepare, check=True, stdout=subprocess.DEVNULL)
        assert edited.read_bytes() == first and edited.stat().st_mtime_ns == timestamp
        edited.write_bytes(first + b"\n// User-owned local edit\n")
        modified = edited.read_bytes()
        rejected = subprocess.run(prepare, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert rejected.returncode != 0 and b"unrecognized local edits" in rejected.stderr
        assert edited.read_bytes() == modified, "local edit must survive failed preparation"
        subprocess.run(["git", "-C", str(checkout), "-c", "user.name=JetCash overlay test", "-c",
                        "user.email=overlay-test@example.invalid", "commit", "--allow-empty", "-m", "test wrong revision"],
                       check=True, stdout=subprocess.DEVNULL)
        rejected = subprocess.run(prepare, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert rejected.returncode != 0 and b"different upstream revision" in rejected.stderr
    print("Patch replay, idempotence, local edit protection, and revision lock passed")

if __name__ == "__main__":
    main()
