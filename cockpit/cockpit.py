import importlib
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "app" / "command_center" / "agents")
)
sys.path.insert(0, str(Path(__file__).resolve().parent / "memory"))

# Force-reload modules to pick up edits after Streamlit hot-reload
for _mod in ["base_agent", "cognitive_log"]:
    if _mod in sys.modules:
        del sys.modules[_mod]
importlib.invalidate_caches()

from base_agent import (  # noqa: E402
    AgentRegistry,
)
from cognitive_log import (  # noqa: E402
    LogEntry,
    get_all_agents,
    get_session_ids,
    log_interaction,
    query_interactions,
)

_gov_check = (
    Path(__file__).resolve().parent.parent / "GOVERNANCE" / "governance_check.py"
)
if _gov_check.exists():
    import subprocess

    _result = subprocess.run(
        [sys.executable, str(_gov_check), "check"],
        capture_output=True,
        text=True,
        cwd=str(_gov_check.parent.parent),
    )
    if _result.returncode != 0:
        st.error("GOVERNANCE CHECK FAILED أ¢â‚¬â€‌ Session blocked")
        st.code(_result.stdout + _result.stderr)
        st.stop()

try:
    import urllib.request

    _req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
    with urllib.request.urlopen(_req, timeout=3) as _resp:
        _ollama_ok = _resp.status == 200
except (OSError, ValueError):
    _ollama_ok = False

st.set_page_config(page_title="Helix Prime Operations Control Room", layout="wide")

st.markdown(
    """
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #E0E0E0; padding: 0; margin-bottom: 0; }
    .main-sub { font-size: 0.85rem; color: #777; margin-bottom: 1.2rem; }
    .section-hdr {
        font-size: 0.9rem; font-weight: 700; color: #00BFA6;
        text-transform: uppercase; letter-spacing: 2px;
        margin-top: 0.5rem; margin-bottom: 0.75rem;
        border-bottom: 1px solid #252A38; padding-bottom: 0.3rem;
    }
    .agent-live {
        display: inline-flex; align-items: center; gap: 6px;
        font-size: 0.8rem; font-weight: 600; margin-bottom: 6px;
    }
    .dot-online { width: 9px; height: 9px; border-radius: 50%; background: #00C853; display: inline-block; }
    .dot-offline { width: 9px; height: 9px; border-radius: 50%; background: #FF4444; display: inline-block; }
    .label-online { color: #00C853; }
    .label-offline { color: #FF4444; }
    .engine-title { font-size: 0.9rem; font-weight: 700; color: #E0E0E0; }
    .engine-desc { font-size: 0.72rem; color: #888; line-height: 1.35; margin: 1px 0 4px 0; }
    .engine-meta { font-size: 0.7rem; color: #555; }
    .agent-response-box {
        background: #0B0E14; border: 1px solid #252A38; border-radius: 6px;
        padding: 10px 14px; margin-top: 8px;
        font-size: 0.8rem; color: #BBB; max-height: 250px; overflow-y: auto;
        line-height: 1.45;
    }
    .reasoning-box {
        background: #0D1117; border: 1px solid #1E3050; border-left: 3px solid #FFA726;
        border-radius: 4px; padding: 8px 12px; margin: 8px 0;
        font-size: 0.75rem; color: #888; font-family: monospace;
        line-height: 1.4; max-height: 200px; overflow-y: auto;
    }
    .inter-call-box {
        background: #0D1117; border: 1px solid #2E4A3A; border-left: 3px solid #66BB6A;
        border-radius: 4px; padding: 8px 12px; margin: 8px 0;
        font-size: 0.75rem; color: #A5D6A7; font-family: monospace;
    }
    .agent-bar {
        background: #131823; border: 1px solid #252A38; border-radius: 6px;
        padding: 12px 16px; margin-bottom: 16px;
    }
    .agent-tag {
        display: inline-block; padding: 2px 8px; border-radius: 10px;
        font-size: 0.7rem; font-weight: 600; margin: 2px 4px 2px 0;
        background: #1A2332; color: #00BFA6; border: 1px solid #253545;
    }
    .sim-step {
        background: #0B0E14; border: 1px solid #252A38; border-radius: 6px;
        padding: 10px 14px; margin: 8px 0;
        border-left: 4px solid #00BFA6;
    }
    .sim-step.completed { border-left-color: #66BB6A; }
    .stProgress > div > div > div > div { background-color: #00BFA6; }
    div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {
        background-color: #0B0E14 !important; border: 1px solid #252A38 !important;
        border-radius: 4px !important; color: #E0E0E0 !important; font-size: 0.8rem !important;
    }
    div.stButton > button {
        background: #00BFA6 !important; color: #0E1117 !important;
        font-weight: 700 !important; font-size: 0.75rem !important;
        border: none !important; border-radius: 4px !important;
    }
    div.stButton > button:hover { background: #00D9B0 !important; }
</style>
""",
    unsafe_allow_html=True,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CLIENTS = {
    "Account Alpha": {
        "agents": 420,
        "calls_per_day": 8500,
        "shrinkage": 0.12,
        "avg_handle_time": 480,
        "service_level": 0.78,
        "attrition": 0.18,
        "open_positions": 45,
        "onboarding_pipeline": 120,
    },
    "Account Beta": {
        "agents": 180,
        "calls_per_day": 2400,
        "shrinkage": 0.15,
        "avg_handle_time": 520,
        "service_level": 0.80,
        "attrition": 0.22,
        "open_positions": 22,
        "onboarding_pipeline": 55,
    },
    "Account Gamma": {
        "agents": 650,
        "calls_per_day": 12000,
        "shrinkage": 0.10,
        "avg_handle_time": 420,
        "service_level": 0.85,
        "attrition": 0.14,
        "open_positions": 60,
        "onboarding_pipeline": 180,
    },
}

AGENTS = [
    {"name": "SAMI", "role": "CEO / Strategist", "color": "#00BFA6"},
    {"name": "SUBY", "role": "Operations Executive", "color": "#42A5F5"},
    {"name": "PHILI", "role": "Personnel Director", "color": "#FFCA28"},
    {"name": "WILI", "role": "L&D Director", "color": "#AB47BC"},
]

ENGINE_DESCRIPTIONS = {
    "WFM Forecasting": "Forecasts call volume, staffing requirements, and schedule adherence by hour",
    "RTA Command Center": "Real-time agent adherence tracking and intraday performance monitoring",
    "CX Churn Sentinel": "Customer satisfaction trends, churn risk scoring, and sentiment analysis by day",
    "B2B Onboarding": "Client account pipeline tracking through onboarding stages to activation",
    "Personnel Engine": "Workforce composition by role, open positions, pipeline, and time-to-fill",
    "CRM Engine": "Sales pipeline value, deal stages, win rates, and revenue forecasting",
}

ENGINE_MODULE_PATHS = {
    "WFM Forecasting": "engines\\wfm\\src\\app_wfm.py",
    "RTA Command Center": "engines\\rta\\src\\app.py",
    "CX Churn Sentinel": "engines\\cx\\src\\risk_scorer.py",
    "B2B Onboarding": "engines\\b2b\\src\\main.py",
    "Personnel Engine": "engines\\personnel\\src\\main.py",
    "CRM Engine": "engines\\crm\\src\\sales_pipeline.py",
}

ENGINE_NAMES = list(ENGINE_DESCRIPTIONS.keys())


def get_agent_online(agent_name):
    return _ollama_ok


def probe_agent_connection(agent_name: str) -> dict:
    result = {
        "name": agent_name,
        "status": "unknown",
        "detail": "",
        "can_run": False,
        "lines": 0,
    }
    agent_path = PROJECT_ROOT / "app" / "command_center" / "agents" / "base_agent.py"
    if not agent_path.exists():
        result["detail"] = "Agent base not found"
        return result
    result["lines"] = len(agent_path.read_text().splitlines())
    try:
        from base_agent import AgentRegistry

        agent = AgentRegistry.get_agent(agent_name)
        result["can_run"] = agent is not None and _ollama_ok
        result["status"] = "loaded" if agent else "not-registered"
        result["detail"] = f"{result['lines']} lines أ¢â‚¬â€‌ OK"
    except Exception as e:  # noqa: BLE001 - import probe, keep each agent independent
        result["status"] = "error"
        result["detail"] = f"Import failed: {type(e).__name__}"
    return result


agent_probes = {}
for a in AGENTS:
    agent_probes[a["name"]] = probe_agent_connection(a["name"])


def probe_engine(ename: str, module_path: str) -> dict:
    full = Path(PROJECT_ROOT) / module_path
    r = {"name": ename, "status": "not-found", "detail": "", "loc": 0, "can_run": False}
    if not full.exists():
        r["detail"] = "File not found"
        return r
    r["loc"] = len(full.read_text().splitlines())
    try:
        import py_compile

        py_compile.compile(str(full), doraise=True)
    except py_compile.PyCompileError:
        r["status"] = "error"
        return r
    try:
        mod_dir = str(full.parent)
        if mod_dir not in sys.path:
            sys.path.insert(0, mod_dir)
        spec = importlib.util.spec_from_file_location(ename, str(full))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            r["status"] = "loaded"
            r["can_run"] = True
            r["detail"] = f"{r['loc']} lines أ¢â‚¬â€‌ OK"
    except Exception:  # noqa: BLE001 - engine load probe, report status only
        r["status"] = "error"
    return r


def _add_to_path(*segments):
    p = PROJECT_ROOT
    for s in segments:
        p = p / s
    dir_path = str(p) if p.is_dir() else str(p.parent)
    if dir_path not in sys.path:
        sys.path.insert(0, dir_path)


def call_wfm(client):
    _add_to_path("engines", "wfm", "src")
    c = CLIENTS.get(client, {})
    try:
        from erlang_c import ErlangCParameters, create_erlang_c_engine
    except ImportError as ex:
        return None, f"ImportError: {ex}"
    try:
        params = ErlangCParameters(
            arrival_rate=c.get("calls_per_day", 5000) / 17,
            average_handling_time=c.get("avg_handle_time", 480)
            / 60,  # seconds أ¢â€ â€™ minutes
            service_level_target=c.get("service_level", 0.80),
            average_calls_per_period=17,
        )
        engine = create_erlang_c_engine(
            params.arrival_rate,
            params.average_handling_time,
            params.service_level_target,
            params.average_calls_per_period,
        )
        result = engine.optimize_agents()
        rows = [
            {"Parameter": "Optimal Agents", "Value": result.optimal_agents},
            {
                "Parameter": "Probability Waiting",
                "Value": round(result.probability_waiting, 4),
            },
            {
                "Parameter": "Avg Speed of Answer (min)",
                "Value": round(result.average_speed_of_answer, 1),
            },
            {
                "Parameter": "Service Level Achieved",
                "Value": round(result.service_level_achieved, 4),
            },
            {
                "Parameter": "Traffic Intensity",
                "Value": round(result.traffic_intensity, 3),
            },
            {"Parameter": "Utilization", "Value": round(result.utilization, 4)},
        ]
        return pd.DataFrame(rows), None
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as ex:
        return None, f"RuntimeError: {ex}"


def call_rta(client):
    _add_to_path("engines", "rta", "src")
    c = CLIENTS.get(client, {})
    try:
        from calculations import create_rta_calculator
    except ImportError as ex:
        return None, f"ImportError: {ex}"
    import pandas as pd

    np.random.seed(hash(client + "rta") % 2**32)
    n_agents = max(5, c.get("agents", 100) // 10)
    schedule_data = pd.DataFrame(
        {
            "agent_id": [f"A{i}" for i in range(n_agents)],
            "scheduled_min": np.random.randint(420, 500, n_agents),
        }
    )
    actual_data = pd.DataFrame(
        {
            "agent_id": [f"A{i}" for i in range(n_agents)],
            "logged_min": np.random.randint(300, 500, n_agents),
            "productive_min": np.random.randint(250, 450, n_agents),
        }
    )
    try:
        calc = create_rta_calculator(adherence_threshold=0.85, variance_threshold=2.0)
        result = calc.analyze(schedule_data, actual_data)
        adj = getattr(result, "adherence_metrics", {})
        sm = getattr(result, "schedule_metrics", {})
        rows = [
            {
                "Metric": "Overall Adherence %",
                "Value": round(adj.get("overall", 0), 1) if adj else "N/A",
            },
            {
                "Metric": "Schedule Efficiency %",
                "Value": round(sm.get("efficiency", 0), 1) if sm else "N/A",
            },
        ]
        return pd.DataFrame(rows), None
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as ex:
        return None, f"RuntimeError: {ex}"


def call_cx(client):
    _add_to_path("engines", "cx", "src")
    try:
        from risk_scorer import create_risk_scorer
    except ImportError as ex:
        return None, f"ImportError: {ex}"
    import random as _r

    sample_data = [
        {
            "customer_id": f"C{i}",
            "csat": round(3.0 + _r.random() * 1.8, 2),
            "fcr": round(0.5 + _r.random() * 0.45, 2),
            "churn_risk": round(_r.random() * 0.3, 3),
            "sentiment": round(-0.2 + _r.random() * 1.0, 2),
        }
        for i in range(10)
    ]
    try:
        scorer = create_risk_scorer()
        result = scorer.score_customers(sample_data)
        overall = getattr(result, "overall_risk_score", "N/A")
        high_risk = getattr(result, "high_risk_customers", [])
        rows = [
            {"Metric": "Overall Risk Score", "Value": overall},
            {"Metric": "High Risk Customers", "Value": len(high_risk)},
        ]
        return pd.DataFrame(rows), None
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as ex:
        return None, f"RuntimeError: {ex}"


def call_b2b(client):
    _add_to_path("engines", "b2b", "src")
    try:
        from automator import ClientProfile, OnboardingAutomator
    except ImportError as ex:
        return None, f"ImportError: {ex}"
    try:
        automator = OnboardingAutomator()
        cid = client.replace(" ", "_").lower()
        profile = ClientProfile(
            client_id=cid,
            name=client,
            industry="Technology",
            size="Mid-Market",
            complexity="Standard",
            requirements=["Onboarding", "Training", "Go-Live Support"],
        )
        automator.add_client(profile)
        summary = automator.get_client_summary(cid)
        rows = [{"Field": k, "Value": str(v)} for k, v in (summary or {}).items()]
        return pd.DataFrame(rows) if rows else pd.DataFrame({"Note": ["No data"]}), None
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as ex:
        return None, f"RuntimeError: {ex}"


def call_personnel(client):
    _add_to_path("engines", "personnel", "src")
    try:
        from main import PipelineManager
    except ImportError as ex:
        return None, f"ImportError: {ex}"
    try:
        mgr = PipelineManager()
        analytics = mgr.get_pipeline_analytics()
        rows = [{"Field": k, "Value": str(v)} for k, v in (analytics or {}).items()]
        return pd.DataFrame(rows) if rows else pd.DataFrame({"Note": ["No data"]}), None
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as ex:
        return None, f"RuntimeError: {ex}"


def call_crm(client):
    _add_to_path("engines", "crm", "src")
    try:
        from sales_pipeline import create_sales_pipeline
    except ImportError as ex:
        return None, f"ImportError: {ex}"
    try:
        pipeline = create_sales_pipeline()
        analytics = pipeline.get_sales_analytics()
        rows = [{"Metric": k, "Value": str(v)} for k, v in (analytics or {}).items()]
        return pd.DataFrame(rows) if rows else pd.DataFrame({"Note": ["No data"]}), None
    except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as ex:
        return None, f"RuntimeError: {ex}"


ENGINE_CALLERS = {
    "WFM Forecasting": call_wfm,
    "RTA Command Center": call_rta,
    "CX Churn Sentinel": call_cx,
    "B2B Onboarding": call_b2b,
    "Personnel Engine": call_personnel,
    "CRM Engine": call_crm,
}


def main():
    """Main entry point for the Streamlit application."""
    if not _ollama_ok:
        st.markdown(
            "<div style='background:#6B1414; padding:10px 18px; border-radius:6px; "
            "border-left:4px solid #FF4444; margin-bottom:12px;'>"
            "<span style='font-weight:700; color:#FF6666;'>&#9888; Ollama OFFLINE</span>"
            "<span style='color:#FFAAAA; font-size:0.85rem;'> Agents cannot respond.</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='main-header'>Helix Prime Operations Control Room</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='main-sub'>Session run: {datetime.now().strftime('%H:%M:%S')}</div>",
        unsafe_allow_html=True,
    )

    if "session_id" not in st.session_state:
        st.session_state.session_id = (
            datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(uuid.uuid4())[:8]
        )
    if "sim_client_profile" not in st.session_state:
        st.session_state.sim_client_profile = None
    if "sim_steps" not in st.session_state:
        st.session_state.sim_steps = []

    with st.sidebar:
        st.markdown(
            "<div style='font-size:1.1rem; font-weight:700; color:#00BFA6; letter-spacing:1px; margin-bottom:4px;'>CONTROL ROOM</div>",
            unsafe_allow_html=True,
        )
        page = st.radio(
            "",
            [
                "Dashboard",
                "Agents",
                "Engines",
                "Memory",
                "System Status",
                "Client Simulation",
            ],
            label_visibility="collapsed",
        )
    st.divider()
    client = st.selectbox("Client Context", list(CLIENTS.keys()))
    st.divider()
    total_online = sum(
        1 for a in AGENTS if agent_probes[a["name"]]["can_run"] and _ollama_ok
    )
    st.metric("Agents Online", f"{total_online}/{len(AGENTS)}")
    engines_ok = sum(
        1 for e in ENGINE_NAMES if probe_engine(e, ENGINE_MODULE_PATHS[e])["can_run"]
    )
    st.metric("Engines Loaded", f"{engines_ok}/{len(ENGINE_NAMES)}")
    st.caption(f"Session: {st.session_state.session_id}")

    # أ¢â€‌â‚¬أ¢â€‌â‚¬ PERMANENT "ASK ANY AGENT" BAR أ¢â‚¬â€‌ visible on every page أ¢â€‌â‚¬أ¢â€‌â‚¬أ¢â€‌â‚¬أ¢â€‌â‚¬أ¢â€‌â‚¬أ¢â€‌â‚¬أ¢â€‌â‚¬أ¢â€‌â‚¬
    st.markdown("<div class='agent-bar'>", unsafe_allow_html=True)
    ask_cols = st.columns([4, 1, 0.3])
    with ask_cols[0]:
        global_query = st.text_input(
            "Ask any agent",
            placeholder="Ask SAMI, SUBY, PHILI, or WILI anything...",
            label_visibility="collapsed",
            key="global_agent_query",
        )
    with ask_cols[1]:
        global_agent_choice = st.selectbox(
            "",
            ["SAMI", "SUBY", "PHILI", "WILI"],
            label_visibility="collapsed",
            key="global_agent_choice",
        )
    with ask_cols[2]:
        global_submit = st.button("Go", key="global_agent_submit")
    st.markdown("</div>", unsafe_allow_html=True)

    if global_submit and global_query:
        agent_name = global_agent_choice
        with st.spinner(f"Consulting {agent_name}..."):
            agent = AgentRegistry.get_agent(agent_name)
            if agent and _ollama_ok:
                agent.session_id = st.session_state.session_id
                agent.client_context = client
                try:
                    result = agent.process_request(global_query, _recursion_depth=0)
                except TypeError:
                    result = agent.process_request(global_query)
                reasoning = getattr(agent, "_last_reasoning", None)
                if reasoning:
                    with st.expander("Show agent reasoning"):
                        st.markdown(
                            f"<div class='reasoning-box'>{reasoning}</div>",
                            unsafe_allow_html=True,
                        )
                inter_calls = getattr(agent, "_inter_agent_calls", [])
                if inter_calls:
                    for call in inter_calls:
                        st.markdown(
                            f"<div class='inter-call-box'>أ¢â€ â€™ Called {call['agent']}: {call['input'][:80]}...</div>",
                            unsafe_allow_html=True,
                        )
                        if call.get("reasoning"):
                            with st.expander(f"Show {call['agent']} reasoning"):
                                st.markdown(
                                    f"<div class='reasoning-box'>{call['reasoning']}</div>",
                                    unsafe_allow_html=True,
                                )
                st.markdown(
                    f"<div class='agent-response-box'><b>{agent_name}:</b> {result}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.error("Agent unavailable or Ollama offline.")

    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    # DASHBOARD PAGE
    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    if page == "Dashboard":
        st.markdown(
            "<div class='section-hdr'>Business Engines</div>", unsafe_allow_html=True
        )
        eng_cols = st.columns(3, gap="small")
        for i, ename in enumerate(ENGINE_NAMES):
            pr = probe_engine(ename, ENGINE_MODULE_PATHS[ename])
            icon = "ظ‹ع؛ع؛آ¢" if pr["can_run"] else "ظ‹ع؛â€‌آ´"
            with eng_cols[i % 3]:
                with st.container(border=True):
                    st.markdown(
                        f"<div class='engine-title'>{icon} {ename}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='engine-desc'>{ENGINE_DESCRIPTIONS[ename]}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='engine-meta'>{pr['status']} &middot; {pr['loc']} lines</div>",
                        unsafe_allow_html=True,
                    )

        st.markdown("<div class='section-hdr'>AI Agents</div>", unsafe_allow_html=True)
        agent_cols = st.columns(2, gap="medium")
        for i, acfg in enumerate(AGENTS):
            aname = acfg["name"]
            probe = agent_probes[aname]
            is_online = probe["can_run"] and _ollama_ok
            dot_class = "dot-online" if is_online else "dot-offline"
            label_class = "label-online" if is_online else "label-offline"
            with agent_cols[i % 2]:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='font-size:0.85rem; font-weight:700; color:#E0E0E0;'>{aname}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div style='font-size:0.72rem; color:{acfg['color']}; margin-bottom:2px;'>{acfg['role']}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='agent-live'><span class='{dot_class}'></span><span class='{label_class}'>Online</span><span style='color:#555;'>&middot; {probe['detail']}</span></div>"
                        if is_online
                        else f"<div class='agent-live'><span class='{dot_class}'></span><span class='{label_class}'>Offline</span></div>",
                        unsafe_allow_html=True,
                    )
                    q_key = f"dq_{aname}"
                    btn_key = f"db_{aname}"
                    resp_key = f"dr_{aname}"
                    q = st.text_input(
                        "",
                        placeholder=f"Ask {aname}...",
                        label_visibility="collapsed",
                        key=q_key,
                    )
                    ask = st.button("Ask", key=btn_key, type="primary", width="stretch")
                    if ask and q:
                        if is_online:
                            agent = AgentRegistry.get_agent(aname)
                            if agent:
                                agent.session_id = st.session_state.session_id
                                agent.client_context = client
                                try:
                                    r = agent.process_request(q, _recursion_depth=0)
                                except TypeError:
                                    r = agent.process_request(q)
                                reasoning = getattr(agent, "_last_reasoning", None)
                                inter_calls = getattr(agent, "_inter_agent_calls", [])
                                st.session_state[resp_key] = r
                                st.session_state[f"{resp_key}_reasoning"] = reasoning
                                st.session_state[f"{resp_key}_calls"] = inter_calls
                        else:
                            st.session_state[resp_key] = "Agent is offline"
                    if st.session_state.get(resp_key):
                        if st.session_state.get(f"{resp_key}_reasoning"):
                            with st.expander("Show agent reasoning"):
                                st.markdown(
                                    f"<div class='reasoning-box'>{st.session_state[f'{resp_key}_reasoning']}</div>",
                                    unsafe_allow_html=True,
                                )
                        calls = st.session_state.get(f"{resp_key}_calls", [])
                        for call in calls:
                            st.markdown(
                                f"<div class='inter-call-box'>أ¢â€ â€™ Called {call['agent']}</div>",
                                unsafe_allow_html=True,
                            )
                            if call.get("reasoning"):
                                with st.expander(f"Show {call['agent']} reasoning"):
                                    st.markdown(
                                        f"<div class='reasoning-box'>{call['reasoning']}</div>",
                                        unsafe_allow_html=True,
                                    )
                        st.markdown(
                            f"<div class='agent-response-box'>{st.session_state[resp_key]}</div>",
                            unsafe_allow_html=True,
                        )

        st.markdown(
            "<div class='section-hdr'>Client Snapshot</div>", unsafe_allow_html=True
        )
        c = CLIENTS[client]
        cols = st.columns(5)
        cols[0].metric("Agent Headcount", c["agents"])
        cols[1].metric("Avg Handle Time", f"{c['avg_handle_time']}s")
        cols[2].metric("Service Level", f"{c['service_level']:.0%}")
        cols[3].metric("Attrition", f"{c['attrition']:.0%}")
        cols[4].metric("Shrinkage", f"{c['shrinkage']:.0%}")

    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    # AGENTS PAGE
    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    elif page == "Agents":
        st.markdown(
            "<div class='section-hdr'>Agent Chat Panels</div>", unsafe_allow_html=True
        )
        st.markdown(
            "<div style='font-size:0.75rem; color:#888; margin-bottom:12px;'>Agents show collapsible reasoning traces (if supported by model) and real inter-agent calls.</div>",
            unsafe_allow_html=True,
        )
        for acfg in AGENTS:
            aname = acfg["name"]
            probe = agent_probes[aname]
            is_online = probe["can_run"] and _ollama_ok
            with st.container(border=True):
                col_a, col_b = st.columns([1, 4])
                with col_a:
                    st.markdown(
                        f"<div style='font-size:1.2rem; font-weight:700; color:{acfg['color']}'>{aname}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div style='font-size:0.8rem; color:#00BFA6;'>{acfg['role']}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<div class='agent-live'><span class='{'dot-online' if is_online else 'dot-offline'}'></span><span class='{'label-online' if is_online else 'label-offline'}'>{'Online' if is_online else 'Offline'}</span></div>",
                        unsafe_allow_html=True,
                    )
                with col_b:
                    q_key = f"ag_q_{aname}"
                    btn_key = f"ag_b_{aname}"
                    resp_key = f"ag_r_{aname}"
                    q = st.text_area(
                        "",
                        placeholder=f"Ask {aname} a question...",
                        label_visibility="collapsed",
                        height=80,
                        key=q_key,
                    )
                    ask = st.button("Submit", key=btn_key, type="primary")
                    if ask and q:
                        if is_online:
                            agent = AgentRegistry.get_agent(aname)
                            if agent:
                                agent.session_id = st.session_state.session_id
                                agent.client_context = client
                                try:
                                    r = agent.process_request(q, _recursion_depth=0)
                                except TypeError:
                                    r = agent.process_request(q)
                                reasoning = getattr(agent, "_last_reasoning", None)
                                inter_calls = getattr(agent, "_inter_agent_calls", [])
                                st.session_state[resp_key] = r
                                st.session_state[f"{resp_key}_reasoning"] = reasoning
                                st.session_state[f"{resp_key}_calls"] = inter_calls
                        else:
                            st.session_state[resp_key] = "Agent is offline."
                    if st.session_state.get(resp_key):
                        if st.session_state.get(f"{resp_key}_reasoning"):
                            with st.expander("Show reasoning trace"):
                                st.markdown(
                                    f"<div class='reasoning-box'>{st.session_state[f'{resp_key}_reasoning']}</div>",
                                    unsafe_allow_html=True,
                                )
                        calls = st.session_state.get(f"{resp_key}_calls", [])
                        for call in calls:
                            st.markdown(
                                f"<div class='inter-call-box'>أ¢â€ â€™ <b>{call['agent']}</b> consulted | Input: {call['input'][:60]}...</div>",
                                unsafe_allow_html=True,
                            )
                        st.markdown(
                            f"<div class='agent-response-box'>{st.session_state[resp_key]}</div>",
                            unsafe_allow_html=True,
                        )

    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    # ENGINES PAGE
    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    elif page == "Engines":
        st.markdown(
            f"<div class='section-hdr'>Engine Data أ¢â‚¬â€‌ {client}</div>",
            unsafe_allow_html=True,
        )
        engine_tabs = st.tabs(ENGINE_NAMES)
        for tab_idx, tab in enumerate(engine_tabs):
            ename = ENGINE_NAMES[tab_idx]
            with tab:
                pr = probe_engine(ename, ENGINE_MODULE_PATHS[ename])
                icon = "ظ‹ع؛ع؛آ¢" if pr["can_run"] else "ظ‹ع؛â€‌آ´"
                st.markdown(
                    f"<div style='font-size:0.85rem;'><b>{icon} Status:</b> {pr['status']} &middot; {pr['loc']} lines &middot; {pr['detail']}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='font-size:0.75rem; color:#888; margin-bottom:8px;'>{ENGINE_DESCRIPTIONS[ename]}</div>",
                    unsafe_allow_html=True,
                )
                _result = ENGINE_CALLERS[ename](client)
                if _result[1] is not None:
                    st.error(_result[1])
                elif _result[0] is not None and not _result[0].empty:
                    df = _result[0]
                    st.dataframe(df, width="stretch", hide_index=True)
                    num = df.select_dtypes(include=[np.number]).columns.tolist()
                    if num:
                        st.caption("Numerical Summary")
                        st.dataframe(df[num].describe(), width="stretch")
                else:
                    st.warning("No data.")

    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    # MEMORY PAGE أ¢â‚¬â€‌ NEW
    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    elif page == "Memory":
        st.markdown(
            "<div class='section-hdr'>Cognitive Memory Log</div>",
            unsafe_allow_html=True,
        )

        mem_cols = st.columns([2, 2, 2, 3])
        with mem_cols[0]:
            filter_agent = st.selectbox(
                "Filter by agent", ["All"] + get_all_agents(), key="mem_agent"
            )
        with mem_cols[1]:
            filter_session = st.selectbox(
                "Filter by session", ["All"] + get_session_ids(), key="mem_session"
            )
        with mem_cols[2]:
            date_range = st.date_input(
                "Date range",
                [datetime.now() - timedelta(days=7), datetime.now()],
                key="mem_date",
            )
        with mem_cols[3]:
            search_text = st.text_input(
                "Search in content",
                placeholder="Search interactions...",
                key="mem_search",
            )

        agent_param = None if filter_agent == "All" else filter_agent
        session_param = None if filter_session == "All" else filter_session
        start_param = date_range[0].isoformat() if len(date_range) > 0 else None
        end_param = date_range[1].isoformat() if len(date_range) > 1 else None
        search_param = search_text if search_text else None

        mem_limit = st.slider("Results", 10, 500, 100, key="mem_limit")
        results = query_interactions(
            agent=agent_param,
            start_date=start_param,
            end_date=end_param,
            session_id=session_param,
            search_text=search_param,
            limit=mem_limit,
        )

        if results:
            st.markdown(
                f"<div style='color:#888; font-size:0.8rem; margin-bottom:8px;'>{len(results)} interactions logged.</div>",
                unsafe_allow_html=True,
            )
            for entry in results:
                ts = entry.get("timestamp", "?")
                agent = entry.get("agent", "?")
                user_in = entry.get("user_input", "")
                agent_out = entry.get("agent_output", "")
                reasoning = entry.get("reasoning_trace")
                calls_raw = entry.get("inter_agent_calls")
                calls = json.loads(calls_raw) if calls_raw else None

                with st.expander(f"[{ts}] {agent} أ¢â‚¬â€‌ {user_in[:60]}..."):
                    st.markdown(f"<b>Input:</b> {user_in}", unsafe_allow_html=True)
                    st.markdown(
                        f"<b>Output:</b><div class='agent-response-box'>{agent_out}</div>",
                        unsafe_allow_html=True,
                    )
                    if reasoning:
                        st.markdown(
                            f"<b>Reasoning Trace:</b><div class='reasoning-box'>{reasoning}</div>",
                            unsafe_allow_html=True,
                        )
                    if calls:
                        st.markdown("<b>Inter-agent calls:</b>", unsafe_allow_html=True)
                        for call in calls:
                            st.markdown(
                                f"<div class='inter-call-box'>أ¢â€ â€™ <b>{call.get('agent', '?')}</b>: {call.get('input', '')[:100]}</div>",
                                unsafe_allow_html=True,
                            )
                    if entry.get("session_id"):
                        st.caption(f"Session: {entry['session_id']}")
        else:
            st.info(
                "No interactions logged yet. Start asking questions in the dashboard or agents tabs."
            )

    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    # SYSTEM STATUS PAGE
    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    elif page == "System Status":
        st.markdown(
            "<div class='section-hdr'>System Status أ¢â‚¬â€‌ Audit Report</div>",
            unsafe_allow_html=True,
        )
        st.markdown("**AI Agents**")
        agent_rows = []
        for aname, pr in agent_probes.items():
            is_online = pr["can_run"] and _ollama_ok
            agent_rows.append(
                {
                    "Agent": aname,
                    "Status": "ظ‹ع؛ع؛آ¢ Online" if is_online else "ظ‹ع؛â€‌آ´ Offline",
                    "Module": pr["status"],
                    "Lines": pr["lines"],
                    "Detail": pr["detail"],
                }
            )
        st.dataframe(pd.DataFrame(agent_rows), width="stretch", hide_index=True)

        st.markdown("**Business Engines**")
        eng_rows = []
        for ename in ENGINE_NAMES:
            pr = probe_engine(ename, ENGINE_MODULE_PATHS[ename])
            eng_rows.append(
                {
                    "Engine": ename,
                    "Status": "ظ‹ع؛ع؛آ¢ Loaded" if pr["can_run"] else "ظ‹ع؛â€‌آ´ Error",
                    "Lines": pr["loc"],
                    "Detail": pr["detail"],
                }
            )
        st.dataframe(pd.DataFrame(eng_rows), width="stretch", hide_index=True)

        st.markdown("**Infrastructure**")
        infra = {
            "Governance": ("GOVERNANCE/", "Enforcement + audit"),
            "Orchestrator": ("orchestration/", "Direct orchestration"),
            "Cognitive Memory Log": ("cockpit/memory/", "JSONL + SQLite"),
            "Ollama Service": (
                "localhost:11434",
                "Running" if _ollama_ok else "OFFLINE",
            ),
            "Dashboard": ("cockpit/cockpit.py", "Operations Control Room"),
        }
        infra_rows = []
        for name, (pth, note) in infra.items():
            exists = (PROJECT_ROOT / pth).exists()
            infra_rows.append(
                {
                    "Component": name,
                    "Path": pth,
                    "Exists": "أ¢إ“â€¦" if exists else "ظ‹ع؛â€‌آ´",
                    "Note": note,
                }
            )
        st.dataframe(pd.DataFrame(infra_rows), width="stretch", hide_index=True)

        line_counts = {}
        for ename in ENGINE_NAMES:
            ep = Path(PROJECT_ROOT) / ENGINE_MODULE_PATHS[ename]
            try:
                line_counts[ename] = len(ep.read_text().splitlines())
            except OSError:
                line_counts[ename] = 0
        agent_lines = {a["name"]: agent_probes[a["name"]]["lines"] for a in AGENTS}
        truth = f"""Helix Prime Operations Control Room أ¢â‚¬â€‌ System Truth ({datetime.now().strftime("%Y-%m-%d %H:%M")})

    AI AGENTS (4):
      SAMI  = {"ONLINE" if agent_probes["SAMI"]["can_run"] and _ollama_ok else "OFFLINE"} أ¢â‚¬â€‌ {agent_lines.get("SAMI", 0)} lines
      SUBY  = {"ONLINE" if agent_probes["SUBY"]["can_run"] and _ollama_ok else "OFFLINE"} أ¢â‚¬â€‌ {agent_lines.get("SUBY", 0)} lines
      PHILI = {"ONLINE" if agent_probes["PHILI"]["can_run"] and _ollama_ok else "OFFLINE"} أ¢â‚¬â€‌ {agent_lines.get("PHILI", 0)} lines
      WILI  = {"ONLINE" if agent_probes["WILI"]["can_run"] and _ollama_ok else "OFFLINE"} أ¢â‚¬â€‌ {agent_lines.get("WILI", 0)} lines

    ENGINES (6):
      WFM  = {"OK" if probe_engine("WFM Forecasting", ENGINE_MODULE_PATHS["WFM Forecasting"])["can_run"] else "MISSING"}
      RTA  = {"OK" if probe_engine("RTA Command Center", ENGINE_MODULE_PATHS["RTA Command Center"])["can_run"] else "MISSING"}
      CX   = {"OK" if probe_engine("CX Churn Sentinel", ENGINE_MODULE_PATHS["CX Churn Sentinel"])["can_run"] else "MISSING"}
      B2B  = {"OK" if probe_engine("B2B Onboarding", ENGINE_MODULE_PATHS["B2B Onboarding"])["can_run"] else "MISSING"}
      PERS = {"OK" if probe_engine("Personnel Engine", ENGINE_MODULE_PATHS["Personnel Engine"])["can_run"] else "MISSING"}
      CRM  = {"OK" if probe_engine("CRM Engine", ENGINE_MODULE_PATHS["CRM Engine"])["can_run"] else "MISSING"}

    INFRASTRUCTURE:
      Ollama      = {"RUNNING" if _ollama_ok else "OFFLINE"}
      Governance  = ACTIVE
      Cog Memory  = ACTIVE (JSONL + SQLite)
      Dashboard   = Streamlit Ops Control Room on port 8501
    """
        st.code(truth)

    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    # CLIENT SIMULATION MODE أ¢â‚¬â€‌ NEW
    # أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯أ¢â€¢ع¯
    elif page == "Client Simulation":
        st.markdown(
            "<div class='section-hdr'>Client Simulation Mode</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='font-size:0.8rem; color:#888; margin-bottom:16px;'>Define a fake business profile and walk through a full scenario أ¢â‚¬â€‌ each step is logged to the cognitive memory system.</div>",
            unsafe_allow_html=True,
        )

        sim_tab1, sim_tab2, sim_tab3 = st.tabs(
            ["Business Profile", "Scenario Walkthrough", "Simulation Log"]
        )

        with sim_tab1:
            st.markdown("### Step 1: Create Client Profile")
            col1, col2 = st.columns(2)
            with col1:
                sim_name = st.text_input(
                    "Company Name", placeholder="e.g. NovaTech Solutions"
                )
                sim_industry = st.selectbox(
                    "Industry",
                    [
                        "Technology",
                        "Healthcare",
                        "Finance",
                        "Retail",
                        "Manufacturing",
                        "Telecommunications",
                        "Education",
                    ],
                )
                sim_size = st.selectbox(
                    "Company Size",
                    [
                        "Startup (1-50)",
                        "Small (50-200)",
                        "Mid-Market (200-1000)",
                        "Enterprise (1000-5000)",
                        "Large Enterprise (5000+)",
                    ],
                )
            with col2:
                sim_headcount = st.number_input(
                    "Agent Headcount", min_value=10, max_value=10000, value=200
                )
                sim_calls = st.number_input(
                    "Daily Call Volume", min_value=0, max_value=50000, value=4000
                )
                sim_sl = st.slider("Current Service Level", 0.0, 1.0, 0.78)

            sim_needs = st.text_area(
                "Business Needs / Scenario",
                placeholder="Describe what this client needs أ¢â‚¬â€‌ e.g. 'Just signed a contract, needs B2B onboarding, staffing forecast for 200 agents, SOP generation for new hires, and personnel pipeline setup'",
            )

            if st.button("Initialize Simulation", type="primary"):
                st.session_state.sim_client_profile = {
                    "name": sim_name or "SimClient",
                    "industry": sim_industry,
                    "size": sim_size,
                    "headcount": sim_headcount,
                    "daily_calls": sim_calls,
                    "service_level": sim_sl,
                    "needs": sim_needs or "General operations support",
                    "created": datetime.now().isoformat(),
                }
                st.session_state.sim_steps = []
                log_interaction(
                    LogEntry(
                        timestamp=datetime.now().isoformat(),
                        agent="SIMULATION",
                        user_input=f"Simulation initialized: {sim_name} ({sim_industry}, {sim_size})",
                        agent_output="Simulation profile created.",
                        session_id=st.session_state.session_id,
                        client_context=sim_name,
                    )
                )
                st.success(
                    f"Profile for **{sim_name}** created! Go to the Scenario Walkthrough tab."
                )

        with sim_tab2:
            if not st.session_state.sim_client_profile:
                st.warning("Create a client profile in the Business Profile tab first.")
            else:
                profile = st.session_state.sim_client_profile
                st.markdown(
                    "<div style='background:#131823; padding:16px; border-radius:6px; margin-bottom:12px; border-left:4px solid #00BFA6;'>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<b>Client:</b> {profile['name']} &middot; <b>Industry:</b> {profile['industry']} &middot; <b>Size:</b> {profile['size']} &middot; <b>Headcount:</b> {profile['headcount']}</div>",
                    unsafe_allow_html=True,
                )

                st.markdown("### Run Scenario Steps")
                st.markdown(
                    "Click each button below to execute a step. Each step calls real agents/engines."
                )

                sim_step_1 = st.button(
                    "1. B2B Onboarding أ¢â‚¬â€‌ Register client in system"
                )
                if sim_step_1:
                    with st.spinner(
                        "Registering client and generating onboarding plan..."
                    ):
                        b2b_result, err = call_b2b(profile["name"])
                        wili = AgentRegistry.get_agent("WILI")
                        wili.session_id = st.session_state.session_id
                        wili.client_context = profile["name"]
                        wili_output = wili.process_request(
                            f"Generate a training onboarding plan for {profile['name']}, a {profile['industry']} company with {profile['headcount']} agents. They need SOP training and new-hire curriculum."
                        )
                        wili_reasoning = getattr(wili, "_last_reasoning", None)
                        step = {
                            "step": "B2B Onboarding + WILI Training Plan",
                            "engine_result": b2b_result.to_dict("records")
                            if b2b_result is not None
                            else err,
                            "agent_output": wili_output,
                            "agent_reasoning": wili_reasoning,
                            "timestamp": datetime.now().isoformat(),
                        }
                        st.session_state.sim_steps.append(step)
                        log_interaction(
                            LogEntry(
                                timestamp=step["timestamp"],
                                agent="SIMULATION",
                                user_input=f"B2B Onboarding for {profile['name']}",
                                agent_output=f"B2B: {b2b_result is not None} | WILI training plan generated",
                                reasoning_trace=wili_reasoning,
                                session_id=st.session_state.session_id,
                                client_context=profile["name"],
                            )
                        )
                        st.rerun()

                sim_step_2 = st.button(
                    "2. WFM Staffing Forecast أ¢â‚¬â€‌ Predict staffing needs"
                )
                if sim_step_2:
                    with st.spinner("Running WFM Erlang-C forecast..."):
                        wfm_result, err = call_wfm(profile["name"])
                        if wfm_result is None:
                            wfm_result = err
                        suby = AgentRegistry.get_agent("SUBY")
                        suby.session_id = st.session_state.session_id
                        suby.client_context = profile["name"]
                        suby_output = suby.process_request(
                            f"Analyze the staffing forecast for {profile['name']}: they have {profile['headcount']} agents handling {profile['daily_calls']} calls/day with a service level target of {profile['service_level']:.0%}. What operational risks do you see?"
                        )
                        suby_reasoning = getattr(suby, "_last_reasoning", None)
                        step = {
                            "step": "WFM Staffing Forecast + SUBY Analysis",
                            "engine_result": wfm_result.to_dict("records")
                            if isinstance(wfm_result, pd.DataFrame)
                            else str(wfm_result),
                            "agent_output": suby_output,
                            "agent_reasoning": suby_reasoning,
                            "timestamp": datetime.now().isoformat(),
                        }
                        st.session_state.sim_steps.append(step)
                        log_interaction(
                            LogEntry(
                                timestamp=step["timestamp"],
                                agent="SIMULATION",
                                user_input=f"WFM Forecast for {profile['name']}",
                                agent_output=f"WFM done | SUBY: {suby_output[:100]}...",
                                reasoning_trace=suby_reasoning,
                                session_id=st.session_state.session_id,
                                client_context=profile["name"],
                            )
                        )
                        st.rerun()

                sim_step_3 = st.button(
                    "3. Personnel Pipeline أ¢â‚¬â€‌ Mock hiring pipeline"
                )
                if sim_step_3:
                    with st.spinner("Running personnel pipeline check..."):
                        pers_result, err = call_personnel(profile["name"])
                        if pers_result is None:
                            pers_result = err
                        phili = AgentRegistry.get_agent("PHILI")
                        phili.session_id = st.session_state.session_id
                        phili.client_context = profile["name"]
                        phili_output = phili.process_request(
                            f"Build a hiring pipeline for {profile['name']}. They have {profile['headcount']} agents and need workforce planning. What personnel strategy do you recommend?"
                        )
                        phili_reasoning = getattr(phili, "_last_reasoning", None)
                        step = {
                            "step": "Personnel Pipeline + PHILI Strategy",
                            "engine_result": pers_result.to_dict("records")
                            if isinstance(pers_result, pd.DataFrame)
                            else str(pers_result),
                            "agent_output": phili_output,
                            "agent_reasoning": phili_reasoning,
                            "timestamp": datetime.now().isoformat(),
                        }
                        st.session_state.sim_steps.append(step)
                        log_interaction(
                            LogEntry(
                                timestamp=step["timestamp"],
                                agent="SIMULATION",
                                user_input=f"Personnel Pipeline for {profile['name']}",
                                agent_output=f"Pipeline done | PHILI: {phili_output[:100]}...",
                                reasoning_trace=phili_reasoning,
                                session_id=st.session_state.session_id,
                                client_context=profile["name"],
                            )
                        )
                        st.rerun()

                sim_step_4 = st.button(
                    "4. SOP Generation via WILI أ¢â‚¬â€‌ Create client SOPs"
                )
                if sim_step_4:
                    with st.spinner("Generating SOPs with WILI + PHILI data..."):
                        wili = AgentRegistry.get_agent("WILI")
                        wili.session_id = st.session_state.session_id
                        wili.client_context = profile["name"]

                        # WILI should call PHILI internally for personnel data check
                        wili_output = wili.process_request(
                            f"Generate a full set of SOPs for {profile['name']}, a {profile['industry']} company. Before finalizing, check with PHILI for personnel headcount ({profile['headcount']}) and open roles to align training with actual needs. Produce onboarding SOP, quality SOP, and escalation SOP."
                        )
                        wili_reasoning = getattr(wili, "_last_reasoning", None)
                        wili_calls = getattr(wili, "_inter_agent_calls", [])

                        step = {
                            "step": "WILI SOP Generation (with PHILI consult)",
                            "engine_result": "SOP generation via agent",
                            "agent_output": wili_output,
                            "agent_reasoning": wili_reasoning,
                            "inter_agent_calls": wili_calls,
                            "timestamp": datetime.now().isoformat(),
                        }
                        st.session_state.sim_steps.append(step)
                        log_interaction(
                            LogEntry(
                                timestamp=step["timestamp"],
                                agent="SIMULATION",
                                user_input=f"SOP generation for {profile['name']}",
                                agent_output=wili_output[:200],
                                reasoning_trace=wili_reasoning,
                                inter_agent_calls=wili_calls,
                                session_id=st.session_state.session_id,
                                client_context=profile["name"],
                            )
                        )
                        st.rerun()

                sim_step_5 = st.button(
                    "5. Strategic Review via SAMI أ¢â‚¬â€‌ CEO wrap-up"
                )
                if sim_step_5:
                    with st.spinner("Consulting SAMI for strategic review..."):
                        sami = AgentRegistry.get_agent("SAMI")
                        sami.session_id = st.session_state.session_id
                        sami.client_context = profile["name"]

                        summary_text = f"We just completed a full client simulation for {profile['name']} ({profile['industry']}). "
                        summary_text += (
                            f"Steps completed: {len(st.session_state.sim_steps)}. "
                        )
                        for s in st.session_state.sim_steps:
                            summary_text += f"- {s['step']}; "

                        sami_output = sami.process_request(
                            f"Provide a CEO-level strategic review for {profile['name']}, a {profile['industry']} company with {profile['headcount']} agents. Here's what we've done: {summary_text}. What's your assessment of this engagement and what should our next priorities be?"
                        )
                        sami_reasoning = getattr(sami, "_last_reasoning", None)
                        sami_calls = getattr(sami, "_inter_agent_calls", [])

                        step = {
                            "step": "SAMI Strategic Review",
                            "engine_result": "Strategic review via agent",
                            "agent_output": sami_output,
                            "agent_reasoning": sami_reasoning,
                            "inter_agent_calls": sami_calls,
                            "timestamp": datetime.now().isoformat(),
                        }
                        st.session_state.sim_steps.append(step)
                        log_interaction(
                            LogEntry(
                                timestamp=step["timestamp"],
                                agent="SIMULATION",
                                user_input=f"Strategic review for {profile['name']}",
                                agent_output=sami_output[:200],
                                reasoning_trace=sami_reasoning,
                                inter_agent_calls=sami_calls,
                                session_id=st.session_state.session_id,
                                client_context=profile["name"],
                            )
                        )
                        st.rerun()

                if st.session_state.sim_steps:
                    if st.button("Reset Simulation", type="secondary"):
                        st.session_state.sim_steps = []
                        st.session_state.sim_client_profile = None
                        st.rerun()

        with sim_tab3:
            if not st.session_state.sim_steps:
                st.info(
                    "No simulation steps run yet. Go to the Scenario Walkthrough tab."
                )
            else:
                st.markdown(
                    f"### Simulation Log أ¢â‚¬â€‌ {len(st.session_state.sim_steps)} steps"
                )
                for i, step in enumerate(st.session_state.sim_steps):
                    with st.expander(
                        f"Step {i + 1}: {step['step']} أ¢â‚¬â€‌ {step['timestamp'][:19]}"
                    ):
                        if (
                            isinstance(step.get("engine_result"), list)
                            and len(step["engine_result"]) > 0
                        ):
                            st.markdown("<b>Engine Data:</b>", unsafe_allow_html=True)
                            st.json(step["engine_result"])
                        elif step.get("engine_result"):
                            st.text(str(step["engine_result"]))
                        if step.get("agent_reasoning"):
                            with st.expander("Show agent reasoning trace"):
                                st.markdown(
                                    f"<div class='reasoning-box'>{step['agent_reasoning']}</div>",
                                    unsafe_allow_html=True,
                                )
                        if step.get("inter_agent_calls"):
                            for call in step["inter_agent_calls"]:
                                st.markdown(
                                    f"<div class='inter-call-box'>أ¢â€ â€™ Called <b>{call['agent']}</b></div>",
                                    unsafe_allow_html=True,
                                )
                        if step.get("agent_output"):
                            st.markdown(
                                f"<b>Agent Output:</b><div class='agent-response-box'>{step['agent_output']}</div>",
                                unsafe_allow_html=True,
                            )
                st.success(
                    "This complete simulation can be exported from the Memory tab أ¢â‚¬â€‌ download-ready for your interview portfolio."
                )


if __name__ == "__main__":
    main()
