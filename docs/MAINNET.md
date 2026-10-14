# Mainnet operation

Mainnet is enabled in the C++ daemon and is the launcher's default profile. The
local node is separate from the temporary chains used for mining tests. Its data
directory is `~/.local/share/jetcash`. Enabling mainnet is not an independent audit.

## Start, inspect, stop

From PowerShell in the project folder:

```powershell
.\scripts\Start-JetCash.ps1
.\jetcash.ps1 info
.\scripts\Stop-JetCash.ps1
```

Start keeps WSL and the daemon running in a hidden Windows process after the
command returns. It is idempotent when this JetCash mainnet node is already
listening. Stop uses the daemon's graceful shutdown endpoint. The PC must stay
awake and connected; these scripts do not install a boot-time service.

For a foreground node instead, use `.\jetcash.ps1 node --mainnet --non-interactive`.
Default P2P binds all WSL IPv4 interfaces on TCP **41080**. Daemon RPC **41081** and
ZMQ RPC **41082** bind only to loopback. No mining starts automatically. No premine
or reward wallet has been created for the persistent chain.

Create your wallet with `.\jetcash.ps1 wallet --generate-new-wallet YOUR_WALLET_PATH`.
Record its recovery phrase privately. Use `start_mining 1` in the wallet to start
one CPU thread after the daemon has synchronized with a mainnet peer. An initial
standalone node with no peers reports `synchronized: false`; an enabled profile
alone is not an established peer network.

## Make this Windows PC reachable

Windows WSL forwarding observed on this machine currently listens on localhost.
Internet reachability requires both Windows forwarding/firewall configuration and
a reachable router/ISP path. From **Administrator PowerShell**, in this project:

```powershell
.\scripts\Enable-Public-P2P.ps1
```

The script forwards Windows TCP 41080 to the running WSL IPv4 address and creates
a firewall rule for that peer port. It does not forward RPC. Windows administrator
privileges are required for these operations. Run the script in an Administrator
PowerShell window. Re-run it after WSL changes its internal IPv4 address.
If the PC's LAN address changes, pass its current address with `-ListenAddress`.

On the router, forward external **TCP 41080** to this PC's LAN address
**YOUR_PC_LAN_IP**, port **41080** (check your current LAN address; verify it has
not changed). Keep a stable LAN assignment. The host must have a route for incoming
internet connections; forwarding alone cannot establish reachability through every
ISP or VPN configuration. An existing reachable VPS is an alternative.

Verify the peer port from a different internet connection. A successful localhost
request only proves that the local daemon is working. No public reachability check
has been completed, and no public seed address is currently configured.

## Joining from another node

Once the host is publicly reachable, start a node built from the same pinned
JetCash sources with an explicit bootstrap peer:

```powershell
.\jetcash.ps1 node --mainnet --non-interactive --add-priority-node PUBLIC_HOST:41080
```

Replace `PUBLIC_HOST` with the verified public IP or DNS name of the bootstrap
node. This placeholder is not a working seed. Public peers only need the peer
port, not wallet or daemon RPC access. Mainnet uses the UUID and genesis recorded
in [the network manifest](../network/mainnet.json). Regression peers have a
different peer UUID and are rejected. Fixed difficulty is restricted to regression
mode; normal mainnet uses the actual difficulty algorithm.

## Validation evidence

`artifacts/mainnet-test.json` records temporary-chain tests of real RandomX mining,
the 5 JET first reward, 60-second target, mainnet wallet refresh, peer sync,
regression-peer rejection, and restart persistence. The test chain and its wallets
are discarded. These checks do not allocate coins on the persistent node and do
not verify public internet reachability.

`dev-data/live-node.json` records the persistent process and genesis. Logs are in
`dev-data/mainnet.stdout.log` and `dev-data/mainnet.stderr.log`. Those files are
local runtime state, not public release artifacts. The build remains independently
unaudited; enabling a profile does not change that status.
