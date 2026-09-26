$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv-py312\Scripts\python.exe"
$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) { $cloudflared = Join-Path $env:TEMP "cloudflared-quick-tunnel.exe" }
if (-not (Test-Path $cloudflared)) { throw "cloudflared is not installed or is not on PATH" }
if (-not (Test-Path $python)) { throw "missing Python environment: $python" }
$env:HELIX_APP_HOST = "127.0.0.1"
$env:HELIX_APP_PORT = "8100"
$env:HELIX_APP_COOKIE_SECURE = "false"
$env:HELIX_APP_ALLOW_INSECURE_COOKIES = "true"
$app = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "helix_codex_app.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8100") -WorkingDirectory $repo -PassThru
$log = Join-Path $env:TEMP "helix-cloudflared-$PID.log"
$errlog = Join-Path $env:TEMP "helix-cloudflared-$PID.err.log"
$tunnel = $null
try {
    Start-Sleep -Seconds 2
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8100/app/healthz" -UseBasicParsing
    if ($health.StatusCode -ne 200) { throw "loopback health check returned $($health.StatusCode)" }
    Write-Host "Helix app is listening on 127.0.0.1:8100"
    $tunnel = Start-Process -FilePath $cloudflared -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8100") -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru
    $origin = $null
    for ($i = 0; $i -lt 30 -and -not $origin; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $log) { $origin = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1 -ExpandProperty Matches | Select-Object -First 1 -ExpandProperty Value }
        if (-not $origin -and (Test-Path $errlog)) { $origin = Select-String -Path $errlog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1 -ExpandProperty Matches | Select-Object -First 1 -ExpandProperty Value }
    }
    if (-not $origin) { throw "cloudflared did not publish a Quick Tunnel URL; see $log and $errlog" }
    & (Join-Path $PSScriptRoot "update-worker-origin.ps1") -Origin $origin
    Write-Host "Worker origin registered: $origin"
    Wait-Process -Id $tunnel.Id
}
finally {
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id }
    if (-not $app.HasExited) { Stop-Process -Id $app.Id }
    Remove-Item -LiteralPath $log,$errlog -Force -ErrorAction SilentlyContinue
}