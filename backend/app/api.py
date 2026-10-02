import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .config import settings
from .db import get_task, list_tasks, insert_task, retry_task, cancel_task, delete_task
from .runner import continue_session
from .events import events

app = FastAPI(title="Claude Queue Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskCreate(BaseModel):
    prompt: str = Field(min_length=1)
    max_retries: int | None = Field(default=None, ge=0, le=20)
    scheduled_at: datetime | None = Field(default=None, description="ISO-8601 datetime; if provided with timezone it will be honored. Naive datetimes are interpreted as UTC.")

class ContinueRequest(BaseModel):
    message: str = Field(min_length=1)

@app.get("/api/tasks")
async def tasks():
    return list_tasks()

@app.post("/api/tasks")
async def create_task(req: TaskCreate):
    try:
        task_id = uuid.uuid4().hex[:12]
        scheduled_iso = None
        is_scheduled_future = False
        if req.scheduled_at is not None:
            dt = req.scheduled_at
            # Naive datetime => treat as UTC (per Pydantic convention; warn via docstring).
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            scheduled_iso = dt.isoformat()
            now_iso = datetime.now(timezone.utc).isoformat()
            is_scheduled_future = scheduled_iso > now_iso
        task = {
            "id": task_id,
            "prompt": req.prompt,
            "workspace": str(settings.workspace_root / task_id),
            "log_file": str(settings.log_root / f"{task_id}.log"),
            "trace_file": str(settings.log_root / f"{task_id}.trace.jsonl"),
            "max_retries": settings.max_retries if req.max_retries is None else req.max_retries,
            "scheduled_at": scheduled_iso,
        }
        insert_task(task)
        if is_scheduled_future:
            await events.publish({"type":"task_scheduled","task_id":task_id,"scheduled_at":scheduled_iso})
        else:
            await events.publish({"type":"task_created","task_id":task_id})
        return get_task(task_id)
    except Exception as e:
        raise HTTPException(500, f"创建任务失败: {str(e)}")

@app.get("/api/tasks/{task_id}")
async def task(task_id: str):
    item = get_task(task_id)
    if not item:
        raise HTTPException(404, "Task not found")
    return item

@app.get("/api/tasks/{task_id}/log")
async def log(task_id: str):
    item = get_task(task_id)
    if not item:
        raise HTTPException(404, "Task not found")
    p = Path(item["log_file"])
    return {"task_id":task_id, "log":p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""}

@app.get("/api/tasks/{task_id}/trace")
async def trace(task_id: str):
    """返回结构化的执行过程（工具调用链等）"""
    item = get_task(task_id)
    if not item:
        raise HTTPException(404, "Task not found")
    trace_path = Path(item.get("trace_file", ""))
    if not trace_path.exists():
        return {"task_id": task_id, "trace": [], "has_trace": False}
    lines = trace_path.read_text(encoding="utf-8", errors="replace").strip().split("\n")
    events = []
    for line in lines:
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"task_id": task_id, "trace": events, "has_trace": True}

@app.post("/api/tasks/{task_id}/retry")
async def retry(task_id: str):
    if not retry_task(task_id):
        raise HTTPException(400, "Only FAILED tasks can be retried")
    return get_task(task_id)

@app.post("/api/tasks/{task_id}/cancel")
async def cancel(task_id: str):
    if not cancel_task(task_id):
        raise HTTPException(400, "Only PENDING tasks can be cancelled")
    return get_task(task_id)

@app.post("/api/tasks/{task_id}/continue")
async def continue_task(task_id: str, req: ContinueRequest):
    """向现有 session 发送消息继续对话"""
    item = get_task(task_id)
    if not item:
        raise HTTPException(404, "Task not found")
    if not item.get("session_id"):
        raise HTTPException(400, "No session_id found. Task may not have been run yet.")
    result = await continue_session(item, req.message)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return {"status": "ok", "message": "Message sent to session"}

@app.delete("/api/tasks/{task_id}")
async def delete(task_id: str):
    if not delete_task(task_id):
        raise HTTPException(404, "Task not found")
    return {"ok": True}

@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    q = await events.subscribe()
    try:
        while True:
            await ws.send_text(json.dumps(await q.get(), ensure_ascii=False))
    except WebSocketDisconnect:
        pass
    finally:
        events.unsubscribe(q)
