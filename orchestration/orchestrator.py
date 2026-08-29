"""Central orchestrator for Helix Prime agent-engine coordination.

Real routing: given an incoming request, decides which agent(s) should handle it
based on request content, calls the real agent function(s), and returns the
combined result.
"""

import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Routing rules ──────────────────────────────────────────────────────
# Each rule is (keywords, agent_names) — if ANY keyword matches, route
# to the listed agents. Rules are checked in order; first match wins.
# An empty agent list means "default" fallback.

ROUTING_RULES = [
    # Personnel & HR domain
    (
        [
            "attrition",
            "attrition",
            "turnover",
            "retention",
            "hiring",
            "onboard",
            "onboarding",
            "resign",
            "resignation",
            "headcount",
            "open position",
            "open positions",
            "recruit",
            "recruitment",
            "pipeline",
            "talent",
            " workforce ",
            "staff composition",
            "skill gap",
            "training need",
        ],
        ["phili"],
    ),
    # Operations & WFM domain
    (
        [
            "attrition",
            "staffing",
            "service level",
            "service level",
            "shrinkage",
            "schedule",
            "scheduled",
            "adherence",
            "rta",
            "handle time",
            "handle time",
            "call volume",
            "abandoned",
            "wfm",
            "workforce",
            "shift",
            "shift pattern",
            "rostering",
            "agent utilization",
            "productivity",
            "operational",
            "operational kpi",
        ],
        ["suby"],
    ),
    # CX / Customer Experience domain
    (
        [
            "churn",
            "csat",
            "customer",
            "sentiment",
            "nps",
            "complaint",
            "complaints",
            "satisfaction",
            "cx ",
            "customer experience",
            "voice of",
            "feedback",
            "survey",
        ],
        ["suby"],
    ),
    # B2B / Sales / Pipeline domain
    (
        [
            "pipeline",
            "deal",
            "sale",
            "sales ",
            "crm",
            "booking",
            "revenue",
            "pricing",
            "contract",
            "client onboarding",
            "b2b",
            "account",
            "upsell",
            "cross-sell",
            "win rate",
            "lost deal",
        ],
        ["sami"],
    ),
    # Training / L&D domain
    (
        [
            "training",
            "learn",
            "skill",
            "certif",
            "upskill",
            "cross-train",
            "curriculum",
            "program",
            "cohort",
            "time-to-competency",
            "l&d",
            "learning and development",
            "induction",
            "competency",
        ],
        ["wili"],
    ),
    # Compliance & Quality domain
    (
        [
            "compliance",
            "quality",
            "qa ",
            "audit",
            "policy",
            "evidence pack",
            "calibration",
            "risk control",
            "escalation review",
            "corrective action",
            "standard operating",
        ],
        ["andy"],
    ),
    # Fraud domain
    (
        [
            "fraud",
            "fraudulent",
            "chargeback",
            "scam",
            "money laundering",
            "aml",
            "anomaly",
            "suspicious transaction",
            "dispute",
            "financial crime",
        ],
        ["nono"],
    ),
    # Marketing domain
    (
        [
            "marketing",
            "campaign",
            "brand",
            "lead generation",
            "promotion",
            "content marketing",
            "social media",
            "messaging",
            "awareness",
        ],
        ["maya"],
    ),
    # Sales domain (distinct from SAMI's strategic/commercial keywords)
    (
        [
            "quota",
            "prospect",
            "sales pipeline",
            "account expansion",
            "renewal",
            "sales forecast",
            "lead gen",
            "territory",
            "sales target",
        ],
        ["liza"],
    ),
    # ICT domain
    (
        [
            "ict",
            "infrastructure",
            "network",
            "outage",
            "cyber",
            "security incident",
            "system status",
            "tooling",
            "data platform",
            "vpn",
            "endpoint",
        ],
        ["tomy"],
    ),
    # Strategic / CEO domain
    (
        [
            "strategy",
            "strategic",
            "long-term",
            "vision",
            "competitive",
            "market",
            "invest",
            "investment",
            "expand",
            "acquisition",
            "stakeholder",
            "shareholder",
            "board",
            "executive",
            "ceo",
            "direction",
            "priorit",
            "20,000 foot",
        ],
        ["sami"],
    ),
]

# Default fallback when no rule matches
DEFAULT_AGENTS = ["sami", "suby", "phili"]

# Precompute a flat keyword lookup for routing.
# Each request now checks this single list instead of nested rule lists.
ROUTING_KEYWORD_LOOKUP = []
for keywords, agent_names in ROUTING_RULES:
    for kw in keywords:
        ROUTING_KEYWORD_LOOKUP.append((kw.lower(), agent_names))

# Agent class mapping
AGENT_CLASSES = {
    "sami": ("sami", "SAMIAgent"),
    "suby": ("suby", "SUBYAgent"),
    "phili": ("phili", "PHILIAgent"),
    "wili": ("wili", "WILIAgent"),
    "andy": ("base_agent", "ComplianceQualityAgent"),
    "nono": ("base_agent", "FraudAgent"),
    "maya": ("base_agent", "MarketingAgent"),
    "liza": ("base_agent", "SalesAgent"),
    "tomy": ("base_agent", "ICTAgent"),
}


class Orchestrator:
    def __init__(self):
        self.agents = {}
        self.engines = {}
        self._discover_agents()
        self._discover_engines()

    def _discover_agents(self):
        agent_dir = PROJECT_ROOT / "app" / "command_center" / "agents"
        if not agent_dir.exists():
            return
        sys.path.insert(0, str(agent_dir))
        for f in agent_dir.glob("*.py"):
            if f.stem.startswith("_"):
                continue
            self.agents[f.stem] = {"path": str(f), "loaded": False}
        # Ensure every canonical agent in AGENT_CLASSES is discoverable even when
        # its class lives in a shared module (e.g. base_agent.py). Without this,
        # _load_agent would early-return None for andy/nono/maya/liza/tomy.
        for key in AGENT_CLASSES:
            if key not in self.agents:
                self.agents[key] = {"path": "shared", "loaded": False}

    def _discover_engines(self):
        engine_map = {
            "WFM Forecasting": "engines/wfm/src/app_wfm.py",
            "RTA Command Center": "engines/rta/src/app.py",
            "CX Churn Sentinel": "engines/cx/src/risk_scorer.py",
            "B2B Onboarding": "engines/b2b/src/main.py",
            "Personnel Engine": "engines/personnel/src/main.py",
            "CRM Engine": "engines/crm/src/sales_pipeline.py",
        }
        for name, rel_path in engine_map.items():
            p = PROJECT_ROOT / rel_path
            if p.exists():
                self.engines[name] = {"path": str(p), "loaded": False}

    def _resolve_agents(self, user_message: str) -> list:
        """Decide which agent(s) should handle the request based on content."""
        message_lower = user_message.lower()
        matched = []

        for kw, agent_names in ROUTING_KEYWORD_LOOKUP:
            if kw in message_lower:
                for name in agent_names:
                    if name not in matched:
                        matched.append(name)

        if not matched:
            matched = DEFAULT_AGENTS

        return matched

    def _load_agent(self, agent_key: str):
        """Lazy-load an agent class and return an instance."""
        if agent_key not in AGENT_CLASSES:
            return None

        if agent_key not in self.agents:
            return None

        agent_info = self.agents[agent_key]
        if agent_info.get("loaded"):
            return agent_info.get("instance")

        try:
            module_name, class_name = AGENT_CLASSES[agent_key]
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            instance = cls()
            self.agents[agent_key]["loaded"] = True
            self.agents[agent_key]["instance"] = instance
            return instance
        except (ImportError, AttributeError, KeyError, TypeError, OSError) as e:
            print(f"[ORCHESTRATOR] Failed to load agent {agent_key}: {e}")
            return None

    def route(self, user_message: str) -> dict:
        """Route request to agent(s) and return combined results."""
        target_agents = self._resolve_agents(user_message)
        results = {}

        for agent_key in target_agents:
            agent = self._load_agent(agent_key)
            if agent is None:
                results[agent_key] = {
                    "status": "unavailable",
                    "error": f"Agent {agent_key} could not be loaded",
                }
                continue

            try:
                response = agent.process_request(user_message)
                results[agent_key] = {
                    "status": "success",
                    "response": response,
                    "role": agent.role if hasattr(agent, "role") else agent_key,
                }
            except (ValueError, TypeError, KeyError, OSError) as e:
                results[agent_key] = {
                    "status": "error",
                    "error": str(e),
                }

        return {
            "request": user_message,
            "routed_to": target_agents,
            "results": results,
        }

    def status(self):
        return {
            "agents": {k: v["loaded"] for k, v in self.agents.items()},
            "engines": {k: v["loaded"] for k, v in self.engines.items()},
        }


_orchestrator = None


def orchestrate():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


if __name__ == "__main__":
    o = orchestrate()
    print("Orchestrator status:", o.status())
