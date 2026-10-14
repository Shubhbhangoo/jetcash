#!/usr/bin/env python3
"""Fetch the locked C++ engine, apply JetCash changes, build, and test it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "engine/upstream.json").read_text())

def run(*args):
    subprocess.run([str(a) for a in args], check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=Path(os.environ.get("JETCASH_ENGINE_DIR", Path.home() / ".cache/jetcash/engine")))
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error("jobs must be 1..32")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source, build = work / "source", work / "build"
    if not source.exists():
        run("git", "clone", "--depth", "1", "--branch", PIN["tag"], PIN["repository"], source)
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != PIN["commit"]:
        raise RuntimeError("engine source does not match the locked commit")
    # Submodules are selected by the pinned parent's gitlinks.
    run("git", "-C", source, "submodule", "update", "--init", "--recursive", "--depth", "1")
    run(sys.executable, ROOT / "engine/prepare.py", source)
    run("cmake", "-S", source, "-B", build, "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTS=OFF", "-DBUILD_DOCUMENTATION=OFF",
        "-DBUILD_GUI_DEPS=OFF", "-DBUILD_SHARED_LIBS=OFF", "-DBUILD_TAG=jetcash-dev",
        "-DMANUAL_SUBMODULES=ON", "-DUSE_DEVICE_TREZOR=OFF", "-DCMAKE_POLICY_VERSION_MINIMUM=3.5")
    run("cmake", "--build", build, "--target", "daemon", "simplewallet", "wallet_rpc_server",
        "jetcash-consensus-tests", "-j", args.jobs)
    run(build / "jetcash-consensus-tests")
    notices = work / "notices"
    notices.mkdir(exist_ok=True)
    (notices / "LICENSE.monero").write_bytes((source / "LICENSE").read_bytes())
    (notices / "UPSTREAM.json").write_bytes((ROOT / "engine/upstream.json").read_bytes())
    for license_file in source.rglob("*"):
        if not license_file.is_file() or ".git" in license_file.parts:
            continue
        if license_file.name.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT")):
            destination = notices / "upstream-licenses" / license_file.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(license_file.read_bytes())
    report = {"upstream_commit": PIN["commit"], "network": "mainnet enabled; independent audit outstanding",
              "mainnet_enabled": True, "production_audited": False,
              "overlay_sha256": hashlib.sha256((ROOT / "engine/jetcash.patch").read_bytes()).hexdigest(),
              "binaries": {}}
    for name in ["jetcashd", "jetcash-wallet-cli", "jetcash-wallet-rpc"]:
        binary = build / "bin" / name
        report["binaries"][name] = {"path": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"JetCash binaries: {build / 'bin'}")
    print(f"Run private-payment integration test: python3 {ROOT / 'engine/smoke_test.py'} --build-dir {build}")

if __name__ == "__main__":
    main()
