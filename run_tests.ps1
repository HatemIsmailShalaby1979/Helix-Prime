& "h:\Project Helix Prime Ecosystem\.venv\Scripts\Activate.ps1"
$env:TMPDIR = "h:\Project Helix Prime Ecosystem\.pytest-tmp"
$env:TEMP = "h:\Project Helix Prime Ecosystem\.pytest-tmp"
$env:TMP = "h:\Project Helix Prime Ecosystem\.pytest-tmp"
if (-not (Test-Path "h:\Project Helix Prime Ecosystem\.pytest-tmp")) { New-Item -ItemType Directory -Path "h:\Project Helix Prime Ecosystem\.pytest-tmp" | Out-Null }
& "h:\Project Helix Prime Ecosystem\.venv\Scripts\python.exe" -m pytest -q -r a --basetemp="h:\Project Helix Prime Ecosystem\.pytest-tmp"
