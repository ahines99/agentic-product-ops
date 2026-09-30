param(
    [string]$Distro = 'Ubuntu-22.04',
    [string]$ComposeProject = 'apo-offline-g07'
)
$ErrorActionPreference = 'Stop'
$pilotRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pilotDirectory = Join-Path $pilotRoot '.local/pilot'
if (-not (Test-Path -LiteralPath (Join-Path $pilotDirectory 'pilot.json'))) {
    throw 'Initialized private pilot profile required'
}
$pilotHash = [Convert]::ToBase64String([Security.Cryptography.SHA256]::Create().ComputeHash(
    [Text.Encoding]::UTF8.GetBytes($pilotRoot))).Replace('/', '_')
$pilotMutex = [Threading.Mutex]::new($false, "Local\AgenticProductOps-$pilotHash")
$pilotOwnsMutex = $false
$pilotKeepalive = $null
$pilotProcess = $null
function Stop-OwnedPilotTunnel {
    $pilotTunnelRecord = Join-Path $pilotDirectory 'tunnel-process.json'
    if (Test-Path -LiteralPath $pilotTunnelRecord) {
        $pilotTunnel = Get-Content -LiteralPath $pilotTunnelRecord -Raw | ConvertFrom-Json
        $pilotProfile = Get-Content -LiteralPath (Join-Path $pilotDirectory 'pilot.json') -Raw | ConvertFrom-Json
        $pilotCandidate = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$pilotTunnel.pid)"
        if ($null -ne $pilotCandidate -and $pilotCandidate.ExecutablePath -eq $pilotProfile.cloudflared_path -and
            $pilotTunnel.executable -eq $pilotProfile.cloudflared_path -and
            $pilotCandidate.CommandLine.Contains("http://127.0.0.1:$($pilotProfile.linear_webhook_port)")) {
            Stop-Process -Id $pilotCandidate.ProcessId -ErrorAction SilentlyContinue
        }
    }
}
try {
    try { $pilotOwnsMutex = $pilotMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $pilotOwnsMutex = $true }
    if (-not $pilotOwnsMutex) { exit 0 }
    Set-Location -LiteralPath $pilotRoot
    $pilotWsl = Join-Path $env:SystemRoot 'System32/wsl.exe'
    $pilotKeepalive = Start-Process -FilePath $pilotWsl -ArgumentList '-d',$Distro,'--exec','sleep','infinity' -WindowStyle Hidden -PassThru
    $pilotLinuxRoot = (& $pilotWsl -d $Distro --exec wslpath -a $pilotRoot).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pilotLinuxRoot.StartsWith('/mnt/')) { throw 'WSL path resolution failed' }
    while ($true) {
        Stop-OwnedPilotTunnel
        # Windows PowerShell treats native stderr progress as an error record.
        # Compose's exit code is authoritative; progress output is not a startup failure.
        $ErrorActionPreference = 'Continue'
        & $pilotWsl -d $Distro --exec docker compose --project-directory $pilotLinuxRoot -p $ComposeProject up --detach --wait postgres temporal *> (Join-Path $pilotDirectory 'infrastructure.log')
        $pilotComposeExit = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($pilotComposeExit -eq 0) {
            $pilotProcess = Start-Process -FilePath (Join-Path $pilotRoot '.venv/Scripts/python.exe') -ArgumentList '-m','agentic_product_ops.pilot.cli','run' -WorkingDirectory $pilotRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $pilotDirectory 'service-stdout.log') -RedirectStandardError (Join-Path $pilotDirectory 'service-stderr.log') -PassThru
            $pilotProcess.Id | Set-Content -LiteralPath (Join-Path $pilotDirectory 'service-launcher.pid')
            $pilotProcess.WaitForExit()
            Stop-OwnedPilotTunnel
        }
        Start-Sleep -Seconds 15
    }
} finally {
    if ($pilotOwnsMutex) { Stop-OwnedPilotTunnel }
    if ($null -ne $pilotProcess -and -not $pilotProcess.HasExited) { $pilotProcess.Kill() }
    if ($null -ne $pilotKeepalive -and -not $pilotKeepalive.HasExited) { $pilotKeepalive.Kill() }
    if ($pilotOwnsMutex) { $pilotMutex.ReleaseMutex() }
    $pilotMutex.Dispose()
}
