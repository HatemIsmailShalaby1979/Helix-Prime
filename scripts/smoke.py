#!/usr/bin/env python3
"""
C0 smoke: one smoke command that works without Ollama.
Probes engines (py_compile + importlib), agents (AgentRegistry), orchestrator routing,
and cognitive_log. Writes evidence/baseline/smoke.log (gitignored) and prints summary.
Exit 0 = baseline green, non-zero = failure.
"""
from __future__ import annotations
import importlib.util
import py_compile
import sys
from pathlib import Path
import datetime
import json

ROOT = Path(__file__).resolve().parent.parent
evidence_dir = ROOT / "evidence" / "baseline"
evidence_dir.mkdir(parents=True, exist_ok=True)
log_path = evidence_dir / "smoke.log"

def log(msg: str):
    print(msg)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# fresh log
if log_path.exists():
    log_path.unlink()
log(f"Helix Prime C0 smoke — {datetime.datetime.now().isoformat()}")
log(f"ROOT={ROOT} python={sys.version.split()[0]}")

# 1) engines
ENGINE_MAP = {
    "WFM Forecasting": "engines/wfm/src/app_wfm.py",
    "RTA Command Center": "engines/rta/src/app.py",
    "CX Churn Sentinel": "engines/cx/src/risk_scorer.py",
    "B2B Onboarding": "engines/b2b/src/main.py",
    "Personnel Engine": "engines/personnel/src/main.py",
    "CRM Engine": "engines/crm/src/sales_pipeline.py",
}
ok_eng = 0
for name, rel in ENGINE_MAP.items():
    p = ROOT / rel
    loc = 0
    can = False
    detail = "not-found"
    try:
        loc = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
        py_compile.compile(str(p), doraise=True)
        mod_dir = str(p.parent)
        if mod_dir not in sys.path:
            sys.path.insert(0, mod_dir)
        spec = importlib.util.spec_from_file_location(name.replace(" ","_"), str(p))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            can = True
            detail = f"{loc} lines OK"
    except Exception as e:
        detail = f"ERROR {type(e).__name__}: {e}"
    status = "✓" if can else "✗"
    log(f"ENGINE {status} {name}: {detail}")
    if can:
        ok_eng += 1

# ensure project root on path for orchestration + agents + cockpit
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# 2) agents
sys.path.insert(0, str(ROOT / "app" / "command_center" / "agents"))
sys.path.insert(0, str(ROOT / "cockpit" / "memory"))
agents_ok = 0
try:
    from base_agent import AgentRegistry
    for name in ["SAMI","SUBY","PHILI","WILI"]:
        try:
            ag = AgentRegistry.get_agent(name)
            imported = ag is not None
            log(f"AGENT {'✓' if imported else '✗'} {name}: {'registered' if imported else 'missing'}")
            if imported:
                agents_ok += 1
        except Exception as e:
            log(f"AGENT ✗ {name}: {e}")
except Exception as e:
    log(f"AGENT probe failed: {e}")

# 3) orchestrator
try:
    from orchestration.orchestrator import Orchestrator
    o = Orchestrator()
    st = o.status()
    log(f"ORCHESTRATOR ✓: {json.dumps(st)}")
    # deterministic routing checks
    checks = [
        ("What is our hiring pipeline?", ["phili"]),
        ("service level is dropping", ["suby"]),
        ("churn risk for customers", ["suby"]),
        ("training competency gap", ["wili"]),
        ("strategic market expansion", ["sami"]),
        ("hello generic", ["sami","suby","phili"]),
    ]
    for msg, expected in checks:
        got = o._resolve_agents(msg)
        ok = got == expected or (expected == ["sami","suby","phili"] and set(got)==set(expected))
        log(f"  route {'✓' if ok else '✗'} {msg!r} -> {got} expected {expected}")
except Exception as e:
    log(f"ORCHESTRATOR ✗: {e}")

# 4) cockpit imports
for rel in ["cockpit/cockpit.py", "cockpit/memory/cognitive_log.py"]:
    p = ROOT / rel
    try:
        py_compile.compile(str(p), doraise=True)
        log(f"COCKPIT ✓ {rel} compiles")
    except Exception as e:
        log(f"COCKPIT ✗ {rel}: {e}")

# 5) pytest quick run (capture)
try:
    import subprocess
    r = subprocess.run([sys.executable,"-m","pytest","-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    log("PYTEST STDOUT:\n" + r.stdout[:2000])
    if r.stderr:
        log("PYTEST STDERR:\n" + r.stderr[:2000])
    log(f"PYTEST exit={r.returncode}")
except Exception as e:
    log(f"PYTEST run failed: {e}")

log(f"SUMMARY engines {ok_eng}/6 agents {agents_ok}/4")
# exit code based on baseline green
if ok_eng == 6 and agents_ok == 4:
    log("C0 SMOKE PASS")
    sys.exit(0)
else:
    log("C0 SMOKE FAIL")
    sys.exit(1)
