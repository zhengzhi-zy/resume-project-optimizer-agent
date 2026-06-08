# Resume Project Optimizer Agent

An interactive resume project optimization system built on top of the local `hello_agents` package.

The project helps a user turn a vague project description into a stronger, interview-ready resume project entry through staged questioning, structured memory, context engineering, and evidence-aware rewriting.

## What It Does

- Collects project information through multi-round questioning instead of asking for everything up front
- Splits the conversation into four stages: project positioning, personal role, technical depth, and impact
- Uses `NoteTool` to store structured session memory rather than relying only on raw chat history
- Uses `ContextBuilder` to compress multi-round answers and notes into grounded context for downstream agents
- Generates a resume package containing summary, bullets, highlights, architecture points, quantified results, and interview follow-up questions
- Uses a reflection-style review step to remove weak claims and improve the final output

## Why This Project Matters

Many project descriptions are too rough to be used directly in a resume. People often know what they built, but cannot clearly explain:

- who the project serves
- what problem it solves
- what they personally implemented
- what technical decisions mattered
- what can be honestly claimed in an interview

This project turns that fuzzy input into a more structured and defensible resume artifact.

## System Overview

The backend is a FastAPI service and the frontend is a lightweight static web UI. The workflow coordinates several agents built with `hello_agents`.

### Core Components

- `HelloAgentsLLM`
  Connects the project to DeepSeek or OpenAI-compatible models.

- `SimpleAgent`
  Used for questioning, analysis, and drafting tasks.

- `ReflectionAgent`
  Used for evidence-aware review and refinement of generated resume content.

- `ToolRegistry`
  Registers tools that agents can use during execution.

- `NoteTool`
  Stores structured notes for session start, user answers, analysis results, and final package.

- `ContextBuilder`
  Builds compact context from the original project description, stage answers, and note records.

## Agent Workflow

### 1. Discovery Agent

The `DiscoveryAgent` asks follow-up questions stage by stage instead of trying to collect everything in one pass.

Current stages:

- `overview`
- `role`
- `technical`
- `impact`

It also performs a second job in the same LLM call:

- understand the user's latest answer
- classify the answer as `skip`, `unknown_only`, `informative`, or `informative_with_unknown`
- extract useful facts and uncertain parts
- decide whether to continue the current stage or move forward

This avoids adding a separate "answer understanding agent" and keeps token usage under better control.

### 2. Memory Layer

Every important interaction is written into `NoteTool` as structured memory, including:

- initial project description
- each answer with answer intent
- extracted useful facts
- uncertain or missing parts
- analysis result
- final resume package

This gives later agents better evidence than raw conversation alone.

### 3. Project Analyzer Agent

The `ProjectAnalyzerAgent` reads the session state and note summary, then produces a structured project analysis such as:

- problem
- scenario
- personal role
- technical stack
- challenges
- solutions
- results
- risks
- missing information

### 4. Resume Writer Agent

The `ResumeWriterAgent` converts the structured analysis into a resume-oriented output package, including:

- project positioning
- resume summary
- resume bullets
- technical highlights
- architecture points
- quantified results
- interview questions
- next actions

### 5. Resume Critic Agent

The `ResumeCriticAgent` uses reflection plus context engineering to review the generated package against the available evidence.

Its role is to make the final result more defensible by:

- removing or weakening claims that are not well supported
- moving uncertain parts into missing information
- improving clarity and interview-readiness

## End-to-End Flow

```text
User Input
  -> FastAPI session start
  -> DiscoveryAgent staged questioning
  -> NoteTool structured memory
  -> ProjectAnalyzerAgent
  -> ResumeWriterAgent
  -> ResumeCriticAgent
  -> Final resume package
  -> Frontend rendering / stream output
```

## Tech Stack

- Python
- FastAPI
- Pydantic
- Uvicorn
- JavaScript
- `hello_agents`
- DeepSeek API or OpenAI-compatible API

## Project Structure

```text
.
├─ main.py
├─ requirements.txt
├─ src
│  ├─ app.py
│  ├─ config.py
│  ├─ llm.py
│  ├─ models.py
│  ├─ agents
│  │  ├─ base.py
│  │  ├─ discovery.py
│  │  ├─ analyzer.py
│  │  ├─ writer.py
│  │  └─ critic.py
│  ├─ services
│  │  ├─ workflow.py
│  │  ├─ session_store.py
│  │  └─ memory_store.py
│  └─ utils
│     └─ json_utils.py
└─ static
   ├─ index.html
   ├─ app.js
   └─ styles.css
```

## Run Locally

### 1. Install dependencies

```powershell
cd "D:\codex_nigr\New project 5"
D:\python02\python.exe -m pip install -r requirements.txt
```

### 2. Create local env file

```powershell
copy .env.example .env
```

### 3. Start the app

```powershell
D:\python02\python.exe main.py
```

Open:

```text
http://127.0.0.1:8000
```

## LLM Configuration

The project supports an offline demo mode and a real LLM mode.

### Offline demo mode

```env
LLM_ENABLED=false
```

### Real DeepSeek mode

```env
LLM_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.deepseek.com/v1
```

## API Endpoints

- `GET /api/health`
- `POST /api/session/start`
- `POST /api/session/submit`
- `POST /api/session/{session_id}/finalize`
- `POST /api/session/{session_id}/finalize/stream`
- `GET /api/session/list`
- `GET /api/session/{session_id}`
- `DELETE /api/session/{session_id}`
- `DELETE /api/session/all`
- `GET /api/notes/summary`

## Resume-Facing Design Choices

This project intentionally focuses on several engineering ideas that are useful to discuss in interviews:

- staged agent workflow instead of one-shot prompting
- structured memory through tool usage
- context engineering over long multi-round conversations
- evidence-aware refinement instead of blind beautification
- balancing LLM autonomy with deterministic workflow control

## Current Limitations

- Output quality still depends on the honesty and completeness of user input
- There is no dedicated authentication or multi-user isolation layer yet
- The frontend is oriented toward workflow clarity rather than polished product design
- Evidence checking is stronger than plain prompting, but it is not a formal fact-verification system

## Future Improvements

- Export final result to Markdown or Word
- Add richer evidence scoring per bullet
- Add screenshot upload or project artifact upload as supporting evidence
- Improve frontend presentation of stage memory and reasoning progress
- Add analytics for question quality and stage completion efficiency
