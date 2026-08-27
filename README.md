# Helix Prime

The ops platform I built because I was tired of stitching together five different tools that didn't talk to each other.

## What this actually is

Six business engines. Four local AI agents. One Streamlit cockpit. All running on your laptop.

**Engines inside:** WFM/Erlang C, Real-Time Adherence, CX Churn Sentinel, B2B Onboarding, Personnel, CRM.

**Agents:** SAMI (staffing), SUBY (adherence), PHILI (churn), WILI (onboarding). They connect to Ollama locally — no cloud, no API keys.

**Orchestrator:** Content-based routing. You drop a request in, it figures out which engine handles it.

## Honest status

**Alpha.** The cockpit works. The engines run. The agents respond (if you have Ollama). What's missing: full agent-to-agent chatter through the UI, and I haven't put this in front of a real client yet.

No production deployments. No enterprise case studies. Just code that works on my machine and hopefully yours.

## Run it (Windows)

```batch
setup.bat
launch.bat
```

Opens at `http://127.0.0.1:8501`.

## Run it (macOS/Linux)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r cockpit/requirements.txt
python launch.py
```

## Want the AI agents?

Install [Ollama](https://ollama.com) and pull a small model:

```bash
ollama pull qwen2.5:1.5b
```

Without Ollama, the cockpit still works — agents just show "Offline."

## Where the engines came from

Helix Prime is the consolidation of five prototypes I built first. They're private now because the code moved into this repo, but they tell the story:

- **wfm-forecasting-calculator** — Erlang C staffing, shrinkage, interval planning, FTE costs
- **RTA_command_center** — real-time adherence with auto-alerts and anomaly detection
- **cx-sentiment-sentinel** — NLP churn prediction and sentiment pipeline
- **Dynamic-Ops-Automation-Engine** — client intake → staffing schedule + Notion SOPs
- **META-COGNITIVE-WFM-ENGINE** — advanced modeling experiments

## Why I built this

28 years in ops taught me one thing: the best tool is the one that's already open on your screen. Helix Prime is the dashboard I wanted — one place to see staffing, adherence, churn risk, onboarding pipeline, people data, and customer context. With local AI that actually helps instead of hallucinating.

## Stack

- Python 3.10+
- Streamlit for the cockpit
- Ollama for local LLM (optional but recommended)
- Pandas, Plotly, Flask for the engines
- Pydantic for data contracts

## Part of a bigger thing

This is the operational core. The learning side lives in [Study Studio](https://github.com/HatemIsmailShalaby1979/Study-Studio), [Helix Education](https://github.com/HatemIsmailShalaby1979/Helix-Education), and [L&D Command Center](https://github.com/HatemIsmailShalaby1979/L-D-Command-Center).

## License

MIT — use it, break it, improve it.