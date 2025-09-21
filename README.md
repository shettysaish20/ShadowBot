# ShadowBot

**The Undetectable AI Overlay for Interviews & Meetings**

Real-time suggestions, smart notes, and instant help—all displayed via a transparent overlay, so you can focus on your conversation without breaking flow.

## Supported Platforms

- Windows
- macOS

---
## 1. Project Overview

- A graph‑first execution engine (NetworkX) for explicit reasoning flow visualization & introspection.
- Multi‑Agent role specialization (Planner / Retriever / Thinker / Coder / Distiller / Clarifier / QA / Scheduler / Formatter / Decision / Tooling) coordinated via a structured loop (`AgentLoop4`).
- Multi‑MCP (Model Context Protocol) server aggregation for tool, retrieval, and browser search capabilities.
- Dynamic model configuration and runtime Gemini API key injection (no static secret requirement at cold start).
- Unified context management (files, user query, retrieved knowledge, agent outputs) with persistent session graph.
- Extensible profiles system to bias persona, tone, criteria, or domain behaviors.

The system is designed for research, rapid experimentation, and production‑grade extensibility: you can add tools, plug in new LLM providers, introduce new agent roles, or alter the execution graph with predictable impact.

---
## 2. Application Features - 

- Real-time AI Coaching — Get contextual tips and suggested answers as you speak. Helps with phrasing, structure, staying concise. 

- Transparent Overlay — Always-on-top window that sits above any app. Option to toggle “click-through” so the overlay doesn’t intercept clicks. 

- Live Transcription — Captures audio and some screen context to make suggestions more relevant to your actual conversation. 

- Multiple Profiles / Modes — Switch between different contexts such as Interview, Customer Support, Business Meeting etc., so the assistance is tailored. 

- Fast & Private — Designed for low latency, with a focus on running locally (as much as possible) to protect privacy. 

- Cross-Platform — Supports Windows and macOS, with easy installers. No coding needed to get started.

---
## 3. Functionalities

### Reasoning & Orchestration
- Graph‑based execution (NetworkX) with node‑level provenance.
- Deterministic + adaptive path selection (validators & analyzers).
- Multi‑turn session continuity (context reused until explicit reset).

### Multi‑Agent Architecture
- Specialized agents for planning, retrieval, synthesis, formatting, code generation, QA, clarification, scheduling, decision routing, and distillation.
- Configurable model per agent (via `config/agent_config.yaml`).
- Pluggable agent profiles (domain/persona overlays from `config/profiles.yaml`).

### Tooling & MCP Integration
- Aggregated MultiMCP launcher (see `mcp_servers/` & `mcp_servers/multiMCP.py`).
- Browser MCP (interactive stateful browsing, DOM element indexing, command surfaces, debug modes SSE/STDIO).
- Additional MCP servers (captioning, media, retrieval, etc.).

### Retrieval & Knowledge Handling
- FAISS vector indexing (local semantic retrieval).
- Rapid ingestion of user‑supplied files at query time.
- Structured file manifest captured for reproducibility.

### Model Abstraction
- Central `ModelManager` for LLM selection / initialization.
- Dynamic Gemini key injection via API (`/start`) or `.env` fallback.
- JSON configuration of available models (`config/models.json`).

### Developer Experience & Observability
- Rich logging (`logs/common.log`) + step logging utilities.
- Graph visualization utilities (`agentLoop/visualizer.py`).
- Output analyzer to summarize session outcomes.

### Extensibility
- Add new agent role: implement logic & register in `agents.py` + loop flow.
- Add tool: expose via MCP server, register in server config YAML.
- Support alternative model providers by extending `ModelManager`.

---
## 3. Tech Stack
### Backend
- Python (3.11+ recommended)
- FastAPI / Uvicorn (API server) *(current dynamic key entrypoint)*
- Flask + flask-sock (legacy / websocket experiments)
- NetworkX (graph reasoning backbone)
- FAISS (vector retrieval)
- Playwright / Patchright (browser automation via MCP)
- mcp (Model Context Protocol tooling)
- Rich / TQDM (UX / console)
- Pydantic (validation)

### Frontend
Two lightweight front-end surfaces (for demonstration / extension):
- `shadowbot-web-app/` (Vanilla JS + HTML + CSS)
- `shadowbot-fe/` (Node + potential packaging / extension scaffolding)

### Models / AI
- Gemini (dynamic API key injection)
- Local / alternative models (Ollama) if configured in environment & `config/models.json`.

### Data / Config
- YAML configurations for agents, profiles, MCP servers.
- JSON model registry.

---
## 4. Installation & Setup

### 4.1 Local Setup

#### 4.1.1 Prerequisites
- Python 3.11+
- Node.js (if building any front-end assets)
- (Optional) Ollama installed & models pulled if using local LLMs.

#### 4.1.2 Clone
```
git clone <repo-url>
cd ShadowBot
```

#### 4.1.3 Python Environment
Using `uv` (recommended for speed):
```
uv sync
```
Or vanilla:
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 4.1.4 Environment Variables
Create `.env` (optional if supplying runtime API key):
```
GEMINI_API_KEY=your_key_here   # can be omitted if using /start injection
```
Other optional variables can be added as you extend tooling.

#### 4.1.5 Launching MCP Servers
The system spins them up via `MultiMCP`. Ensure `config/mcp_server_config.yaml` lists enabled servers. You normally only run the main entrypoint; servers are initialized programmatically.

#### 4.1.6 Starting the CLI Orchestrator
```
uv run main.py
```

#### 4.1.7 Starting the API Server (Dynamic Gemini Key)
```
uv run api_server.py
```
Then POST to `/start`:
```
POST /start
Content-Type: application/json
{
  "api_key": "GEMINI_KEY_VALUE",   // optional
  "session_name": "demo"           // example additional field (if implemented)
}
```

If you omit `api_key`, server falls back to environment variable `GEMINI_API_KEY`.

#### 4.1.8 Front-End (Optional)

`shadowbot-fe/` (if build scripts configured):
```
cd shadowbot-fe
npm install
npm run dev   # or build
```
### 4.2 AWS Cloud Setup

#### 4.2.1 First run sync-to-ec2.sh locally in git-bash (ensure you have added the correct EC2 instance ID)
```
cd ShadowBot
./sync-to-ec2.sh
```

#### 4.2.2 Create python environment and install requirements
```
cd my-app
sudo apt install python3-venv
python3 -m venv env

source env/scripts/activate
python -m pip install -r requirements.txt
```

#### 4.2.3 Playwright installation
```
sudo apt-get update
playwright install-deps
playwright install
```

#### 4.2.4 ffmpeg installation
```
sudo apt-get install -y ffmpeg
ffmpeg -version
which ffmpeg   # should print /usr/bin/ffmpeg
```

#### 4.2.5 Starting application
```
(env) ubuntu@ip-172-31-6-119:~/my-app$ python api_server.py
```

---
## 5. Runtime Flow (High Level)
1. User supplies files & a query (CLI) or hits API.
2. `AgentLoop4` constructs / extends a session context (graph + memory).
3. Planner agent drafts an execution plan.
4. Retriever and/or Browser agents fetch knowledge or interact with web states.
5. Thinker / Coder / Distiller / Formatter refine outputs.
6. QA / Clarifier loops trigger if gaps detected.
7. Scheduler or Decision nodes finalize routing or termination.
8. Graph + outputs serialized / analyzable.

---
## 6. Architecture & Directory Guide

### 6.1 Architecture

### Frontend (User Interface – macOS / Windows)

- Overlay Transparent App Screen
    - Always-on-top overlay window visible during meetings/interviews.
    - Displays AI-generated suggestions, notes, and summaries.
    - Built using Electron (Chromium + Node.js).

- Profile Selection
    - Users can choose different profiles (Interview, Customer Support, Meeting Notetaker).
    - Each profile activates a different set of agents tailored to that context.

- Chat Interface
    - Allows direct user interaction with the AI assistant.
    - Provides fallback if the overlay is insufficient.

- Communication with Backend
    - Via REST API calls to Flask server.
    - Sends audio, screen, and session data for processing.

### Backend (AWS Cloud Infrastructure)

1. Orchestrator Code (on EC2 instance)

- Core logic that manages inputs/outputs and coordinates agents:
    - Audio Processor — Captures and processes live audio for transcription & analysis.
    - Screen Analyzer — Interprets screen context (slides, documents, tools in use).
    - Session Manager — Maintains conversation history, session states, and metadata.
This layer connects the frontend to the Agent Ecosystem.

2. Agent Ecosystem (Persona-specific PlannerAgents + Agents)

Each profile corresponds to a set of Planner Agents that orchestrate specialized sub-agents:

- Interview Assistant
    - Agents: Retriever, Thinker, Distiller, Coder, QA, Clarification.
    - Goal: Help users answer questions effectively, provide structured responses (e.g., STAR method).

- Customer Support Assistant
    - Agents: Retriever, Thinker, Distiller, Formatter.
    - Goal: Provide empathetic responses, fetch KB articles, and summarize solutions.

- Meeting Notetaker (coming soon)
    - Agents: Scheduler, Formatter.
    - Goal: Generate meeting summaries, highlight decisions, schedule follow-ups.

3. LLM Integration (Gemini API)

- ShadowBot connects to Gemini (Google’s LLM) via LLM API.
- LLM is used for reasoning, language generation, and contextual suggestions.
- The multi-agent planner decides when and how to query the LLM.

4. MCP Servers (Tooling & External Connectors)

These are specialized tool servers agents can call:
- File System Tools (read/write local files)
- Web Search Tools (fetch external info)
- Code Execution Tools (run snippets, debugging help)
- Knowledge Base Tools (internal KB lookups)
- Document Processing Tools (parse bills, contracts, reports)

This gives agents access to both external knowledge and system-level actions.

5. Storage & Logs

S3 (AWS Cloud Storage)
- Session Data: conversation history, user profiles, session metadata.
- Media Files: audio recordings, screenshots, video captures.
- Orchestrator Logs: records of agent steps, intermediate results, and performance metrics.

This supports reproducibility, debugging, and compliance.

### 6.2 Directory Guide
```
agentLoop/            Core loop, agents, model manager, graph logic
mcp_servers/          Individual MCP server implementations & multiplexer
browserMCP/           Browser automation tooling & utilities
config/               YAML + JSON configs (agents, profiles, models, servers)
prompts/              Prompt templates for specialized agents
utils/                Logging, parsing, helpers
test_*.py             Integration / feature tests
shadowbot-web-app/    Static demo web interface
shadowbot-fe/         Alternate FE scaffold
logs/                 Runtime logs
media/                Uploaded & generated artifacts
```
Key Files:
- `main.py` – CLI session loop.
- `api_server.py` – HTTP surface & dynamic API key handling.
- `agentLoop/flow.py` – Orchestrates multi-agent execution logic.
- `agentLoop/agents.py` – Agent class definitions / registry.
- `agentLoop/model_manager.py` – Model abstraction (Gemini + others).
- `mcp_servers/multiMCP.py` – Aggregates & controls multiple MCP servers.
- `config/agent_config.yaml` – Agent model + behavioral config.
- `config/profiles.yaml` – Persona / domain profiles.
- `config/models.json` – Model registry & env key mappings.

---
## 8. Agents & Profiles
### 8.1 Agent Roles (Representative)
- Planner: Decomposes user intent into steps.
- Retriever: Gathers context (files, vector search, external sources).
- Thinker: Deep reasoning / synthesis.
- Coder: Generates or refactors code artifacts.
- Distiller: Summarizes / compresses multi‑source content.
- Clarifier: Asks for disambiguation when intent unclear.
- QAAgent: Validates completeness / correctness.
- Scheduler / Decision: Determines next action or termination.
- Formatter: Produces final structured output.

See `agentLoop/agents.py` for concrete implementations & mapping logic.

### 8.2 Profiles
Profiles (in `config/profiles.yaml`) overlay persona, tone, or domain constraints (e.g., concise analyst, verbose tutor, security auditor). They can:
- Adjust prompt system headers.
- Influence tool usage thresholds.
- Bias style (formatting, verbosity, caution level).

Selection Mechanism:
- Determined at session start or by agent logic (depending on flow design).
- Can be extended by adding a new profile YAML entry and referencing it in agent configuration.

---
## 9. Prompts & Prompt Engineering
Prompts in `prompts/` are modular text templates used by each agent type. Enhancement guidelines:
- Keep role clarity explicit.
- Preserve delimiters for parser stability.
- Version prompts when modifying (add backup copy) for reproducibility.

---
## 10. Extending the System
### Add a New Agent
1. Implement logic in `agentLoop/agents.py`.
2. Register its invocation in `AgentLoop4` (flow orchestration).
3. Add configuration entry in `config/agent_config.yaml`.
4. (Optional) Create new prompt template.

### Add a New MCP Tool
1. Create new server module in `mcp_servers/`.
2. Register in `config/mcp_server_config.yaml`.
3. Ensure `MultiMCP` initialization picks it up.

### Add a New Model Provider
1. Extend `ModelManager` with provider client factory.
2. Update `config/models.json` with provider id + env var mapping.
3. Reference new model id in `agent_config.yaml`.

---
## 11. Roadmap (Potential Enhancements)
- Hot model/key rotation without process restart.
- Unified web control panel for session graphs & tool telemetry.
- Persistent vector store & document ingestion pipeline.
- Advanced planner w/ reinforcement loop.
- Multi-provider ensemble reasoning.
- Structured evaluation harness (BLEU / factuality / latency metrics).
- Prompt versioning & automatic diff impact testing.

---
## 12. Contributing
1. Fork & create a feature branch.
2. Add or update configuration as needed (agents, profiles, models).
3. Provide test script or scenario.
4. Submit PR with concise rationale + architectural impacts.

---
