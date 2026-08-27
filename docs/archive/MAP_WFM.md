> **📦 ARCHIVED — Historical Reference Only**
> This MAP file documents the original WFM engine file listing from the old `AI Automation Engineering\04_helix_mini\` structure, before the engine directories were lost during the rename/merge operation and subsequently recovered to `engines/wfm/`. For the current engine structure, see `docs/ENGINEERING_SPECIFICATION.md` §1.3 or `ROOT_BOOT.md`.

## The Helix Ecosystem

Helix is an accumulated operations solution — 28 years of contact-centre, WFM, and BPO operations — that has evolved from AI-as-a-tool into a full automated agentic organization.

---

﻿.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\app_wfm.py
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\README.md
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\requirements.txt
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\wfm-forecasting-toolkitexamplessample_hourly_volumes.csv.xlsx
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\wfm-forecasting-toolkitREADME.md.txt
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\wfm-forecasting-toolkitrequirements.txt.txt
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\wfm-forecasting-toolkitsrcapp_wfm.py.txt
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\wfm-forecasting-toolkitsrcerlang_c.py.txt
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\.github\workflows\python-package.yml
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\data\actuals.csv
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\data\sample_intervals.csv
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\output\fte_schedule.xlsx
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\output\variance_report.xlsx
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\src\data_pipeline.py
.\AI Automation Engineering\04_helix_mini\WFM FORECASTING CALCULATOR\src\variance_engine.py

---

## Helix Ecosystem — Master Story

> Source of truth: `MASTER STORY.docx`. The canonical Helix narrative is reproduced below for every project document so the ecosystem story stays consistent.

# THE HELIX ECOSYSTEM - MASTER STORY
Single Source of Truth

## Origin: An Accumulated Operations Solution
Helix is not a tutorial project and not a chatbot wrapper. It is the accumulated operational solution of 28 years in contact-centre, Workforce Management (WFM), and BPO operations. Every engine encodes hard-won operational truth: how staffing actually fails, why adherence slips, what makes a client churn, where onboarding breaks.

## AI as a Tool, Then an Agentic Organization
We began by using AI as a tool - local models and scripts that solved one painful workflow at a time (Erlang C staffing, real-time adherence, churn risk, client SOP generation). Those tools compounded. They became a system of specialized agents and domain engines that observe, reason, remember, and act. Helix is now a full automated agentic organization: humans supervise, the system executes.

## Mission
To deliver the ultimate, powerful, real solutions for business's most critical operations workflows - the reactive-not-predictive pain points that quietly drain enterprises: talent acquisition, workforce forecasting, real-time adherence, customer churn, and client onboarding. Not dashboards that report the past, but systems that prevent the failure before it happens.

## The Two Repositories
The Helix Ecosystem ships as two focused repositories:

1. AI Automation Engineering - the operational engine platform. Five domain engines (WFM Forecasting, RTA Command Center, CX Churn Sentinel, B2B Onboarding, Helix Personnel) unified in one Streamlit command center, plus a metacognitive memory layer (TMK loop) that learns across engines.
2. Helix Prime CEO - the agentic orchestration system. A Go runtime daemon routes tasks through a Python orchestrator to a capability-tagged agent registry (SAMI, WILI, PHILI, SUBY) with crash-isolated subprocess execution, shared memory, and local RAG. Zero mandatory cloud dependency.

## Engineering Philosophy - Constitution 000
Architecture is the expression of truth. Identity precedes implementation. No hardcoded configuration. Crash isolation by design. Local-first, secure, human-supervised. Every decision must reveal the assumptions it introduces.

## Verified Working - Local Test Results
- Unified dashboard boots clean on localhost:8501 (Streamlit, headless).
- All sections render: Home, WFM, RTA, CX, B2B, Personnel Board, Metacognition.
- WFM Erlang C pipeline returns required agents, SLA-met flag, occupancy, service level.
- RTA adherence and variance charts render from sample schedule CSV.
- CX 4-KPI risk scorer classifies Critical / High / Medium / Low.
- B2B SOP generator produces staffing plan + Notion payload.
- Personnel Board: hiring funnel, open requisitions, staffing recommendations, pending actions (Generate), HR Director Report - all render; empty-states safe with no seeded data.
- Metacognition: memory store, cross-engine pattern detection, TMK reflect, decision log all functional.
- python -m compileall passes; CEO daemon crash-isolation verified (agent crash leaves daemon and memory intact).

## Trajectory
Single operations practitioner -> accumulated operational solution -> AI-augmented toolset -> full automated agentic organization, purpose-built to solve the operations workflows that matter most.
