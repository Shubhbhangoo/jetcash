#!/usr/bin/env python3
"""Local lifecycle management. Consensus, keys and proofs stay in the C++ engine."""
import argparse
import getpass
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {"mainnet": 41080, "testnet": 42080, "stagenet": 43080, "regtest": 44080}
PACKAGES = ["build-essential", "cmake", "ninja-build", "git", "pkg-config", "python3",
    "libssl-dev", "libboost-chrono-dev", "libboost-date-time-dev", "libboost-filesystem-dev",
    "libboost-locale-dev", "libboost-program-options-dev", "libboost-regex-dev",
    "libboost-serialization-dev", "libboost-system-dev", "libboost-thread-dev", "libzmq3-dev",
    "libsodium-dev", "libunbound-dev", "libreadline-dev", "libexpat1-dev", "libunwind-dev",
    "libhidapi-dev", "libusb-1.0-0-dev"]

def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink(): raise RuntimeError(f"Refusing a symlink for private state: {path}")
    path.chmod(0o700)
    return path

def private_write(path, text):
    private_dir(path.parent)
    temporary = path.with_name(path.name + "." + secrets.token_hex(6))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream: stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()

def amount_atomic(text):
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,8})?", text):
        raise RuntimeError("Amount must be a positive decimal with at most 8 places")
    whole, _, fraction = text.partition(".")
    value = int(whole) * 100000000 + int((fraction + "00000000")[:8])
    if not 0 < value <= 1000000000000000: raise RuntimeError("Amount must be above zero and at most 10 million JET")
    return value

def money(value): return f"{value // 100000000}.{value % 100000000:08d}"

def peer_address(text):
    try:
        parsed = urllib.parse.urlsplit("//" + text)
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError()
        host, port = parsed.hostname, parsed.port
        if not host or port is None or not 1 <= port <= 65535: raise ValueError()
        try: ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in host.split(".")):
                raise ValueError()
    except ValueError:
        raise RuntimeError("Peer must be HOST:PORT, or [IPv6]:PORT, without credentials or a URL path") from None
    return text

def rpc(port, method, params=None, credentials=None, plain=False, timeout=30):
    body = (params or {}) if plain else {"jsonrpc": "2.0", "id": "jetcash-cli", "method": method, "params": params or {}}
    path = "/" + method if plain else "/json_rpc"
    payload = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    # Upstream binds digest nonces to a TCP connection. Reuse that connection for
    # the challenge/response; urllib's digest handler opens a new one and fails.
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        for attempt in range(3):
            connection.request("POST", path, body=payload, headers=headers)
            response = connection.getresponse()
            data = response.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024: raise RuntimeError("RPC response exceeds limit")
            if response.status != 401: break
            if not credentials or attempt == 2: raise RuntimeError("Wallet RPC authentication failed")
            fields = None
            # Upstream advertises multiple Digest algorithms in separate headers.
            # getheader() joins them, which would mix distinct challenges.
            for key, challenge in response.getheaders():
                if key.lower() != "www-authenticate" or not challenge.startswith("Digest "): continue
                candidate = urllib.request.parse_keqv_list(urllib.request.parse_http_list(challenge[7:]))
                if candidate.get("algorithm", "MD5").upper() == "MD5" and "auth" in [q.strip() for q in candidate.get("qop", "").split(",")]:
                    fields = candidate
                    break
            if fields is None: raise RuntimeError("Unsupported RPC digest algorithm")
            username, password = credentials
            realm, nonce = fields.get("realm", ""), fields.get("nonce", "")
            if not nonce or any(ord(c) < 32 for c in realm + nonce + username): raise RuntimeError("Invalid RPC digest challenge")
            # MD5 is required by the upstream HTTP-auth protocol, not used for PoW or keys.
            digest = lambda text: hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()
            cnonce, count = secrets.token_hex(16), "00000001"
            answer = digest(f"{digest(username + ':' + realm + ':' + password)}:{nonce}:{count}:{cnonce}:auth:{digest('POST:' + path)}")
            quote = lambda text: '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
            values = {"username": username, "realm": realm, "nonce": nonce, "uri": path, "response": answer, "cnonce": cnonce}
            if "opaque" in fields: values["opaque"] = fields["opaque"]
            headers["Authorization"] = "Digest " + ", ".join(key + "=" + quote(value) for key, value in values.items()) + ", algorithm=MD5, qop=auth, nc=" + count
        if response.status != 200: raise RuntimeError(f"RPC HTTP status {response.status}")
        result = json.loads(data)
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as error:
        raise RuntimeError(f"Local RPC on port {port} is unavailable: {error}") from None
    finally: connection.close()
    if "error" in result: raise RuntimeError(f"{method}: {result['error'].get('message', 'RPC error')}")
    result = result if plain else result.get("result", {})
    if result.get("status", "OK") != "OK": raise RuntimeError(f"{method}: {result['status']}")
    return result

def port_busy(port):
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0

def wait_until(function, process=None, timeout=60):
    deadline = time.monotonic() + timeout
    last = "not ready"
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None: raise RuntimeError("Service exited; inspect the log shown above")
        try:
            result = function()
            if result: return result
        except RuntimeError as error: last = str(error)
        time.sleep(0.2)
    raise RuntimeError(f"Service readiness timed out: {last}")

class Manager:
    def __init__(self, profile="mainnet"):
        self.profile = profile
        self.home = Path(os.environ.get("JETCASH_HOME", Path.home() / ".local/share/jetcash")).expanduser().resolve()
        self.work = Path(os.environ.get("JETCASH_ENGINE_DIR", Path.home() / ".cache/jetcash/engine")).expanduser().resolve()
        self.control = self.home / ".control" / profile
        self.wallets = self.home / "wallets" / profile
        self.base = int(os.environ.get("JETCASH_PORT_BASE", PROFILES[profile]))
        if not 1024 <= self.base <= 65531: raise RuntimeError("Port base must be 1024..65531")
        self.rport, self.zport, self.wport = self.base + 1, self.base + 2, self.base + 3
        self.config_file = self.control / "settings.json"
        self.config = json.loads(self.config_file.read_text()) if self.config_file.exists() else {"peers": []}
        for peer in self.config.get("peers", []): peer_address(peer)

    @property
    def binaries(self): return self.work / "build/bin"

    def binary(self, name):
        binary = self.binaries / name
        if not binary.is_file(): raise RuntimeError("JetCash is not built yet. Run: jetcash setup")
        return binary

    def save(self): private_write(self.config_file, json.dumps(self.config, indent=2) + "\n")

    def daemon(self, method, params=None, plain=False):
        return rpc(self.rport, method, params, plain=plain)

    def node_info(self):
        info = self.daemon("get_info")
        expected = "fakechain" if self.profile == "regtest" else self.profile
        if info.get("nettype") != expected or "jetcash" not in info.get("version", ""):
            raise RuntimeError("RPC port belongs to a different node or profile; refusing to control it")
        if self.profile in ("mainnet", "regtest"):
            expected_hash = json.loads((ROOT / "network/mainnet.json").read_text())["genesis_hash"]
            if self.daemon("get_block", {"height": 0})["block_header"]["hash"] != expected_hash:
                raise RuntimeError("Node genesis differs from the locked JetCash network")
        return info

    def launch(self, name, argv):
        private_dir(self.control)
        log = self.control / (name + ".log")
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as output:
            child = subprocess.Popen([str(a) for a in argv], stdin=subprocess.DEVNULL, stdout=output,
                stderr=subprocess.STDOUT, start_new_session=True)
        private_write(self.control / (name + ".pid"), str(child.pid) + "\n")
        print(f"{name} log: {log}")
        return child

    def start(self):
        if port_busy(self.rport):
            info = self.node_info()
            print(f"Node already running: {self.profile}, height {info['height']}")
            return info
        private_dir(self.home)
        argv = [self.binary("jetcashd"), "--non-interactive", "--data-dir", self.home,
            "--p2p-bind-ip", "0.0.0.0" if self.profile == "mainnet" else "127.0.0.1",
            "--p2p-bind-port", self.base, "--rpc-bind-ip", "127.0.0.1", "--rpc-bind-port", self.rport,
            "--zmq-rpc-bind-ip", "127.0.0.1", "--zmq-rpc-bind-port", self.zport,
            "--no-igd", "--check-updates", "disabled", "--disable-dns-checkpoints", "--rpc-ssl", "disabled",
            "--log-file", self.control / "daemon-engine.log", "--log-level", "0"]
        if self.profile != "mainnet": argv.append("--" + self.profile)
        if self.profile == "regtest": argv += ["--keep-fakechain", "--fixed-difficulty", "1", "--allow-local-ip"]
        for peer in self.config.get("peers", []): argv += ["--add-priority-node", peer]
        private_dir(self.control)
        child = self.launch("node", argv)
        info = wait_until(self.node_info, child)
        self.save()
        print(f"Node running: {self.profile}, P2P {self.base}, local RPC {self.rport}")
        if not info.get("synchronized"):
            print("Waiting for peers. Add a reachable peer with: jetcash peer add HOST:PORT")
        return info

    def stop(self):
        self.stop_wallet_service()
        if not port_busy(self.rport):
            print("Node is already stopped")
            return
        self.node_info()
        self.daemon("stop_daemon", plain=True)
        wait_until(lambda: not port_busy(self.rport), timeout=30)
        print("Node stopped cleanly; chain and wallets kept")

    def wallet_credentials(self):
        path = self.control / "wallet-rpc-credentials.json"
        if not path.exists():
            private_write(path, json.dumps({"username": "jetcash", "password": secrets.token_hex(32)}))
        if path.is_symlink() or path.stat().st_mode & 0o077: raise RuntimeError("Wallet RPC credentials must be private (mode 600)")
        value = json.loads(path.read_text())
        return value["username"], value["password"]

    def wallet_rpc(self, method, params=None):
        return rpc(self.wport, method, params, credentials=self.wallet_credentials(), timeout=120)

    def wallet_service(self):
        self.start()
        private_dir(self.wallets)
        credentials = self.wallet_credentials()
        if port_busy(self.wport):
            self.wallet_rpc("get_version")
            return
        cfg = self.control / "wallet-rpc.conf"
        private_write(cfg, f"rpc-login={credentials[0]}:{credentials[1]}\n")
        argv = [self.binary("jetcash-wallet-rpc"), "--config-file", cfg, "--non-interactive",
            "--wallet-dir", self.wallets, "--rpc-bind-ip", "127.0.0.1", "--rpc-bind-port", self.wport,
            "--rpc-ssl", "disabled", "--daemon-address", f"127.0.0.1:{self.rport}", "--trusted-daemon",
            "--log-file", self.control / "wallet-engine.log", "--log-level", "0"]
        if self.profile in ("testnet", "stagenet"): argv += ["--" + self.profile]
        child = self.launch("wallet-rpc", argv)
        wait_until(lambda: self.wallet_rpc("get_version"), child)

    def stop_wallet_service(self):
        if not port_busy(self.wport): return
        # Authenticate before stopping; never kill a PID read from an untrusted file.
        self.wallet_rpc("get_version")
        self.wallet_rpc("stop_wallet")
        wait_until(lambda: not port_busy(self.wport), timeout=30)
        opened = self.control / "opened-wallet.json"
        if opened.exists(): opened.unlink()

    def name(self, name):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
            raise RuntimeError("Wallet name must be 1..64 letters, digits, underscores or hyphens")
        return name

    def create_wallet(self, name="default"):
        name = self.name(name)
        self.wallet_service()
        if (self.wallets / (name + ".keys")).exists(): raise RuntimeError("Wallet already exists; use address or balance to open it")
        password = getpass.getpass("New wallet password: ")
        if len(password) < 8: raise RuntimeError("Use a wallet password of at least 8 characters")
        if password != getpass.getpass("Repeat wallet password: "): raise RuntimeError("Passwords do not match")
        try: self.wallet_rpc("close_wallet")
        except RuntimeError: pass  # A new service may have no wallet open.
        self.wallet_rpc("create_wallet", {"filename": name, "password": password, "language": "English"})
        self.wallet_rpc("auto_refresh", {"enable": False})
        private_write(self.control / "opened-wallet.json", json.dumps({"name": name}))
        address = self.wallet_rpc("get_address")["address"]
        seed = self.wallet_rpc("query_key", {"key_type": "mnemonic"})["key"]
        print(f"Wallet: {name}\nAddress: {address}\nRecovery phrase — record privately; it is not saved by the manager:\n{seed}")
        return address

    def open_wallet(self, name="default"):
        name = self.name(name)
        self.wallet_service()
        path = self.control / "opened-wallet.json"
        if path.exists() and json.loads(path.read_text()).get("name") == name:
            try: return self.wallet_rpc("get_address")["address"]
            except RuntimeError: pass
        if not (self.wallets / (name + ".keys")).is_file():
            raise RuntimeError("Wallet does not exist. Run: jetcash wallet-create --name " + name)
        try: self.wallet_rpc("close_wallet")
        except RuntimeError: pass
        password = getpass.getpass(f"Password for wallet {name}: ")
        self.wallet_rpc("open_wallet", {"filename": name, "password": password})
        self.wallet_rpc("auto_refresh", {"enable": False})
        private_write(path, json.dumps({"name": name}))
        return self.wallet_rpc("get_address")["address"]

    def doctor(self):
        result = {"network": self.profile, "engine_directory": str(self.work), "data_directory": str(self.home),
            "p2p_port": self.base, "rpc_loopback_port": self.rport,
            "binaries": {name: (self.binaries / name).is_file() for name in ("jetcashd", "jetcash-wallet-cli", "jetcash-wallet-rpc")},
            "configured_peers": self.config.get("peers", []), "public_reachability_verified": False}
        try:
            info = self.node_info()
            result.update({"running": True, "height": info["height"], "synchronized": info["synchronized"],
                "incoming_peers": info["incoming_connections_count"], "outgoing_peers": info["outgoing_connections_count"]})
        except RuntimeError as error: result.update({"running": False, "detail": str(error)})
        print(json.dumps(result, indent=2))
        return result

def dependencies():
    if shutil.which("dpkg-query"):
        packages = subprocess.run(["dpkg-query", "-W", "-f=${db:Status-Status}\n", *PACKAGES],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        statuses = packages.stdout.splitlines()
        return packages.returncode == 0 and len(statuses) == len(PACKAGES) and all(status == "installed" for status in statuses)
    return all(shutil.which(name) for name in ("cmake", "g++", "ninja", "git", "pkg-config")) and subprocess.run(
        ["pkg-config", "--exists", "openssl", "libsodium", "libzmq", "libunbound", "expat", "libunwind"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0 and Path("/usr/include/boost/program_options.hpp").exists()

def setup(manager, args):
    if not dependencies():
        if not shutil.which("apt-get"): raise RuntimeError("Automatic dependency setup supports Ubuntu/Debian. Install the dependencies listed in docs/DEVNET.md")
        prefix = [] if os.geteuid() == 0 else ["sudo"]
        subprocess.run([*prefix, "apt-get", "update"], check=True)
        subprocess.run([*prefix, "apt-get", "install", "-y", *PACKAGES], check=True)
    subprocess.run([sys.executable, str(ROOT / "engine/build.py"), "--work-dir", str(manager.work), "--jobs", str(args.jobs)], check=True)
    if args.peer:
        manager.config["peers"] = list(dict.fromkeys(manager.config.get("peers", []) + args.peer))
        manager.save()
        if not args.no_start and port_busy(manager.rport): manager.stop()
    if not args.no_start: manager.start()
    print("Ready. Use: jetcash wallet-create | jetcash mine | jetcash doctor")

def main(command, argv):
    parser = argparse.ArgumentParser(prog="jetcash " + command)
    parser.add_argument("--network", choices=PROFILES, default="mainnet")
    if command == "setup":
        parser.add_argument("--jobs", type=int, default=2)
        parser.add_argument("--peer", type=peer_address, action="append", default=[])
        parser.add_argument("--no-start", action="store_true")
    if command == "peer":
        parser.add_argument("action", choices=["add", "remove", "list"])
        parser.add_argument("address", type=peer_address, nargs="?")
    if command in ("wallet-create", "address", "balance", "backup", "mine", "send"):
        parser.add_argument("--name", default="default")
    if command == "mine": parser.add_argument("--threads", type=int, default=1)
    if command == "send":
        parser.add_argument("address")
        parser.add_argument("amount", type=amount_atomic)
    args = parser.parse_args(argv)
    manager = Manager(args.network)
    if command == "setup":
        if not 1 <= args.jobs <= 32: parser.error("jobs must be 1..32")
        setup(manager, args)
    elif command == "start": manager.start()
    elif command == "stop": manager.stop()
    elif command == "restart":
        manager.stop()
        manager.start()
    elif command in ("status", "doctor"): manager.doctor()
    elif command == "peer":
        if args.action == "list": print(json.dumps(manager.config.get("peers", []), indent=2))
        else:
            if not args.address: parser.error("peer add/remove requires HOST:PORT")
            peers = manager.config.setdefault("peers", [])
            if args.action == "add" and args.address not in peers: peers.append(args.address)
            if args.action == "remove" and args.address in peers: peers.remove(args.address)
            manager.save()
            manager.stop()
            manager.start()
    elif command == "wallet-create": manager.create_wallet(args.name)
    elif command == "address": print(manager.open_wallet(args.name))
    elif command == "balance":
        manager.open_wallet(args.name)
        manager.wallet_rpc("refresh")
        balance = manager.wallet_rpc("get_balance")
        print(f"Balance: {money(balance['balance'])} JET\nUnlocked: {money(balance['unlocked_balance'])} JET")
    elif command == "backup":
        manager.open_wallet(args.name)
        # Reopening requires the wallet password before disclosing recovery material.
        manager.wallet_rpc("close_wallet")
        opened = manager.control / "opened-wallet.json"
        if opened.exists(): opened.unlink()
        manager.open_wallet(args.name)
        print(manager.wallet_rpc("query_key", {"key_type": "mnemonic"})["key"])
    elif command == "lock": manager.stop_wallet_service()
    elif command == "mine":
        if not 1 <= args.threads <= (os.cpu_count() or 1) * 4: parser.error("invalid CPU thread count")
        if not (manager.wallets / (manager.name(args.name) + ".keys")).exists():
            print("Create a receiving wallet before mining:")
            address = manager.create_wallet(args.name)
        else: address = manager.open_wallet(args.name)
        info = manager.node_info()
        if not info["synchronized"]: raise RuntimeError("Node is waiting for peers; use jetcash peer add HOST:PORT, then retry mining")
        manager.daemon("start_mining", {"miner_address": address, "threads_count": args.threads,
            "do_background_mining": False, "ignore_battery": True}, plain=True)
        print(f"CPU mining started with {args.threads} thread(s). Use jetcash stop-mining to stop.")
    elif command == "stop-mining":
        manager.node_info()
        manager.daemon("stop_mining", plain=True)
        print("Mining stopped")
    elif command == "send":
        manager.open_wallet(args.name)
        manager.wallet_rpc("refresh")
        result = manager.wallet_rpc("transfer", {"destinations": [{"address": args.address, "amount": args.amount}],
            "account_index": 0, "priority": 1, "get_tx_key": False})
        print(f"Sent: {money(args.amount)} JET\nFee: {money(result['fee'])} JET\nTransaction: {result['tx_hash']}")
    return 0
