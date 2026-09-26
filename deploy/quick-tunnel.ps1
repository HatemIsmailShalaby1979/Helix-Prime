$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv-py312\Scripts\python.exe"
$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) { throw "cloudflared is not installed or is not on PATH" }
if (-not (Test-Path $python)) { throw "missing Python environment: $python" }
$env:HELIX_APP_HOST = "127.0.0.1"
$env:HELIX_APP_PORT = "8100"
$env:HELIX_APP_COOKIE_SECURE = "false"
$env:HELIX_APP_ALLOW_INSECURE_COOKIES = "true"
$app = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "helix_codex_app.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8100") -WorkingDirectory $repo -PassThru
try {
    Start-Sleep -Seconds 2
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8100/app/healthz" -UseBasicParsing
    if ($health.StatusCode -ne 200) { throw "loopback health check returned $($health.StatusCode)" }
    Write-Host "Helix app is listening on 127.0.0.1:8100"
    & $cloudflared tunnel --url "http://127.0.0.1:8100"
}
finally {
    if (-not $app.HasExited) { Stop-Process -Id $app.Id }
}