$ErrorActionPreference = 'Stop'
$body = '{"jsonrpc":"2.0","id":"jetcash-stop","method":"get_info"}'
$node = Invoke-RestMethod -Uri 'http://127.0.0.1:41081/json_rpc' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 5
if ($node.result.nettype -ne 'mainnet' -or $node.result.version -notlike '*jetcash*') { throw 'Refusing to stop a different service.' }
Invoke-RestMethod -Uri 'http://127.0.0.1:41081/stop_daemon' -Method Post -Body '{}' -ContentType 'application/json' -TimeoutSec 10 | Out-Null
Write-Output 'JetCash node received a graceful shutdown request.'
