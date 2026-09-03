# Claude Queue Manager

本项目是一个本地 Claude Agent 队列管理平台（前后端分离架构）。

功能：
- SQLite 持久化任务队列
- 多 Worker 并发
- 一个任务完成后自动领取下一个任务
- 每个任务独立 workspace
- 调用本机 claude CLI
- 实时保存 stdout/stderr
- WebSocket 实时日志
- 自动重试
- 启动恢复 RUNNING 任务
- React 前端创建/查看/取消/重试任务

## 前置条件

确保本机 Claude Code CLI 可用：

    claude --version

并完成 Claude CLI 所需认证。

## 启动

### 后端

Windows：

    cd backend
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python -m app

macOS/Linux：

    cd backend
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python -m app

### 前端

    cd frontend
    npm install
    npm run dev

浏览器打开 http://localhost:5173

## 配置

环境变量（后端）：

    HOST=127.0.0.1
    PORT=8000
    CLAUDE_BIN=claude
    WORKERS=2
    MAX_RETRIES=2
    DB_PATH=./data/tasks.db
    WORKSPACE_ROOT=./workspace
    LOG_ROOT=./logs

例如：

    $env:WORKERS="3"
    python -m app

## 队列机制

SQLite Queue -> Worker -> Claude Session -> SUCCESS/RETRY/FAILED -> Worker 继续领取下一个任务。

注意：Claude Agent 可以执行命令、读取文件和修改 workspace。建议使用专用项目目录或 Git worktree，不要直接让不可信任务访问重要数据。