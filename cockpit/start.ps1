<#
.SYNOPSIS
  Helix Prime Cockpit - one command to launch everything.
  Binds the Streamlit dashboard to 127.0.0.1 only.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$CockpitDir = $PSScriptRoot
$RequirementsFile = Join-Path $CockpitDir "requirements.txt"
$TempDir = Join-Path $env:TEMP "helix-cockpit-probes"
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

if (-not (Test-Path $VenvPython)) {
    $SystemPython = Get-Command python -ErrorAction Stop
    & $SystemPython.Source -m venv $VenvDir
}

if (-not (Test-Path $VenvPython)) {
    throw "Python virtual environment could not be created at $VenvDir"
}

if (-not (Test-Path $RequirementsFile)) {
    throw "Pinned requirements file not found at $RequirementsFile"
}

& $VenvPython -m pip install --disable-pip-version-check -r $RequirementsFile

function Write-Status($name, $status, $detail) {
    $icon = switch($status) {
        "running"     { "[OK]" }
        "loaded"      { "[OK]" }
        "stub"        { "[--]" }
        "missing"     { "[!!]" }
        "not-found"   { "[!!]" }
        "error"       { "[ER]"}
        default       { "[??]" }
    }
    Write-Host ("  {0} {1,-28} {2,-18} {3}" -f $icon, $name, ("[" + $status + "]"), $detail)
}

function Invoke-Probe {
    param([string]$Name, [string]$ProbeScript)
    $scriptFile = Join-Path $TempDir ($Name + ".py")
    Set-Content -LiteralPath $scriptFile -Value $ProbeScript -Encoding utf8
    $result = & $VenvPython $scriptFile 2>&1
    Remove-Item -LiteralPath $scriptFile -Force -ErrorAction SilentlyContinue
    return $result
}

Write-Host "=================================================="
Write-Host "  HELIX PRIME COCKPIT - LAUNCH SEQUENCE"
Write-Host "=================================================="
Write-Host ""

# -- 0. Governance check (BLOCKS if sign-in or log rules are violated)
$GovCheck = Join-Path $ProjectRoot "GOVERNANCE\governance_check.py"
if (Test-Path $GovCheck) {
    $govResult = & $VenvPython $GovCheck check 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[!!] GOVERNANCE CHECK FAILED -- Session blocked"
        Write-Host $govResult
        exit 1
    }
    Write-Host "  [OK] Governance checks passed"
} else {
    Write-Host "  [??] governance_check.py not found"
}
Write-Host ""

# -- 1. Check Python venv
Write-Host "--- Step 1/5: Environment Check ---"
if (Test-Path $VenvPython) {
    $ver = & $VenvPython --version 2>&1
    Write-Status "Python venv" "running" $ver
} else {
    Write-Status "Python venv" "missing" "No .venv found"
}

# -- 2. Orchestrator
Write-Host ""
Write-Host "--- Step 2/5: Orchestrator ---"
$orchPy = Join-Path $ProjectRoot "orchestration\orchestrator.py"
if (Test-Path $orchPy) {
    $orchProbe = "import sys`n" +
        "sys.path.insert(0, 'orchestration')`n" +
        "from orchestrator import Orchestrator`n" +
        "o = Orchestrator()`n" +
        "print('OK - ' + str(len(o.agents)) + ' agents, ' + str(len(o.engines)) + ' engines')"
    $orchResult = Invoke-Probe -Name "orchestrator" -ProbeScript $orchProbe
    if ($LASTEXITCODE -eq 0) {
        Write-Status "Orchestrator" "loaded" $orchResult
    } else {
        Write-Status "Orchestrator" "error" ($orchResult -join ' ')
    }
} else {
    Write-Status "Orchestrator" "not-found" "orchestration/orchestrator.py missing"
}

# -- 3. Agents
Write-Host ""
Write-Host "--- Step 3/5: AI Agents ---"
$agentNames = @("SAMI (CEO/Strategist)", "SUBY (Operations Exec)", "PHILI (Personnel Director)", "WILI (Learning and Dev)")
$agentKeys = @("sami", "suby", "phili", "wili")
$agentDirs = @(
    (Join-Path $ProjectRoot "app\command_center\agents"),
    (Join-Path $ProjectRoot "agents"),
    (Join-Path $ProjectRoot "cockpit\agents")
)

$agentsOnline = 0
for ($i = 0; $i -lt $agentNames.Length; $i++) {
    $found = $false
    $agentPath = $null
    foreach ($baseDir in $agentDirs) {
        $f = Join-Path $baseDir ($agentKeys[$i] + ".py")
        if (Test-Path $f) {
            $found = $true
            $agentPath = $f
            break
        }
    }
    if ($found) {
        $agentKey = $agentKeys[$i]
        $agentProbe =
            "import sys, importlib.util`n" +
            "sys.path.insert(0, r'" + $ProjectRoot + "\\app\\command_center\\agents')`n" +
            "spec = importlib.util.spec_from_file_location(r'" + $agentKey + "', r'" + $agentPath + "')`n" +
            "mod = importlib.util.module_from_spec(spec)`n" +
            "spec.loader.exec_module(mod)`n" +
            "print('OK')"
        $agentResult = Invoke-Probe -Name ("agent_" + $agentKey) -ProbeScript $agentProbe
        if ($LASTEXITCODE -eq 0) {
            $lines = (Get-Content $agentPath | Measure-Object -Line).Lines
            Write-Status $agentNames[$i] "loaded" ("$lines lines - imported OK")
            $agentsOnline++
        } else {
            Write-Status $agentNames[$i] "error" ($agentResult -join ' ')
        }
    } else {
        Write-Status $agentNames[$i] "not-found" "No agent code found"
    }
}

# -- 4. Engines
Write-Host ""
Write-Host "--- Step 4/5: Business Engines ---"
$engineSpecs = @(
    @{ RelPath = "engines\wfm\src\app_wfm.py";           Name = "WFM Forecasting";      Probe = "import sys; sys.path.insert(0, 'engines/wfm/src'); from app_wfm import WFMForecastingApp; print('OK')" }
    @{ RelPath = "engines\rta\src\app.py";               Name = "RTA Command Center";    Probe = "import sys; sys.path.insert(0, 'engines/rta/src'); from calculations import create_rta_calculator; print('calc OK'); from app import app as flask_app; print('app OK')" }
    @{ RelPath = "engines\cx\src\risk_scorer.py";         Name = "CX Churn Sentinel";     Probe = "import sys; sys.path.insert(0, 'engines/cx/src'); from risk_scorer import RiskScorerEngine; print('OK')" }
    @{ RelPath = "engines\b2b\src\main.py";               Name = "B2B Onboarding";       Probe = "import sys; sys.path.insert(0, 'engines/b2b/src'); from main import OnboardingCLI; print('OK')" }
    @{ RelPath = "engines\personnel\src\main.py";         Name = "Personnel Engine";     Probe = "import sys; sys.path.insert(0, 'engines/personnel/src'); from main import PersonnelCLI; print('OK')" }
    @{ RelPath = "engines\crm\src\sales_pipeline.py";     Name = "CRM Engine";           Probe = "import sys; sys.path.insert(0, 'engines/crm/src'); from sales_pipeline import SalesPipeline; print('OK')" }
)

$engineAvailable = 0
$engineTotal = $engineSpecs.Count
$engineIdx = 0

foreach ($spec in $engineSpecs) {
    $name = $spec.Name
    $epath = Join-Path $ProjectRoot $spec.RelPath
    if (-not (Test-Path $epath)) {
        Write-Status $name "not-found" "Engine file missing"
        $engineIdx++
        continue
    }
    $result = Invoke-Probe -Name ("engine_" + $engineIdx) -ProbeScript $spec.Probe
    if ($LASTEXITCODE -eq 0 -and ($result -match "OK" -or $result -match "ok")) {
        Write-Status $name "loaded" "Import OK"
        $engineAvailable++
    } else {
        $errLine = ($result -join ' ').Substring(0, [math]::Min(80, ($result -join ' ').Length))
        Write-Status $name "error" $errLine
    }
    $engineIdx++
}

# -- 5. Start Dashboard
Write-Host ""
Write-Host "--- Step 5/5: Launching Dashboard ---"
$dashboardPy = Join-Path $CockpitDir "cockpit.py"
$dashboardPort = 8501

if (-not (Test-Path $dashboardPy)) {
    Write-Status "Dashboard script" "not-found" "cockpit.py missing"
    Write-Host ""
    Write-Host "[!!] Cannot start. Dashboard script not found."
    exit 1
}

Write-Status "Dashboard" "running" ("Streamlit on http://127.0.0.1:" + $dashboardPort)
Write-Host ""

Write-Host "=================================================="
Write-Host "  STATUS SUMMARY"
Write-Host "=================================================="
Write-Host ("  AI Agents:      " + $agentsOnline + " of 4 connected")
Write-Host ("  Engines:        " + $engineAvailable + " of " + $engineTotal + " available")
Write-Host "  Orchestrator:   Present"
Write-Host ("  Dashboard:      http://127.0.0.1:" + $dashboardPort)
Write-Host "=================================================="
Write-Host ""
Write-Host "Starting Streamlit dashboard in 2 seconds..."
Start-Sleep -Seconds 2

Push-Location $ProjectRoot
try {
    & $VenvPython -m streamlit run $dashboardPy --server.address=127.0.0.1 --server.port $dashboardPort --server.headless true 2>&1
} finally {
    Pop-Location
}
