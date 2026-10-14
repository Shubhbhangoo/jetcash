#!/usr/bin/env python3
"""Exercise the managed CLI with temporary data, authenticated RPC and real transfers."""
import contextlib
import io
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from unittest.mock import patch
import manage

def free_base():
    for _ in range(200):
        base = 20000 + secrets.randbelow(35000)
        try:
            with contextlib.ExitStack() as stack:
                for offset in range(4):
                    sock = stack.enter_context(socket.socket())
                    sock.bind(("127.0.0.1", base + offset))
                return base
        except OSError: pass
    raise RuntimeError("No test port group available")

def main():
    with tempfile.TemporaryDirectory(prefix="jetcash-cli-check-") as directory:
        root = Path(directory)
        first_base, second_base = free_base(), free_base()
        while abs(first_base - second_base) < 4: second_base = free_base()
        first_env = {"JETCASH_HOME": str(root / "alice-node"), "JETCASH_PORT_BASE": str(first_base)}
        second_env = {"JETCASH_HOME": str(root / "peer-node"), "JETCASH_PORT_BASE": str(second_base)}
        with patch.dict(os.environ, first_env): first = manage.Manager("regtest")
        with patch.dict(os.environ, second_env): second = manage.Manager("regtest")
        try:
            print("Checking CLI start and peer synchronization...", flush=True)
            # Start through the actual command entry point; return before the node exits.
            subprocess.run([sys.executable, str(manage.ROOT / "jetcash"), "start", "--network", "regtest"],
                           env={**os.environ, **first_env}, check=True)
            second.config["peers"] = [f"127.0.0.1:{first_base}"]
            second.save()
            second.start()
            manage.wait_until(lambda: first.node_info()["synchronized"])
            print("Checking encrypted wallet creation and authenticated RPC...", flush=True)
            # Recovery phrases stay captured in memory; never add them to test reports.
            with patch.object(manage.getpass, "getpass", return_value="throwaway-cli-test-password"), contextlib.redirect_stdout(io.StringIO()):
                alice = first.create_wallet("alice")
            try:
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{first.wport}/json_rpc",
                    b'{"jsonrpc":"2.0","id":"unauthorized","method":"get_version"}',
                    {"Content-Type": "application/json"}), timeout=5)
            except urllib.error.HTTPError as error: assert error.code == 401
            else: raise AssertionError("Wallet RPC allowed an unauthenticated request")
            assert (first.control / "wallet-rpc.conf").stat().st_mode & 0o777 == 0o600
            assert (first.control / "wallet-rpc-credentials.json").stat().st_mode & 0o777 == 0o600
            first.daemon("generateblocks", {"wallet_address": alice, "amount_of_blocks": 85})
            first.wallet_rpc("refresh")
            assert first.wallet_rpc("get_balance")["unlocked_balance"] >= 100000000
            with patch.object(manage.getpass, "getpass", return_value="throwaway-cli-test-password"), contextlib.redirect_stdout(io.StringIO()):
                bob = first.create_wallet("bob")
                first.open_wallet("alice")
            print("Checking private send, balance, wallet lock/reopen and clean stop...", flush=True)
            with patch.dict(os.environ, first_env):
                with contextlib.redirect_stdout(io.StringIO()): manage.main("send", [bob, "1", "--name", "alice", "--network", "regtest"])
            first.daemon("generateblocks", {"wallet_address": alice, "amount_of_blocks": 12})
            with patch.object(manage.getpass, "getpass", return_value="throwaway-cli-test-password"), contextlib.redirect_stdout(io.StringIO()):
                first.open_wallet("bob")
            output = subprocess.check_output([sys.executable, str(manage.ROOT / "jetcash"), "balance", "--name", "bob",
                                              "--network", "regtest"], env={**os.environ, **first_env}, text=True)
            assert "Balance: 1.00000000 JET" in output
            with patch.dict(os.environ, first_env), patch.object(manage.getpass, "getpass", return_value="throwaway-cli-test-password"), contextlib.redirect_stdout(io.StringIO()):
                manage.main("mine", ["--threads", "1", "--name", "alice", "--network", "regtest"])
                assert first.daemon("mining_status", plain=True)["active"]
                manage.main("stop-mining", ["--network", "regtest"])
                assert not first.daemon("mining_status", plain=True)["active"]
                first.open_wallet("bob")
            first.stop_wallet_service()
            assert not manage.port_busy(first.wport)
            with patch.object(manage.getpass, "getpass", return_value="throwaway-cli-test-password"), contextlib.redirect_stdout(io.StringIO()):
                first.open_wallet("bob")
            first.wallet_rpc("refresh")
            assert first.wallet_rpc("get_balance")["balance"] == 100000000
            expected_height = first.node_info()["height"]
            first.stop()
            assert not manage.port_busy(first.rport) and not manage.port_busy(first.wport)
            first.start()
            assert first.node_info()["height"] == expected_height
            report = {"passed": True, "temporary_regression_chain": True, "background_cli_start": True,
                "wallet_rpc_authentication_required": True, "private_credential_permissions": True,
                "encrypted_wallet_create_and_reopen": True, "private_cli_send": True,
                "cli_cpu_mining_start_and_stop": True,
                "recipient_balance_atomic": 100000000, "clean_stop_and_restart": True}
            target = manage.ROOT / "artifacts/cli-test.json"
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
        finally:
            for manager in (first, second):
                try: manager.stop()
                except RuntimeError as error:
                    print(f"Test cleanup: {error}", file=sys.stderr)
                    # Only terminate children whose /proc command identifies this
                    # test's temporary data directory and the expected engine.
                    for name in ("wallet-rpc", "node"):
                        pidfile = manager.control / (name + ".pid")
                        if not pidfile.exists(): continue
                        pid = int(pidfile.read_text())
                        proc = Path(f"/proc/{pid}/cmdline")
                        if proc.exists():
                            command = proc.read_bytes().decode(errors="replace")
                            if str(manager.home) in command and str(manager.binaries) in command:
                                os.kill(pid, signal.SIGTERM)

if __name__ == "__main__": main()
