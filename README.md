# Claude Queue Manager

A local Claude Agent queue management platform with a frontend-backend separation architecture.

Features:
- SQLite persistent task queue
- Multi-worker concurrency
- Auto-fetch next task after completion
- Independent workspace per task
- Invokes local claude CLI
- Real-time stdout/stderr saving
- WebSocket real-time logs
- Automatic retry
- Resume RUNNING tasks on startup
- React frontend for task creation/view/cancel/retry

## Prerequisites

Ensure the Claude Code CLI is available on your system:

    claude --version

And complete the required Claude CLI authentication.

## Startup

### Backend

Windows:

    cd backend
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python -m app

macOS/Linux:

    cd backend
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m app

### Frontend

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173 in your browser.

## Configuration

Environment variables (backend):

    HOST=127.0.0.1
    PORT=8000
    CLAUDE_BIN=claude
    WORKERS=2
    MAX_RETRIES=2
    DB_PATH=./data/tasks.db
    WORKSPACE_ROOT=./workspace
    LOG_ROOT=./logs

Example:

    $env:WORKERS="3"
    python -m app

## Queue Mechanism

SQLite Queue -> Worker -> Claude Session -> SUCCESS/RETRY/FAILED -> Worker fetches next task.

Note: Claude Agent can execute commands, read files, and modify the workspace. It is recommended to use a dedicated project directory or Git worktree, and avoid letting untrusted tasks access important data.
