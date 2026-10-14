#!/usr/bin/env python3
"""Verify the actual mainnet profile using discarded, isolated local chains."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from smoke_test import rpc, plain_rpc, wait_for, ports

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, default=Path(os.environ.get("JETCASH_ENGINE_DIR", Path.home() / ".cache/jetcash/engine")) / "build")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    binaries = build / "bin"
    d0, p0, z0, d1, p1, z1, wrpc, dr, pr, zr = ports(10)
    processes, logs = [], []
    report = {"profile": "mainnet", "public_reachability_tested": False,
              "mining_chain": "temporary isolated chain discarded after testing"}
    with tempfile.TemporaryDirectory(prefix="jetcash-mainnet-check-", dir=build.parent) as directory:
        work = Path(directory)
        def launch(name, argv):
            out = open(work / (name + ".log"), "w")
            logs.append(out)
            process = subprocess.Popen([str(a) for a in argv], stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT)
            processes.append(process)
            return process
        def daemon(name, r, p, z, extra=()):
            return launch(name, [binaries / "jetcashd", "--non-interactive", "--data-dir", work / name,
                "--p2p-bind-ip", "127.0.0.1", "--p2p-bind-port", p, "--rpc-bind-ip", "127.0.0.1",
                "--rpc-bind-port", r, "--zmq-rpc-bind-ip", "127.0.0.1", "--zmq-rpc-bind-port", z,
                "--rpc-ssl", "disabled", "--no-igd", "--check-updates", "disabled", "--disable-dns-checkpoints",
                "--allow-local-ip", "--log-level", "1", *extra])
        try:
            guard = subprocess.run([str(binaries / "jetcashd"), "--non-interactive", "--no-igd",
                "--data-dir", str(work / "fixed-difficulty-refused"), "--fixed-difficulty", "1"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
            assert guard.returncode != 0 and "Fixed difficulty is restricted to --regtest" in guard.stdout
            report["mainnet_fixed_difficulty_refused"] = True
            # No --regtest and no fixed difficulty; default selector must be MAINNET.
            first = daemon("mainnet-a", d0, p0, z0, ["--out-peers", "0"])
            info = wait_for(lambda: rpc(d0, "get_info"), processes)
            assert info["nettype"] == "mainnet" and info["mainnet"] and not info["testnet"]
            genesis = rpc(d0, "get_block", {"height": 0})["block_header"]
            assert genesis["reward"] == 0
            manifest = json.loads((Path(__file__).resolve().parents[1] / "network/mainnet.json").read_text())
            assert genesis["hash"] == manifest["genesis_hash"], "genesis differs from published network manifest"
            report["genesis_hash"] = genesis["hash"]
            report["genesis_reward"] = 0
            second = daemon("mainnet-b", d1, p1, z1, ["--add-exclusive-node", f"127.0.0.1:{p0}"])
            wait_for(lambda: rpc(d1, "get_info"), processes)
            walletdir = work / "wallets"
            walletdir.mkdir(mode=0o700)
            launch("wallet", [binaries / "jetcash-wallet-rpc", "--non-interactive", "--wallet-dir", walletdir,
                "--rpc-bind-ip", "127.0.0.1", "--rpc-bind-port", wrpc, "--disable-rpc-login",
                "--daemon-address", f"127.0.0.1:{d0}", "--trusted-daemon", "--rpc-ssl", "disabled"])
            wait_for(lambda: rpc(wrpc, "get_version"), processes)
            rpc(wrpc, "create_wallet", {"filename": "mainnet-test-only", "password": "throwaway-mainnet-test", "language": "English"})
            rpc(wrpc, "auto_refresh", {"enable": False})
            address = rpc(wrpc, "get_address")["address"]
            try:
                rpc(d0, "generateblocks", {"wallet_address": address, "amount_of_blocks": 1})
            except RuntimeError as error:
                assert "Regtest required" in str(error)
            else:
                raise AssertionError("synthetic generation must be refused on mainnet")
            report["regtest_generation_refused"] = True
            print("Testing actual mainnet RandomX CPU mining on a temporary chain...", flush=True)
            mining = plain_rpc(d0, "start_mining", {"miner_address": address, "threads_count": 1,
                "do_background_mining": False, "ignore_battery": True})
            assert mining["status"] == "OK", mining
            wait_for(lambda: rpc(d0, "get_info")["height"] >= 2, processes, timeout=120)
            assert plain_rpc(d0, "stop_mining")["status"] == "OK"
            header = rpc(d0, "get_block_header_by_height", {"height": 1})["block_header"]
            assert header["major_version"] == 16 and header["reward"] == 500000000
            info = rpc(d0, "get_info")
            assert info["target"] == 60
            rpc(wrpc, "refresh")
            assert rpc(wrpc, "get_balance")["balance"] >= 500000000
            wait_for(lambda: rpc(d1, "get_info")["top_block_hash"] == info["top_block_hash"], processes)
            report.update({"randomx_cpu_mining": True, "first_reward_atomic": header["reward"],
                           "target_seconds": 60, "peer_sync": True, "wallet_refresh": True})
            # Default per-IP limits allow one loopback peer; free that slot first.
            second.terminate()
            second.wait(timeout=30)
            processes.remove(second)
            wait_for(lambda: not rpc(d0, "get_connections").get("connections", []), processes)
            # The regression peer's UUID must be rejected before chain synchronization.
            daemon("wrong-network", dr, pr, zr, ["--regtest", "--fixed-difficulty", "1",
                "--add-exclusive-node", f"127.0.0.1:{p0}"])
            wait_for(lambda: rpc(dr, "get_info"), processes)
            def wrong_network_logged():
                for out in logs: out.flush()
                text = (work / "wrong-network.log").read_text(errors="replace").lower()
                text += (work / "mainnet-a.log").read_text(errors="replace").lower()
                return "wrong network" in text
            wait_for(wrong_network_logged, processes, timeout=30)
            assert rpc(dr, "get_info")["height"] == 1
            report["regtest_peer_rejected"] = True
            first.terminate()
            first.wait(timeout=30)
            processes.remove(first)
            daemon("mainnet-a", d0, p0, z0, ["--out-peers", "0"])
            restored = wait_for(lambda: rpc(d0, "get_info"), processes)
            assert restored["top_block_hash"] == info["top_block_hash"]
            report["restart_persistence"] = True
            report["passed"] = True
            output = Path(__file__).resolve().parents[1] / "artifacts/mainnet-test.json"
            output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
        except BaseException:
            for out in logs: out.flush()
            for log in work.glob("*.log"):
                print(log.name + ":\n" + "\n".join(log.read_text(errors="replace").splitlines()[-14:]))
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

if __name__ == "__main__": main()
