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
- **Scheduled Start (Web + CLI)** — Each task can carry a `scheduled_at` timestamp; a dedicated worker claims the task **only when** the scheduled time has arrived **and** no other task is currently running (`status='RUNNING'` count == 0).
- **CLI Submission** — Submit (optionally scheduled) tasks from the terminal via `cli/add.sh` (Linux/macOS/Git Bash) or `cli/add.bat` (Windows cmd).
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
┌─────────────┐     ┌────────────────────────┐     ┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   SQLite    │────▶│  normal  workers  ───▶│  Worker  │────▶│  Claude Session  │────▶│ SUCCESS / FAILED│
│   Queue     │     │ (skip  scheduled_at)   │ (asyncio) │     │  (subprocess)    │     │    / RETRY      │
└─────────────┘     └────────────────────────┘     └─────────────┘     └──────────────────┘     └─────────────────┘
       ▲                                                    │
       │                                                    ↓
┌─  scheduled  ──┐     ┌────────────────────────┐     ┌─────────────┐
│   worker       │     │  due check + idle gate  │     │  Auto-Claim │
│                 └────▶│  scheduled_at <= now    │────▶│  Next Task  │
└────────────────────┘     │  AND count(RUNNING)=0   │     └─────────────┘
                            └────────────────────────────────────┘
```

- Tasks are stored in **SQLite** with states: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`
- Workers claim tasks atomically using `BEGIN IMMEDIATE` to prevent race conditions
- Each task gets an **isolated workspace** under `./workspace/<task_id>/`
- Logs are written to `./logs/<task_id>.log` and traces to `./logs/<task_id>.trace.jsonl`
- The frontend connects via **WebSocket** for real-time updates (polls `/api/tasks` every 3s)
- A dedicated **scheduled worker** runs alongside the normal workers. It only picks a task whose `scheduled_at` has passed **and** only after `count(RUNNING) == 0`. This enforces "one scheduled task at a time, with the system fully idle".

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tasks` | List all tasks (paginated) |
| `POST` | `/api/tasks` | Create a new task. Body: `{ "prompt": "...", "max_retries"?: int, "scheduled_at"?: ISO-8601 datetime }`. When `scheduled_at` is set in the future, a `task_scheduled` event is broadcast; otherwise `task_created`. |
| `GET` | `/api/tasks/{id}` | Get task details |
| `DELETE` | `/api/tasks/{id}` | Delete a task |
| `POST` | `/api/tasks/{id}/cancel` | Cancel a running task |
| `POST` | `/api/tasks/{id}/retry` | Retry a failed task |
| `POST` | `/api/tasks/{id}/continue` | Continue in the same session |
| `GET` | `/api/tasks/{id}/logs` | Stream raw log file |
| `WS` | `/ws` | Real-time event stream |

## CLI Usage

Both CLI scripts hit `POST /api/tasks` via HTTP. The backend must be running.

```bash
# Immediate
./cli/add.sh "echo hello from cli"

# Scheduled (local time)
./cli/add.sh "review code" "2026-10-02 15:30:00"

# Read prompt from file
./cli/add.sh -f prompt.txt

# Scheduled + from file
./cli/add.sh -f prompt.txt "2026-10-02 23:00"

# Remote backend
BASE_URL=http://192.168.1.10:8000 ./cli/add.sh "remote task"
```

Windows (cmd.exe):

```bat
cli\add.bat "echo hello"
cli\add.bat "review code" "2026-10-02 15:30:00"
set BASE_URL=http://192.168.1.10:8000 && cli\add.bat "remote task" "2026-10-02 15:30:00"
```

> Time semantics: a string without a timezone suffix (e.g. `"2026-10-02 15:30:00"`) is interpreted in the **local timezone** of the CLI host, then converted to UTC and stored. Pass an explicit offset (`"2026-10-02T15:30:00+08:00"`) for unambiguous behavior.

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
