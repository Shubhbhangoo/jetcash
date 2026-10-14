#!/usr/bin/env python3
"""Exercise the real daemon/wallets on an isolated temporary regression chain."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

def rpc(port, method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "id": "jetcash-test", "method": method, "params": params or {}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json_rpc", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(f"{method}: {result['error']}")
    return result["result"]

def plain_rpc(port, endpoint, params=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/{endpoint}", json.dumps(params or {}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)

def wait_for(fn, processes, timeout=90):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        for p in processes:
            if p.poll() is not None:
                raise RuntimeError(f"child process exited with {p.returncode}")
        try:
            value = fn()
            if value: return value
        except (OSError, RuntimeError, urllib.error.URLError) as e:
            last_error = e
        time.sleep(0.2)
    raise TimeoutError(f"condition timed out: {last_error}")

def ports(count):
    with contextlib.ExitStack() as stack:
        sockets = [stack.enter_context(socket.socket()) for _ in range(count)]
        for s in sockets: s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in sockets]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, default=Path(os.environ.get("JETCASH_ENGINE_DIR", Path.home() / ".cache/jetcash/engine")) / "build")
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts/devnet-test.json")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    binaries = build / "bin"
    d0, p0, z0, d1, p1, z1, w0, w1 = ports(8)
    processes = []
    logs = []
    report = {"network": "isolated-regtest", "production_ready": False}
    with tempfile.TemporaryDirectory(prefix="jetcash-smoke-", dir=build.parent) as temp:
        work = Path(temp)
        def launch(name, argv):
            out = open(work / f"{name}.log", "w")
            logs.append(out)
            process = subprocess.Popen([str(a) for a in argv], stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
            processes.append(process)
            return process
        try:
            def daemon(name, rpc_port, p2p_port, zmq_port, extra):
                return launch(name, [binaries / "jetcashd", "--regtest", "--keep-fakechain", "--fixed-difficulty", "1",
                    "--non-interactive", "--data-dir", work / name, "--p2p-bind-ip", "127.0.0.1",
                    "--p2p-bind-port", p2p_port, "--rpc-bind-ip", "127.0.0.1", "--rpc-bind-port", rpc_port,
                    "--zmq-rpc-bind-ip", "127.0.0.1", "--zmq-rpc-bind-port", zmq_port,
                    "--rpc-ssl", "disabled", "--disable-dns-checkpoints", "--check-updates", "disabled",
                    "--allow-local-ip", "--no-igd", "--hide-my-port", "--log-level", "0", *extra])
            first = daemon("node-a", d0, p0, z0, ["--out-peers", "0"])
            wait_for(lambda: rpc(d0, "get_info"), processes)
            second = daemon("node-b", d1, p1, z1, ["--add-exclusive-node", f"127.0.0.1:{p0}"])
            wait_for(lambda: rpc(d1, "get_info"), processes)
            for name, port in [("alice", w0), ("bob", w1)]:
                directory = work / name
                directory.mkdir(mode=0o700)
                launch(name, [binaries / "jetcash-wallet-rpc", "--rpc-bind-ip", "127.0.0.1",
                    "--rpc-bind-port", port, "--disable-rpc-login", "--wallet-dir", directory,
                    "--daemon-address", f"127.0.0.1:{d0}", "--trusted-daemon", "--rpc-ssl", "disabled",
                    "--non-interactive", "--log-level", "0"])
                # No wallet is open yet, so probe get_version instead of get_balance.
                wait_for(lambda: rpc(port, "get_version"), processes)
                rpc(port, "create_wallet", {"filename": name, "password": "throwaway-regtest-only", "language": "English"})
                rpc(port, "auto_refresh", {"enable": False})
            alice = rpc(w0, "get_address")["address"]
            bob = rpc(w1, "get_address")["address"]
            genesis = rpc(d0, "get_block", {"height": 0})
            assert genesis["block_header"]["reward"] == 0, "genesis allocation must be zero"
            # Enough independent mature outputs to fill a ring of 16.
            print("Mining 85 real regression blocks with private wallet destinations...", flush=True)
            mined = rpc(d0, "generateblocks", {"wallet_address": alice, "amount_of_blocks": 85, "starting_nonce": 0})
            assert len(mined["blocks"]) == 85
            header = rpc(d0, "get_block_header_by_height", {"height": 1})["block_header"]
            assert header["major_version"] == 16 and header["reward"] == 500000000
            assert rpc(d0, "get_info")["target"] == 60, "JetCash target must be 60 seconds"
            rpc(w0, "refresh")
            before = rpc(w0, "get_balance")
            assert before["unlocked_balance"] >= 100000000
            print("Creating and relaying a CLSAG / Bulletproofs+ private payment...", flush=True)
            transfer = rpc(w0, "transfer", {"destinations": [{"address": bob, "amount": 100000000}],
                "account_index": 0, "priority": 1, "get_tx_key": False, "get_tx_hex": True,
                "do_not_relay": True})
            txid = transfer["tx_hash"]
            tampered = bytearray.fromhex(transfer["tx_blob"])
            tampered[-1] ^= 1
            rejected = plain_rpc(d0, "send_raw_transaction", {"tx_as_hex": tampered.hex(), "do_not_relay": True})
            assert rejected["status"] != "OK", "corrupted private transaction must be rejected"
            accepted = plain_rpc(d0, "send_raw_transaction", {"tx_as_hex": transfer["tx_blob"]})
            assert accepted["status"] == "OK", accepted
            rpc(d0, "generateblocks", {"wallet_address": alice, "amount_of_blocks": 12})
            rpc(w1, "refresh")
            received = rpc(w1, "get_balance")
            assert received["balance"] == 100000000 and received["unlocked_balance"] == 100000000
            raw = plain_rpc(d0, "get_transactions", {"txs_hashes": [txid], "decode_as_json": True})
            decoded = json.loads(raw["txs"][0]["as_json"])
            assert decoded["version"] == 2
            assert decoded["rct_signatures"]["type"] == 6, "Bulletproofs+ / CLSAG transaction required"
            assert all(output["amount"] == 0 for output in decoded["vout"]), "public output amounts forbidden"
            assert all(len(vin["key"]["key_offsets"]) == 16 for vin in decoded["vin"]), "ring size must be 16"
            # Independent node must validate, sync, and retain the same tip.
            expected = rpc(d0, "get_info")
            emission = rpc(d0, "get_coinbase_tx_sum", {"height": 0, "count": expected["height"]})
            assert emission["emission_amount"] == (expected["height"] - 1) * 500000000, "fees must not inflate emission"
            wait_for(lambda: rpc(d1, "get_info")["top_block_hash"] == expected["top_block_hash"], processes, timeout=120)
            assert rpc(d1, "get_info")["height"] == expected["height"]
            report.update({"height": expected["height"], "genesis_reward": 0, "first_subsidy_atomic": header["reward"],
                "hard_fork": header["major_version"], "ring_size": 16, "ringct_type": 6,
                "recipient_balance_atomic": received["balance"], "private_transfer_confirmed": True,
                "corrupted_transaction_rejected": True,
                "issuance_accounting_verified": True, "emission_atomic": emission["emission_amount"],
                "peer_sync": True, "transaction_hash": txid})
            # Replace two empty blocks on an isolated peer with a longer branch.
            # The private payment is deeper than this fork point and must survive.
            print("Testing a longer competing branch and wallet refresh after reorganization...", flush=True)
            second.terminate()
            second.wait(timeout=30)
            processes.remove(second)
            isolated = daemon("node-b", d1, p1, z1, ["--offline"])
            wait_for(lambda: rpc(d1, "get_info"), processes)
            popped = plain_rpc(d1, "pop_blocks", {"nblocks": 2})
            assert popped["height"] == expected["height"] - 2
            rpc(d1, "generateblocks", {"wallet_address": bob, "amount_of_blocks": 4})
            fork_tip = rpc(d1, "get_info")
            assert fork_tip["height"] == expected["height"] + 2
            isolated.terminate()
            isolated.wait(timeout=30)
            processes.remove(isolated)
            daemon("node-b", d1, p1, z1, ["--add-exclusive-node", f"127.0.0.1:{p0}"])
            wait_for(lambda: rpc(d0, "get_info")["top_block_hash"] == fork_tip["top_block_hash"], processes, timeout=120)
            rpc(w1, "refresh")
            assert rpc(w1, "get_balance")["balance"] == 2100000000, "wallet must discover reorg rewards"
            report["longer_chain_reorganization"] = True
            report["wallet_reorg_refresh"] = True
            expected = rpc(d0, "get_info")
            report["height"] = expected["height"]
            final_emission = rpc(d0, "get_coinbase_tx_sum", {"height": 0, "count": expected["height"]})
            assert final_emission["emission_amount"] == (expected["height"] - 1) * 500000000
            report["emission_atomic"] = final_emission["emission_amount"]
            report["final_recipient_balance_atomic"] = 2100000000
            report["target_seconds"] = expected["target"]
            # Restart the first node to exercise LMDB persistence and wallet recovery.
            rpc(w0, "store")
            rpc(w1, "store")
            first.terminate()
            first.wait(timeout=30)
            processes.remove(first)
            daemon("node-a", d0, p0, z0, ["--out-peers", "0"])
            wait_for(lambda: rpc(d0, "get_info")["top_block_hash"] == expected["top_block_hash"], processes)
            rpc(w1, "refresh")
            assert rpc(w1, "get_balance")["balance"] == 2100000000
            rpc(w1, "close_wallet")
            rpc(w1, "open_wallet", {"filename": "bob", "password": "throwaway-regtest-only"})
            rpc(w1, "auto_refresh", {"enable": False})
            rpc(w1, "refresh")
            assert rpc(w1, "get_balance")["balance"] == 2100000000
            report["encrypted_wallet_reopened"] = True
            report["restart_persistence"] = True
            report["passed"] = True
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
        except BaseException:
            for out in logs: out.flush()
            for log in work.glob("*.log"):
                print(f"--- {log.name} (last lines) ---\n" + "\n".join(log.read_text(errors="replace").splitlines()[-18:]))
            raise
        finally:
            for p in processes:
                if p.poll() is None: p.terminate()
            for p in processes:
                try: p.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            for out in logs: out.close()

if __name__ == "__main__":
    main()
