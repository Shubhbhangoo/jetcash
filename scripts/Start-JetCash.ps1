$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $projectRoot 'dev-data'
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$rpcUri = 'http://127.0.0.1:41081/json_rpc'
$request = '{"jsonrpc":"2.0","id":"jetcash-live","method":"get_info"}'
try { $existing = Invoke-RestMethod -Uri $rpcUri -Method Post -Body $request -ContentType 'application/json' -TimeoutSec 3 }
catch { $existing = $null }
if ($existing) {
    if ($existing.result.nettype -ne 'mainnet' -or $existing.result.version -notlike '*jetcash*') {
        throw 'Port 41081 is occupied by another node or network.'
    }
    Write-Output 'JetCash mainnet node is already running.'
    exit 0
}
if (Get-NetTCPConnection -LocalPort 41081 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 41081 is in use by another service.' }
$linuxRoot = ((& wsl.exe -d Ubuntu --exec wslpath -a $projectRoot) -join '').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the project in WSL.' }
$process = Start-Process -FilePath 'wsl.exe' -WindowStyle Hidden -PassThru -ArgumentList @(
    '-d', 'Ubuntu', '--exec', 'python3', "`"$linuxRoot/engine/cli.py`"", 'node', '--mainnet', '--non-interactive'
) -RedirectStandardOutput (Join-Path $stateDir 'mainnet.stdout.log') -RedirectStandardError (Join-Path $stateDir 'mainnet.stderr.log')
$deadline = (Get-Date).AddSeconds(60)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    $process.Refresh()
    if ($process.HasExited) { throw 'Node exited. Inspect dev-data/mainnet.stderr.log and mainnet.stdout.log.' }
    try {
        $response = Invoke-RestMethod -Uri $rpcUri -Method Post -Body $request -ContentType 'application/json' -TimeoutSec 2
        if ($response.result.nettype -eq 'mainnet' -and $response.result.version -like '*jetcash*') { $healthy = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 300
}
if (-not $healthy) { throw 'Node started but RPC readiness timed out. Inspect dev-data logs.' }
$genesisRequest = '{"jsonrpc":"2.0","id":"jetcash-live","method":"get_block","params":{"height":0}}'
$genesis = Invoke-RestMethod -Uri $rpcUri -Method Post -Body $genesisRequest -ContentType 'application/json' -TimeoutSec 10
$state = [ordered]@{
    windows_process_id = $process.Id
    network = 'mainnet'
    p2p_port = 41080
    rpc_url = $rpcUri
    genesis_hash = $genesis.result.block_header.hash
    internet_reachability_verified = $false
    data_directory = '~/.local/share/jetcash'
}
$state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDir 'live-node.json')
Write-Output "JetCash mainnet node running. P2P TCP 41080; RPC localhost 41081. Genesis: $($state.genesis_hash)"
