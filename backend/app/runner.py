import asyncio
import os
from pathlib import Path
from .config import settings
from .db import set_pid, finish_task, mark_retry_or_failed
from .events import events

async def run_task(task):
    workspace = Path(task["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    log_path = Path(task["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [settings.claude_bin, "-p", task["prompt"],"--dangerously-skip-permissions","--disallowed-tools", "AskUserQuestion"]

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

        with log_path.open("a", encoding="utf-8", errors="replace") as log:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else line
                log.write(text)
                log.flush()
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
