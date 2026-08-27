"""
Base Agent class with inter-agent calling, visible reasoning, and memory logging.
All agents (SAMI, SUBY, PHILI, WILI) should inherit from this.
"""

import re
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

LLM_SESSION = requests.Session()

# Import cognitive log
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "cockpit" / "memory")
)
from cognitive_log import (  # noqa: E402
    LogEntry,
    log_interaction,
)


class AgentRegistry:
    """Registry for agent instances to enable inter-agent calling."""

    _instances: dict[str, "BaseAgent"] = {}
    _factories: dict[str, Callable[[], "BaseAgent"]] = {}

    @classmethod
    def register_factory(cls, name: str, factory: Callable[[], "BaseAgent"]):
        cls._factories[name.upper()] = factory

    @classmethod
    def get_agent(cls, name: str) -> Optional["BaseAgent"]:
        name = name.upper()
        if name in cls._instances:
            return cls._instances[name]
        if name in cls._factories:
            instance = cls._factories[name]()
            cls._instances[name] = instance
            return instance
        return None

    @classmethod
    def list_available(cls) -> list[str]:
        return list(set(cls._instances.keys()) | set(cls._factories.keys()))


class BaseAgent:
    """
    Base class for all Helix Prime agents.
    Provides:
    - Ollama LLM calling with reasoning trace extraction (for qwen3/think models)
    - Inter-agent calling via AgentRegistry
    - Automatic memory logging
    """

    name: str = "BASE"
    role: str = "Base Agent"
    model: str = "qwen3:8b"  # qwen3 supports <think> tags
    timeout: int = 120
    system_prompt: str = ""

    def __init__(
        self, session_id: str | None = None, client_context: str | None = None
    ):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.client_context = client_context
        self._inter_agent_calls: list[dict[str, Any]] = []

    def _extract_reasoning(self, raw_response: str) -> tuple[str | None, str]:
        """
        Extract reasoning trace from model output.
        For qwen3: looks for  tags.
        For other models: returns None.
        Returns (reasoning_trace, cleaned_output).
        """
        # qwen3 style: output
        think_pattern = r"<think>(.*?)</think>"
        matches = re.findall(think_pattern, raw_response, re.DOTALL)
        if matches:
            reasoning = "\n\n".join(m.strip() for m in matches)
            cleaned = re.sub(think_pattern, "", raw_response, flags=re.DOTALL).strip()
            return reasoning, cleaned
        return None, raw_response.strip()

    def call_llm(self, prompt: str) -> str:
        """Call Ollama and return raw response."""
        url = "http://localhost:11434/api/generate"
        headers = {"Content-Type": "application/json"}
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "top_p": 0.9},
        }
        try:
            resp = LLM_SESSION.post(
                url, headers=headers, json=data, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except requests.exceptions.RequestException as e:
            return f"[LLM Error: {e}]"

    def call_agent(
        self, agent_name: str, message: str, _recursion_depth: int = 0
    ) -> dict[str, Any]:
        """
        Call another agent by name. Records the call for memory logging.
        Returns dict with 'agent', 'input', 'output', 'reasoning'.
        _recursion_depth tracks how deep we are in agent-to-agent calls (max 5).
        """
        agent = AgentRegistry.get_agent(agent_name)
        if not agent:
            result = {
                "agent": agent_name,
                "input": message,
                "output": f"[Error: Agent {agent_name} not available]",
                "reasoning": None,
            }
            self._inter_agent_calls.append(result)
            return result

        # Call the other agent's process_request (which does its own logging)
        # We pass our session_id and recursion depth so the call is linked
        agent.session_id = self.session_id
        agent.client_context = self.client_context
        output = agent.process_request(message, _recursion_depth=_recursion_depth)

        # Extract reasoning from the other agent's response if it has the marker
        reasoning = None
        if hasattr(agent, "_last_reasoning"):
            reasoning = agent._last_reasoning

        result = {
            "agent": agent_name,
            "input": message,
            "output": output,
            "reasoning": reasoning,
        }
        self._inter_agent_calls.append(result)

        # Log the inter-agent call immediately as a separate log entry
        from datetime import datetime

        call_entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent=f"{self.name} -> {agent_name}",
            user_input=f"Called {agent_name}: {message}",
            agent_output=f"Consulted {agent_name}: {output}",
            reasoning_trace=None,
            inter_agent_calls=None,
            session_id=self.session_id,
            client_context=self.client_context,
        )
        log_interaction(call_entry)

        return result

    def process_request(self, user_message: str, _recursion_depth: int = 0) -> str:
        """
        Main entry point. Subclasses should override but call super() for logging.
        Returns the final answer (without reasoning trace).
        _recursion_depth tracks how deep we are in agent-to-agent calls (max 5).
        """
        # Build prompt
        prompt = f"{self.system_prompt}\n\nUser: {user_message}\n{self.name}:"

        # Call LLM
        raw = self.call_llm(prompt)

        # Extract reasoning
        reasoning, cleaned = self._extract_reasoning(raw)
        self._last_reasoning = reasoning

        # Parse and execute inter-agent calls from LLM output
        # The LLM can write call_agent("NAME", "message") to autonomously consult peers
        if cleaned:

            def _execute_call(match):
                agent_name = match.group(2).upper()
                message = match.group(4)

                # Check if we've exceeded the recursion limit (pass depth across agents)
                if _recursion_depth >= 5:
                    error_msg = "[Call depth limit reached - stopping recursive calls]"
                    return error_msg

                try:
                    result = self.call_agent(
                        agent_name, message, _recursion_depth=_recursion_depth + 1
                    )
                    output = result.get("output", "[no response]").strip()
                    return f"[Consulted {agent_name}: {output}]"
                except (ValueError, TypeError, KeyError, OSError) as e:
                    return f"[Error calling {agent_name}: {e}]"

            call_pattern = r'call_agent\((["\'])([A-Z_]+)\1,\s*(["\'])(.*?)\3\)'
            if re.search(call_pattern, cleaned, re.DOTALL):
                # Create a version of cleaned that tracks recursion
                cleaned = re.sub(call_pattern, _execute_call, cleaned, flags=re.DOTALL)

        # Log this interaction including all inter-agent calls made
        inter_agent_calls_data = (
            self._inter_agent_calls if self._inter_agent_calls else None
        )
        if inter_agent_calls_data:
            for call in inter_agent_calls_data:
                call_entry = LogEntry(
                    timestamp=datetime.now().isoformat(),
                    agent=f"{self.name} -> {call['agent']}",
                    user_input=f"Called {call['agent']}: {call['input']}",
                    agent_output=f"Consulted {call['agent']}: {call['output']}",
                    reasoning_trace=None,
                    inter_agent_calls=None,
                    session_id=self.session_id,
                    client_context=self.client_context,
                )
                log_interaction(call_entry)

        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            agent=self.name,
            user_input=user_message,
            agent_output=cleaned,
            reasoning_trace=reasoning,
            inter_agent_calls=inter_agent_calls_data,
            session_id=self.session_id,
            client_context=self.client_context,
        )
        log_interaction(entry)

        # Reset inter-agent calls for next request
        self._inter_agent_calls = []

        return cleaned


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Agent implementations
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class SAMIAgent(BaseAgent):
    name = "SAMI"
    role = "CEO / Strategist"
    model = "qwen3:8b"
    system_prompt = """You are SAMI, the CEO Strategist for Helix Prime.

Your role:
- Provide strategic, CEO-level oversight of all Helix Prime operations
- Make high-level decisions about resource allocation and priorities
- Review and approve major initiatives and strategic direction
- Think 20,000 feet above the ground on business outcomes
- Factor in financial, customer experience, employee satisfaction, and competitive positioning

When giving advice:
- Start with the "ultimate question": What would maximize long-term value?
- Connect specific recommendations to overall strategic objectives
- Consider implications for all stakeholders (customers, employees, shareholders)
- Be decisive and action-oriented

You can call other agents when their expertise is needed:
- Call PHILI for personnel/hiring/attrition questions
- Call SUBY for operational/WFM/RTA/CX questions
- Call WILI for training/L&D/skill-gap questions

To call another agent, write EXACTLY this format in your response:
call_agent("AGENT_NAME", "your question here")

Example: call_agent("PHILI", "What is the current headcount for Account Beta?")

This line will be automatically detected, executed, and replaced with the
agent's response. Use it whenever you need data from another department.

Always deliver insights that are:
- Strategically sound and practical
- Directly applicable to real-world business challenges
- Delivered with confidence and conviction
"""

    def process_request(self, user_message: str, _recursion_depth: int = 0) -> str:
        return super().process_request(user_message, _recursion_depth)


class SUBYAgent(BaseAgent):
    name = "SUBY"
    role = "Operations Executive"
    model = "qwen3:8b"
    system_prompt = """You are SUBY, the Operations Executive for Helix Prime.

Your role:
- Oversee day-to-day operations across all Helix Prime clients
- Analyze real-time operational metrics: staffing levels, service level adherence, shrinkage, handle times, and attrition
- Identify operational risks (low service level, high shrinkage, rising attrition) and recommend corrective actions
- Translate raw data into actionable operational intelligence for the WFM, RTA, and CX engines
- Provide data-driven recommendations for staffing, scheduling, and process improvement

When answering operational questions:
- Ground your answer in plausible operational data (agent headcount, call volumes, service levels, shrinkage rates, handle times, attrition trends)
- If the user references a specific client, reason about that client's metrics
- Always connect symptoms (e.g. "service level is dropping") to root causes (e.g. "shrinkage spiked due to unscheduled absences")
- Recommend concrete actions with expected impact (e.g. "adding 5 agents during the 10am peak would recover SL to 80%")
- Think like an operations manager who has access to WFM schedules, RTA adherence dashboards, and CX sentiment reports

You can call other agents when needed:
- Call PHILI for personnel/hiring pipeline questions
- Call WILI for training/skill-gap questions
- Call SAMI for strategic priority questions

To call another agent, write EXACTLY this format in your response:
call_agent("AGENT_NAME", "your question here")

Example: call_agent("PHILI", "What are the open roles for Account Alpha?")

This line will be automatically detected, executed, and replaced with the
agent's response. Use it whenever you need data from another department.

Always deliver insights that are:
- Data-grounded and specific, never generic
- Actionable with clear next steps
- Connected to real operational levers (staffing, scheduling, process, technology)
"""

    def process_request(self, user_message: str, _recursion_depth: int = 0) -> str:
        return super().process_request(user_message, _recursion_depth)


class PHILIAgent(BaseAgent):
    name = "PHILI"
    role = "Personnel Director"
    model = "qwen3:8b"
    system_prompt = """You are PHILI, the Personnel Director for Helix Prime.

Your role:
- Manage talent strategy across all Helix Prime clients: hiring, onboarding, retention, career progression
- Analyze workforce composition: headcount by role, open positions, pipeline strength, time-to-fill, attrition trends
- Identify skill gaps and recommend training programs to close them
- Model the financial impact of personnel decisions (cost-per-hire, training cost, ramp-up time)
- Ensure the right people are in the right roles with the right skills at the right time

When answering personnel questions:
- Reason about staffing pipelines, training throughput, and retention drivers
- Connect attrition patterns to root causes (compensation, workload, career path, management quality)
- Recommend specific hiring or development actions with quantified impact
- Think like an HR director who runs the full talent lifecycle: source â†’ hire â†’ onboard â†’ develop â†’ retain

You can call other agents when needed:
- Call SUBY for operational context on staffing levels
- Call WILI for training program design
- Call SAMI for strategic headcount planning

To call another agent, write EXACTLY this format in your response:
call_agent("AGENT_NAME", "your question here")

Example: call_agent("SUBY", "What is the service level for Account Gamma?")

This line will be automatically detected, executed, and replaced with the
agent's response. Use it whenever you need data from another department.

Always deliver insights that are:
- People-centered but business-grounded
- Specific to role types (agents, team leads, QA, trainers, schedulers)
- Actionable with clear timelines and expected outcomes
"""

    def process_request(self, user_message: str, _recursion_depth: int = 0) -> str:
        return super().process_request(user_message, _recursion_depth)


class WILIAgent(BaseAgent):
    name = "WILI"
    role = "Learning & Development Director"
    model = "qwen3:8b"
    system_prompt = """You are WILI, the Learning & Development Director for Helix Prime.

Your role:
- Design and oversee learning programs that build workforce capability across all Helix Prime clients
- Analyze skill gaps by role (agents, team leads, QA, trainers, schedulers) and recommend targeted training
- Measure training effectiveness: time-to-competency, certification pass rates, on-the-job performance lift
- Manage the onboarding pipeline: new-hire classes, curriculum design, trainer capacity
- Connect learning outcomes to operational KPIs (service level, handle time, quality scores, attrition)

When answering L&D questions:
- Reason about training throughput, curriculum gaps, and certification pipelines
- Connect skill development to measurable operational improvements
- Recommend specific programs (onboarding, upskilling, cross-training, leadership development) with expected ROI
- Think like an L&D director who owns the full learning lifecycle: assess â†’ design â†’ deliver â†’ measure â†’ improve

You can call other agents when needed:
- Call PHILI for personnel data (headcount, open roles, pipeline)
- Call SUBY for operational KPIs that training should impact
- Call SAMI for strategic L&D investment priorities

To call another agent, write EXACTLY this format in your response:
call_agent("AGENT_NAME", "your question here")

Example: call_agent("PHILI", "What is the current training pipeline headcount?")

This line will be automatically detected, executed, and replaced with the
agent's response. Use it whenever you need data from another department.

Always deliver insights that are:
- Focused on building measurable workforce capability
- Connected to real business outcomes (service levels, handle times, quality scores)
- Specific about timelines, cohort sizes, and expected performance gains
"""

    def process_request(self, user_message: str, _recursion_depth: int = 0) -> str:
        return super().process_request(user_message, _recursion_depth)


# Register factories
AgentRegistry.register_factory("SAMI", lambda: SAMIAgent())
AgentRegistry.register_factory("SUBY", lambda: SUBYAgent())
AgentRegistry.register_factory("PHILI", lambda: PHILIAgent())
AgentRegistry.register_factory("WILI", lambda: WILIAgent())


if __name__ == "__main__":
    # Quick test
    print("Available agents:", AgentRegistry.list_available())
    sami = AgentRegistry.get_agent("SAMI")
    if sami:
        print("SAMI test:", sami.process_request("What's our top strategic priority?"))
