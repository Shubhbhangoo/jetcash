# Contributing

Use the locked engine revision in `engine/upstream.json`. Change the overlay in
`engine/prepare.py`, not just the generated cached engine tree. Preparation checks
the revision, preserves unknown local edits, copies the shared emission policy,
and generates `engine/jetcash.patch` for review. Commit the resulting patch alongside
overlay changes. Preserve upstream copyright and dependency notices.

Small CLI changes can be checked with:

```sh
python3 engine/test_cli.py
python3 engine/test_manage.py
```

Full checks (temporary chains; no real wallet funds):

```sh
python3 jetcash setup --no-start --jobs 2
python3 engine/test_prepare.py
python3 engine/manage_smoke_test.py
python3 jetcash test
python3 jetcash test-mainnet
```

The CLI smoke test checks background startup, authenticated wallet RPC, private
credential permissions, encrypted wallet creation/reopen, actual private payment,
balance display, and graceful stop/restart. Engine integration checks cover proof
rejection, accounting, peers and reorganizations. Mainnet mining checks use a
discarded temporary chain, never the operator's persistent data.

Consensus changes require explicit tests of malformed inputs and boundary behavior.
Never weaken signature/proof checks to make a test pass. Keep floating point out
of monetary consensus and display code. Do not add accepting placeholder cryptography.

Do not commit chain data, wallets, passwords, seed phrases, RPC login files, logs,
or machine-specific build reports. The source packager uses an explicit file list.
Contribution rights follow the [BSD-3-Clause license](LICENSE), while upstream code
retains its original notices. No copyright assignment is requested.
