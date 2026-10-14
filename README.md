# JetCash

An **open-source Monero-derived C++ privacy coin** with RandomX CPU mining,
mandatory private payments, a **10,000,000 JET issuance ceiling**, and a **60-second
block target**. No premine or founder allocation. Mainnet is enabled.

The C++ engine is pinned to Monero v0.18.5.3 commit
`22578c3f7d7b4b6dd85ff7daa42a827d97cc53d0`. JetCash retains the established
cryptographic implementation and adapts consensus and network identity. This is
a development fork, not evidence of better privacy or security than Monero or
Zcash. A shorter target does not establish faster safe finality.

Licensed under [BSD-3-Clause](LICENSE). Anyone can build, modify, and run a node.
The node and cryptography run in C++; the CLI automates installation and operation.

## Build and run

Ubuntu/Debian, or Ubuntu inside Windows WSL:

```sh
git clone https://github.com/Shubhbhangoo/jetcash.git
cd jetcash
python3 jetcash setup
```

From PowerShell with Ubuntu WSL installed:

```powershell
.\jetcash.ps1 setup
.\jetcash.ps1 status
.\jetcash.ps1 wallet-create
.\jetcash.ps1 mine --threads 1
```

`setup` installs dependencies (using sudo when needed), fetches pinned source,
builds the C++ engine, runs consensus checks, and starts a background node.
It does not automatically create a wallet or start mining. Wallet commands prompt
for passwords, keep keys encrypted, and print recovery phrases only when requested.

**No public bootstrap peer is currently configured.** To join another node, use
`python3 jetcash setup --peer HOST:41080`, or `python3 jetcash peer add HOST:41080`.
Replace HOST with a reachable JetCash node. Source availability does not establish
a connected network; `doctor` reports actual peer and synchronization status.

[Complete CLI and node guide](docs/NODES.md) · [Hosting inbound peers](docs/MAINNET.md)

```sh
python3 jetcash wallet-create
python3 jetcash address
python3 jetcash balance
python3 jetcash mine --threads 1
python3 jetcash stop-mining
python3 jetcash send RECIPIENT_ADDRESS 1.25
python3 jetcash backup
python3 jetcash lock
python3 jetcash doctor
python3 jetcash stop
```

## Components

| Component | Implementation |
|---|---|
| C++ daemon | `jetcashd` |
| Wallet CLI / RPC | `jetcash-wallet-cli`, `jetcash-wallet-rpc` |
| Sender/amount privacy | Inherited CLSAG, RingCT, Bulletproofs+; mandatory ring size 16 |
| Recipient privacy | Inherited stealth addresses, subaddresses, view tags |
| CPU proof of work | Upstream RandomX v1.2.3, from the first mined block |
| Storage / reorgs | Inherited LMDB and cumulative-work chain validation |
| Mempool / relay | Inherited transaction validation and Dandelion++ |
| Supply policy | Shared integer-only header used by policy tool and daemon |
| Network isolation | Distinct genesis, IDs, address prefixes, ports, data namespace |

Monero seed peers, DNS/compiled checkpoints, DNS blocklists, and automatic update
authority are removed or disabled. Peers must be configured explicitly.
Mainnet P2P binds host interfaces; RPC stays on localhost. Some internal/help terminology retains upstream
names; attribution and licenses are preserved. Monero wallets/funds are incompatible.

## Monetary policy

One JET is 100,000,000 atomic units. Genesis has no outputs or allocation. Initial
subsidy is 5 JET, halving every 1,000,000 blocks for 29 nonzero eras. Height
29,000,001 has a scheduled rounding payment of 0.13 JET. Subsequent rewards are
fee-only. Fees recycle existing supply and do not count as new issuance.

The unpenalized schedule totals exactly 10 million JET. Inherited block-weight
penalties can reduce issuance below this ceiling; unpaid penalties are not reissued.
Reward calculation rejects already-issued values above the cap and clamps new
issuance to remaining supply. Coinbase amounts are public protocol rewards;
spend amounts use private transactions. Miner rewards mature after 60 blocks.
Fee estimation retains a nonzero floor after subsidy exhaustion.

A hard cap makes long-term mining security dependent on fees. The new block target,
emission, maturity timing, and fee economics require review before a public launch.

## Reproducibility and checks

- [Upstream lock](engine/upstream.json): exact source revision and pinned dependency gitlinks.
- [Preparation script](engine/prepare.py): guarded, idempotent overlay.
- [Source patch](engine/jetcash.patch): generated, reviewable fork changes.
- [Daemon reward tests](engine/reward_tests.cpp): actual engine reward function and cap/penalty boundaries.
- [Integration test](engine/smoke_test.py): two nodes/wallets, private transfer, corrupted
  transaction rejection, issuance accounting, peer sync, longer-fork adoption,
  wallet reorg refresh, and restart persistence.
- `artifacts/build.json`: binary hashes and overlay digest after a successful build.
- `artifacts/devnet-test.json`: written only after a successful integration test.

The root CMake project is a separate C++20 policy/hash tool named `jetcash-policy`,
not the daemon or wallet. It uses the same monetary header:

```sh
cmake -S . -B "$HOME/.cache/jetcash/policy" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$HOME/.cache/jetcash/policy" -j 2
ctest --test-dir "$HOME/.cache/jetcash/policy" --output-on-failure
"$HOME/.cache/jetcash/policy/jetcash-policy" supply 1000001
```

## Release status

Mainnet is enabled and a local persistent node can run. Public reachability needs host networking setup. No exchange listing, production audit,
or demonstrated superiority is included. Production work requires adversarial testnet
operation, economic analysis, fuzzing, and independent review of JetCash's changed
rules. See [protocol notes](docs/protocol.md).

Original JetCash code uses [BSD-3-Clause](LICENSE). The engine retains
[Monero's license](engine/LICENSE.monero) and dependency notices collected alongside
the build. See [NOTICE](NOTICE) and [contributor instructions](CONTRIBUTING.md).
