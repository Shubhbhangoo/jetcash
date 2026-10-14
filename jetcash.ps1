param(
    [Parameter(Position=0)] [string]$Command = 'help',
    [Parameter(ValueFromRemainingArguments=$true)] [string[]]$JetCashArguments
)
$linuxRootOutput = & wsl.exe -d Ubuntu --exec wslpath -a $PSScriptRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$linuxRoot = ($linuxRootOutput -join '').Trim()
& wsl.exe -d Ubuntu --exec python3 "$linuxRoot/engine/cli.py" $Command @JetCashArguments
exit $LASTEXITCODE
