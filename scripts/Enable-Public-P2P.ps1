# Run this from an Administrator PowerShell after starting the node.
param([Net.IPAddress]$ListenAddress)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Windows requires Administrator rights to configure TCP forwarding and its firewall. Run this script in Administrator PowerShell.' }
if (-not $ListenAddress) {
    $candidates = @(Get-NetIPConfiguration | Where-Object {
        $_.IPv4DefaultGateway -and $_.IPv4Address -and $_.InterfaceAlias -notmatch 'WSL|vEthernet|WARP'
    })
    if ($candidates.Count -ne 1) { throw 'Cannot choose a single LAN interface. Supply your LAN IPv4 address using -ListenAddress.' }
    $ListenAddress = [Net.IPAddress]$candidates[0].IPv4Address[0].IPAddress
}
if ($ListenAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
    -not (Get-NetIPAddress -AddressFamily IPv4 -IPAddress $ListenAddress.IPAddressToString -ErrorAction SilentlyContinue)) {
    throw 'ListenAddress must be an IPv4 address assigned to this PC. Supply the current LAN address with -ListenAddress.'
}
$addresses = ((& wsl.exe -d Ubuntu --exec hostname -I) -join '').Trim().Split(' ', [StringSplitOptions]::RemoveEmptyEntries)
if ($LASTEXITCODE -ne 0) { throw 'Cannot read the running WSL address.' }
$wslAddress = $null
foreach ($candidate in $addresses) {
    $parsedAddress = $null
    if ([Net.IPAddress]::TryParse($candidate, [ref]$parsedAddress) -and $parsedAddress.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) {
        $wslAddress = $parsedAddress.IPAddressToString
        break
    }
}
if (-not $wslAddress) { throw 'No WSL IPv4 address is available.' }
if (-not (Test-NetConnection -ComputerName $wslAddress -Port 41080 -InformationLevel Quiet)) { throw 'JetCash P2P is not listening in WSL. Start the node first.' }
$lanAddress = $ListenAddress.IPAddressToString
& netsh.exe interface portproxy add v4tov4 listenaddress=$lanAddress listenport=41080 connectaddress=$wslAddress connectport=41080 protocol=tcp
if ($LASTEXITCODE -ne 0) { throw 'Windows port forwarding failed.' }
$rule = Get-NetFirewallRule -Name 'JetCash-P2P-41080' -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -Name 'JetCash-P2P-41080' -DisplayName 'JetCash peer network TCP 41080' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $lanAddress -LocalPort 41080 -Profile Any | Out-Null
}
Write-Output "Windows now forwards $lanAddress TCP 41080 to WSL $wslAddress. RPC ports are not forwarded."
Write-Output 'Router step: forward external TCP 41080 to this PC TCP 41080. Then verify from a different internet connection.'
