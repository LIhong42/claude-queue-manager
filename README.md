# Claude Queue Manager

A local queue management platform for orchestrating Claude Agent (Claude Code CLI) tasks with a frontend-backend separation architecture.

## Features

- **SQLite Persistent Queue** — Tasks survive restarts with states: PENDING → RUNNING → SUCCESS/FAILED/CANCELLED
- **Multi-Worker Concurrency** — Configurable number of concurrent workers (default: 2)
- **Auto-Claim** — Workers automatically fetch the next pending task upon completion
- **Isolated Workspaces** — Each task runs in its own directory (`./workspace/<task_id>/`)
- **Local Claude CLI** — Spawns `claude -p <prompt> --dangerously-skip-permissions --output-format stream-json --verbose`
- **Real-time Log Streaming** — WebSocket pushes stdout/stderr to the frontend as they arrive
- **Structured Trace Capture** — Tool-use events parsed from JSONL and displayed as colored cards
- **Automatic Retry** — Failed tasks retry up to `MAX_RETRIES` times (default: 2)
- **Startup Recovery** — Any tasks marked RUNNING on previous shutdown are reset to PENDING
- **Session Continuation** — Reuse `session_id` to continue a conversation in the same Claude session
- **React Frontend** — Create, view, cancel, retry, and delete tasks; view raw logs and execution traces

---

## Prerequisites

Ensure the Claude Code CLI is available and authenticated:

```bash
claude --version
```

## Quick Start

### 1. Start the Backend

**Windows:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app
```

**macOS / Linux:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app
```

The backend starts at `http://127.0.0.1:8000`.

### 2. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `HOST` | `127.0.0.1` | Backend bind address |
| `PORT` | `8000` | Backend port |
| `CLAUDE_BIN` | `claude` | Path to Claude CLI |
| `WORKERS` | `2` | Number of concurrent workers |
| `MAX_RETRIES` | `2` | Max retry attempts per task |
| `DB_PATH` | `./data/tasks.db` | SQLite database path |
| `WORKSPACE_ROOT` | `./workspace` | Per-task workspace root |
| `LOG_ROOT` | `./logs` | Log and trace file directory |

**Example (Windows):**
```powershell
$env:WORKERS="3"
python -m app
```

---

## Effect Preview

### Task List Management Platform

![Task List Management Platform](images/Task-List-Management-Platform.png)

### Check the Run Results

![Check the Run Results](images/Check-the-run-results.png)

### View Execution Process and Continue in Same Session

![View Execution Process and Continue in Same Session](images/View-execution-process-and-modify-in-the-same-session.png)

---

## Queue Mechanism

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   SQLite    │────▶│   Worker    │────▶│  Claude Session  │────▶│ SUCCESS / FAILED│
│   Queue     │     │  (asyncio)  │     │  (subprocess)    │     │    / RETRY      │
└─────────────┘     └─────────────┘     └──────────────────┘     └─────────────────┘
     ▲                   │
     │                   ↓
     │            ┌─────────────┐
     └────────────│  Auto-Claim │
                  │  Next Task  │
                  └─────────────┘
```

- Tasks are stored in **SQLite** with states: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`
- Workers claim tasks atomically using `BEGIN IMMEDIATE` to prevent race conditions
- Each task gets an **isolated workspace** under `./workspace/<task_id>/`
- Logs are written to `./logs/<task_id>.log` and traces to `./logs/<task_id>.trace.jsonl`
- The frontend connects via **WebSocket** for real-time updates (polls `/api/tasks` every 3s)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tasks` | List all tasks (paginated) |
| `POST` | `/api/tasks` | Create a new task |
| `GET` | `/api/tasks/{id}` | Get task details |
| `DELETE` | `/api/tasks/{id}` | Delete a task |
| `POST` | `/api/tasks/{id}/cancel` | Cancel a running task |
| `POST` | `/api/tasks/{id}/retry` | Retry a failed task |
| `POST` | `/api/tasks/{id}/continue` | Continue in the same session |
| `GET` | `/api/tasks/{id}/logs` | Stream raw log file |
| `WS` | `/ws` | Real-time event stream |

---

## Security Note

Claude Agent can execute commands, read files, and modify the workspace. It is recommended to:

- Use a **dedicated project directory** or **Git worktree** for task workspaces
- **Avoid** letting untrusted tasks access important data
- Set appropriate file permissions on the `workspace/` and `logs/` directories

---

## Tech Stack

- **Backend:** Python 3, FastAPI, Uvicorn, Pydantic, asyncio, sqlite3
- **Frontend:** React 18, Vite 6, plain CSS
- **Runtime:** Node.js (for frontend dev server)
