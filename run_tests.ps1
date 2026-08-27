# Helix Prime — cross-platform test runner (C0 fix 2026-08-27)
# Windows: powershell -ExecutionPolicy Bypass -File run_tests.ps1
# Linux/macOS: python3 -m pytest -q
$venvPython = Join-Path $PSScriptRoot ".venv" "Scripts" "python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = Join-Path $PSScriptRoot ".venv" "bin" "python"
}
if (Test-Path $venvPython) {
    & $venvPython -m pytest -q --basetemp="$PSScriptRoot/.pytest-tmp"
} else {
    Write-Host "No .venv found at $PSScriptRoot/.venv — trying system python"
    python -m pytest -q --basetemp="$PSScriptRoot/.pytest-tmp"
    if ($LASTEXITCODE -ne 0) { python3 -m pytest -q --basetemp="$PSScriptRoot/.pytest-tmp" }
}
