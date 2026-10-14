# Run JetCash in WSL

JetCash's working engine is a pinned, modified Monero C++ codebase. It inherits
stealth addresses, RingCT, CLSAG, Bulletproofs+, view tags, Dandelion++ relay,
RandomX, LMDB storage, chain validation/reorganization, a mempool, CLI wallets,
and daemon/wallet RPC. The patch changes consensus and network identity; upstream
review does not constitute an audit of JetCash's modifications.

## Build and verify

From PowerShell in the project folder:

```powershell
.\jetcash.ps1 build --jobs 2
.\jetcash.ps1 test
.\jetcash.ps1 status
```

From Ubuntu in this project folder:

```sh
python3 engine/build.py --jobs 2
python3 engine/smoke_test.py
```

The build uses `~/.cache/jetcash/engine` for source, binaries, and notices. First
build needs network access to clone the pinned engine and submodules. Existing
unrecognized edits in patched upstream files cause preparation to stop rather
than silently overwrite them. No private keys or user wallets are involved in
building. The integration test creates temporary throwaway wallets and stops its
processes before deleting the temporary chain and wallets.

Dependencies on Ubuntu (already installed on this machine during development):

```sh
sudo apt-get install build-essential cmake ninja-build git pkg-config python3 \
  libssl-dev libboost-chrono-dev libboost-date-time-dev libboost-filesystem-dev \
  libboost-locale-dev libboost-program-options-dev libboost-regex-dev \
  libboost-serialization-dev libboost-system-dev libboost-thread-dev libzmq3-dev \
  libsodium-dev libunbound-dev libreadline-dev libexpat1-dev libunwind-dev \
  libhidapi-dev libusb-1.0-0-dev
```

The binaries are `jetcashd`, `jetcash-wallet-cli`, and `jetcash-wallet-rpc`, inside
`~/.cache/jetcash/engine/build/bin`. They run in WSL; native Windows release
binaries are not packaged. Hardware-wallet support is not a tested JetCash feature.

## Start a persistent local testnet node

```powershell
.\jetcash.ps1 node --testnet --non-interactive
```

This stays in the foreground. Ctrl+C shuts it down cleanly. The launcher selects
JetCash testnet explicitly and binds P2P/RPC to localhost. Mainnet is enabled in the
C++ engine. There are no public seeds, checkpoints, or automatic Monero updates.
Explicit JetCash peers can be configured using upstream daemon peer options.

| Profile | P2P | Daemon RPC | ZMQ RPC |
|---|---:|---:|---:|
| Mainnet / regtest configuration | 41080 | 41081 | 41082 |
| Testnet | 42080 | 42081 | 42082 |
| Stagenet | 43080 | 43081 | 43082 |

Data uses the `jetcash-dev` namespace. Wallet files are stored where you explicitly
create them. Keep wallet passwords and recovery phrases private. The test script's
throwaway-wallet password is only for its isolated regression run.

## Create wallets

Open another terminal:

```powershell
.\jetcash.ps1 wallet --testnet --generate-new-wallet YOUR_WALLET_PATH
```

Create the parent directory in Ubuntu first. The CLI prompts for a password and
shows the recovery phrase. Record the recovery phrase yourself. Use a second
wallet file for Bob. Use `address`, `balance`, `refresh`, and `help` in the wallet.
The launcher connects the wallet to the local testnet node.

## CPU mining and payments

In Alice's interactive wallet connected to the trusted local daemon:

```text
start_mining 1
```

This explicitly starts one CPU mining thread at Alice's address. Use
`stop_mining` to stop. This is real RandomX mining; speed depends on CPU and
memory. Miner rewards unlock after 60 blocks. No mining starts during build or
when you merely create a wallet.

After mining enough mature outputs for the mandatory ring size of 16, use:

```text
transfer BOB_ADDRESS 1
```

The payment uses mandatory private transaction rules. Mining coinbase amounts
are public protocol rewards; spend amounts and recipient addresses are protected
by the inherited privacy system. Small development networks have a weak real
anonymity set even when cryptographic verification succeeds.

Use `.\jetcash.ps1 info --testnet` from PowerShell to inspect the running testnet daemon.
Daemon and wallet RPC follow the pinned upstream interfaces, with JetCash's own
addresses, denomination, ports, genesis, and consensus parameters. Some help text
and internal RPC field names retain upstream terminology. Monero wallets and
Monero funds are not compatible with this chain.

## Integration test scope

The smoke test starts two local nodes and two wallets, creates regression blocks,
makes a 1 JET private payment, checks RingCT type 6 and ring size 16, rejects a
corrupted signed transaction, verifies issuance accounting and peer sync, adopts
a longer competing branch, refreshes the wallet after reorganization, reopens its
encrypted wallet file, and restarts the first node to check persistence.
All RPC listeners are loopback only.
The regression network fixes difficulty to 1 to finish tests quickly. It does not
measure production block time or network security.

The report is written to `artifacts/devnet-test.json` only after success. The
separate `jetcash-consensus-tests` binary exercises the actual engine's reward
function at every halving boundary, the cap, excess supply, block-weight penalties,
JET display units, and the actual wallet's fork-version checks.

## Before any public launch

Resolve economic security after subsidy exhaustion, audit consensus changes,
test difficulty and fork behavior under adversarial conditions, evaluate shortened
confirmation/maturity windows, fuzz the modified integration, benchmark the actual
network, run a sustained testnet, and commission independent review. A 60-second
block target alone does not establish better speed, finality, or privacy than Monero
or Zcash. Mainnet operation is documented in MAINNET.md and does not establish production security.
