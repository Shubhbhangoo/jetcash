# JetCash protocol and security scope

JetCash uses a pinned Monero C++ engine, not a new proof construction. The earlier
Orchard/Halo 2 proposal was not integrated. This provides actual private transaction
creation and validation while retaining a maintained implementation. It does not
broaden Monero's anonymity model or establish better privacy than Zcash's shielded pool.

## Active draft rules

- Version 1 genesis at height 0 with no outputs or spendable allocation.
- Version 16 rules at height 1: RandomX, CLSAG, Bulletproofs+, view tags, ring size 16,
  and mandatory RingCT spending.
- 60-second target with inherited difficulty adjustment.
- 8 decimals, 5 JET initial subsidy, million-block halvings, 10 million maximum
  scheduled issuance, no tail emission. Final rounding subsidy: 0.13 JET at 29,000,001.
- Inherited weight penalties reduce issuance; unpaid subsidy is not later emitted.
  Fees are existing coins. Reward-plus-fee addition is bounded.
- Production reward callers supply explicit heights. Static assertions keep engine
  denomination and cap aligned with the shared policy header.
- Inherited maturity counts: 60 blocks for coinbase, 10 blocks for normal outputs.
  Shorter wall-clock durations with the new target need security analysis.
- Distinct genesis, peer UUIDs, address prefixes, ports, and data namespace.
  No Monero seed/checkpoint/update authority.
- Mainnet enabled by default; regression, testnet, and stagenet remain explicit profiles. Regression peers use a distinct peer UUID and fixed difficulty is refused outside regression mode.

## Privacy properties and limits

The inherited system combines one-time recipient output keys, confidential spend
amounts, ring signatures, unique key images, range proofs, and signatures binding
transaction contents. Payment validity depends on the maintained cryptographic
implementation; encryption alone is not used as a payment-validity proof. Mining
coinbase amounts remain public scheduled values.

The objective is protection from passive chain observation. Effective anonymity
still depends on usage and decoy selection; a small development network has a
poor real anonymity set. Endpoint compromise, remote-node behavior, timing correlation,
eclipse attacks, malicious peers, and global traffic observation remain concerns.
Dandelion++ does not eliminate them. Tor/I2P capabilities are inherited but are not
configured or validated by the loopback integration test. No transparent payment mode
was added. Network identity changes are not new cryptographic privacy guarantees.

## Code boundaries

`include/jetcash/emission.hpp` is copied verbatim into the engine. The daemon calls
its integer subsidy function before applying inherited weight penalties. The policy
CLI models the unpenalized schedule and is not a substitute for full transaction
and chain validation.

`engine/upstream.json` pins the parent revision, which pins submodules. Preparation
checks source revision and previously generated content, refusing unrecognized edits
to files it owns. The generated patch exposes the fork changes for review.

Daemon and wallet operation remain in C++. Python only fetches/builds sources,
launches tools, and runs tests. The PowerShell wrapper passes argument arrays directly
to WSL without composing shell command strings.

## Comparative evidence and production gates

Measure median/p95 transaction construction/verification, weight, wallet scan time,
block propagation, stale blocks, memory, and throughput under fixed resource limits.
Record hardware, versions, transaction shape, anonymity assumptions, and confirmation
policy. Compare equivalent private operations. A shorter target alone proves neither
faster safe payments nor better privacy.

The regression test fixes difficulty to 1 and verifies behavior; it is not a security
or performance benchmark. Before production: sustained adversarial testnet, difficulty/
partition/reorg analysis, modified-interface fuzzing, cross-platform reproducible builds,
backup/recovery and remote-node tests, relay privacy evaluation, independent consensus/
security review, and fee-only mining security analysis. A public genesis and launch
plan need separate review. Upstream audits do not automatically apply to changed rules.

## Primary sources

- [Monero v0.18.5.3](https://github.com/monero-project/monero/releases/tag/v0.18.5.3)
- [Monero privacy documentation](https://www.getmonero.org/get-started/faq/)
- [RandomX implementation and specification](https://github.com/tevador/RandomX)
- [Zcash Orchard for comparison](https://zips.z.cash/zip-0224)