import asyncio
import json
import os
from pathlib import Path
from .config import settings
from .db import set_pid, set_session_id, finish_task, mark_retry_or_failed
from .events import events

async def run_task(task):
    workspace = Path(task["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    log_path = Path(task["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 结构化执行过程文件
    trace_path = log_path.with_suffix(".trace.jsonl")
    trace_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用 stream-json 输出格式，获取结构化的工具调用链
    cmd = [
        settings.claude_bin, "-p", task["prompt"],
        "--dangerously-skip-permissions",
        "--disallowed-tools", "AskUserQuestion",
        "--output-format", "stream-json",
        "--verbose",
    ]

    await events.publish({"type":"task_started","task_id":task["id"],"status":"RUNNING"})

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=os.environ.copy(),
        )
        set_pid(task["id"], proc.pid)
        session_id_captured = False

        with (
            log_path.open("a", encoding="utf-8", errors="replace") as log,
            trace_path.open("a", encoding="utf-8", errors="replace") as trace,
        ):
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
                log.write(text)
                log.flush()

                # 尝试解析 JSON 行，提取工具调用事件
                stripped = text.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        event = json.loads(stripped)
                        event_type = event.get("type", "")
                        # 捕获 session_id (在 event 顶层)
                        if not session_id_captured:
                            sess_id = event.get("session_id")
                            if sess_id:
                                set_session_id(task["id"], sess_id)
                                session_id_captured = True
                        # 记录工具调用和结果到结构化文件
                        if event_type in ("tool_use", "tool_result", "assistant", "usage", "content"):
                            trace.write(json.dumps(event, ensure_ascii=False) + "\n")
                            trace.flush()
                        # 同时发布原始日志事件
                        await events.publish({"type":"log","task_id":task["id"],"data":text})
                    except json.JSONDecodeError:
                        await events.publish({"type":"log","task_id":task["id"],"data":text})
                else:
                    await events.publish({"type":"log","task_id":task["id"],"data":text})

        code = await proc.wait()

        if code == 0:
            finish_task(task["id"], "SUCCESS", 0)
            status = "SUCCESS"
        else:
            status = mark_retry_or_failed(task)

        await events.publish({"type":"task_finished","task_id":task["id"],"status":status,"exit_code":code})

    except FileNotFoundError as e:
        finish_task(task["id"], "FAILED", None, f"Claude CLI not found: {e}")
        await events.publish({"type":"task_finished","task_id":task["id"],"status":"FAILED"})
    except Exception as e:
        status = mark_retry_or_failed(task)
        await events.publish({"type":"task_finished","task_id":task["id"],"status":status,"error":str(e)})


async def continue_session(task, message):
    """向现有 session 发送消息并返回结果"""
    session_id = task.get("session_id")
    if not session_id:
        return {"error": "No session_id found for this task"}

    workspace = Path(task["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    log_path = Path(task["log_file"])
    trace_path = log_path.with_suffix(".trace.jsonl")

    # 使用 --continue 参数恢复会话
    cmd = [
        settings.claude_bin, "-p", message,
        "--dangerously-skip-permissions",
        "--disallowed-tools", "AskUserQuestion",
        "--output-format", "stream-json",
        "--verbose",
        "--continue",
    ]

    await events.publish({"type":"task_started","task_id":task["id"],"status":"RUNNING"})

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=os.environ.copy(),
        )
        set_pid(task["id"], proc.pid)

        with (
            log_path.open("a", encoding="utf-8", errors="replace") as log,
            trace_path.open("a", encoding="utf-8", errors="replace") as trace,
        ):
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
                log.write(text)
                log.flush()

                stripped = text.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        event = json.loads(stripped)
                        event_type = event.get("type", "")
                        if event_type in ("tool_use", "tool_result", "assistant", "usage", "content"):
                            trace.write(json.dumps(event, ensure_ascii=False) + "\n")
                            trace.flush()
                        await events.publish({"type":"log","task_id":task["id"],"data":text})
                    except json.JSONDecodeError:
                        await events.publish({"type":"log","task_id":task["id"],"data":text})
                else:
                    await events.publish({"type":"log","task_id":task["id"],"data":text})

        code = await proc.wait()

        if code == 0:
            finish_task(task["id"], "SUCCESS", 0)
            status = "SUCCESS"
        else:
            status = mark_retry_or_failed(task)

        await events.publish({"type":"task_finished","task_id":task["id"],"status":status,"exit_code":code})
        return {"status": status, "exit_code": code}

    except Exception as e:
        return {"error": str(e)}
