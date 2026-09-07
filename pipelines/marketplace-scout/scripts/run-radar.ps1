# Launches the Phase 0 radar (ai-marketplace-monitor).
# Secrets are read from the Windows USER environment (registry) FIRST — that is
# where setup-secrets.ps1 writes its verified values — falling back to this
# process's environment only if the registry has no value. User-first matters:
# a long-lived parent process can carry a stale pre-rotation value in its
# process environment, and that must never shadow a freshly verified one.
# Values are loaded into this process only and are never printed.

$ErrorActionPreference = 'Stop'

$names = 'ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'
$missing = @()
foreach ($n in $names) {
    $scope = $null
    $v = [Environment]::GetEnvironmentVariable($n, 'User')
    if ($v) { $scope = 'User' }
    else {
        $v = [Environment]::GetEnvironmentVariable($n, 'Process')
        if ($v) { $scope = 'Process' }
    }
    if ($v) {
        Set-Item -Path "Env:$n" -Value $v
        Write-Host "  $n : loaded from $scope scope"
    } else {
        $missing += $n
    }
}
if ($missing.Count -gt 0) {
    Write-Host "Missing secrets: $($missing -join ', '). Run scripts\setup-secrets.ps1 first."
    exit 1
}

$exe = Join-Path $PSScriptRoot '..\.venv\Scripts\ai-marketplace-monitor.exe'
if (-not (Test-Path $exe)) {
    Write-Host "Monitor executable not found at $exe - is the venv set up?"
    exit 1
}
Write-Host "Starting ai-marketplace-monitor (headed browser will open; log into Facebook there)..."
& $exe
exit $LASTEXITCODE
