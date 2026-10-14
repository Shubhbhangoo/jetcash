#!/usr/bin/env python3
"""Small launcher; cryptocurrency operations remain in the C++ executables."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get("JETCASH_ENGINE_DIR", Path.home() / ".cache/jetcash/engine"))

def run_script(name, args):
    return subprocess.call([sys.executable, str(ROOT / "engine" / name), *args])

def network_arguments(args, wallet=False):
    if any(arg.startswith("--" + name + "=") for name in ("mainnet", "testnet", "stagenet", "regtest") for arg in args):
        raise RuntimeError("Use network flags without values, for example --testnet")
    profiles = [name for name in ("mainnet", "testnet", "stagenet", "regtest") if "--" + name in args]
    if len(profiles) > 1:
        raise RuntimeError("Select only one network profile")
    profile = profiles[0] if profiles else "mainnet"
    filtered = [arg for arg in args if arg != "--mainnet" and not (wallet and arg == "--regtest")]
    return profile, filtered

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    if command in ("--help", "-h"): command = "help"
    if command in ("--version", "version"):
        print("JetCash CLI 0.2.0; pinned Monero-derived C++ engine")
        return 0
    rest = sys.argv[2:]
    if command in {"setup", "start", "stop", "restart", "doctor", "status", "peer", "wallet-create", "address", "balance", "backup", "lock", "mine", "stop-mining", "send"}:
        import manage
        return manage.main(command, rest)
    if command == "package-source": return run_script("package_source.py", rest)
    if command == "build": return run_script("build.py", rest)
    if command == "test": return run_script("smoke_test.py", rest)
    if command == "test-mainnet": return run_script("mainnet_test.py", rest)
    binaries = WORK / "build/bin"
    names = {"node": "jetcashd", "wallet": "jetcash-wallet-cli", "wallet-rpc": "jetcash-wallet-rpc"}
    if command in names:
        binary = binaries / names[command]
        if not binary.is_file():
            raise RuntimeError("Build the JetCash engine first: ./jetcash.ps1 build")
        profile, rest = network_arguments(rest, wallet=command != "node")
        if command == "node":
            bind_ip = "0.0.0.0" if profile == "mainnet" else "127.0.0.1"
            defaults = ["--p2p-bind-ip", bind_ip, "--rpc-bind-ip", "127.0.0.1", "--no-igd",
                        "--zmq-rpc-bind-ip", "127.0.0.1", "--data-dir", str(Path.home() / ".local/share/jetcash"),
                        "--check-updates", "disabled", "--disable-dns-checkpoints"]
            if profile == "regtest": defaults.append("--keep-fakechain")
        else:
            port = {"mainnet": 41081, "regtest": 41081, "testnet": 42081, "stagenet": 43081}[profile]
            defaults = ["--daemon-address", f"127.0.0.1:{port}"]
            if command == "wallet-rpc": defaults += ["--rpc-bind-ip", "127.0.0.1"]
        # Supply each default only if the caller did not specify that option.
        i = 0
        extra = []
        while i < len(defaults):
            flag = defaults[i]
            value = defaults[i+1] if i+1 < len(defaults) and not defaults[i+1].startswith("--") else None
            if not any(x == flag or x.startswith(flag + "=") for x in rest):
                extra += [flag] + ([value] if value is not None else [])
            i += 2 if value is not None else 1
        os.execv(str(binary), [str(binary), *extra, *rest])
    if command == "info":
        parser = argparse.ArgumentParser()
        parser.add_argument("--rpc-port", type=int)
        group = parser.add_mutually_exclusive_group()
        for name in ("mainnet", "testnet", "stagenet", "regtest"): group.add_argument("--" + name, action="store_true")
        args = parser.parse_args(rest)
        if args.rpc_port is None: args.rpc_port = 42081 if args.testnet else 43081 if args.stagenet else 41081
        request = urllib.request.Request(f"http://127.0.0.1:{args.rpc_port}/json_rpc",
            json.dumps({"jsonrpc": "2.0", "id": "jetcash", "method": "get_info"}).encode(),
            {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            print(json.dumps(json.load(response), indent=2))
        return 0
    if command != "help":
        print(f"Unknown command: {command}", file=sys.stderr)
        return 2
    print("JetCash — node, wallet, mining and payment CLI")
    print("  setup [--peer HOST:PORT]   Install dependencies, build, configure and start")
    print("  start | stop | restart    Manage the background node")
    print("  status | doctor           Show live health and peer connections")
    print("  peer add|remove|list      Save peers and apply changes automatically")
    print("  wallet-create | address | balance | backup | lock")
    print("  mine [--threads 1] | stop-mining")
    print("  send ADDRESS AMOUNT       Send JET using mandatory private transactions")
    print("  package-source            Build a source-only release archive")
    print("Use --network mainnet|testnet|stagenet|regtest and --name WALLET where applicable.")
    print("Advanced: build | test | test-mainnet | node | wallet | wallet-rpc | info")
    print("Linux: python3 jetcash setup   Windows/WSL: .\\jetcash.ps1 setup")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"JetCash: {error}", file=sys.stderr)
        sys.exit(1)
